// =============================================================================
// ha_values.cpp - Home Assistant state extraction from genmon reports
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "ha_values.h"

#include <algorithm>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <set>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

constexpr const char* kUnknownValues[] = {"unknown", "n/a", "none", "--"};

constexpr const char* kWeekdays[] = {
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
};

// Upstream's unit patterns, in its match order: a value ending in one of
// `suffixes` (after a number) gets `unit`. An empty unit means "matched, but
// leave the unit to Home Assistant" (temperatures).
struct UnitPattern {
    std::vector<std::string> suffixes;   // lowercase
    const char*              unit;
};

const std::vector<UnitPattern>& unitPatterns() {
    static const std::vector<UnitPattern> kPatterns = {
        {{"v", "volt", "volts"},          "V"},
        {{"a", "amp", "amps"},            "A"},
        {{"w", "watt", "watts"},          "W"},
        {{"kw", "kilowatt", "kilowatts"}, "kW"},
        {{"kwh"},                         "kWh"},
        {{"hz", "hertz"},                 "Hz"},
        {{"rpm"},                         "RPM"},
        {{"%", "percent"},                "%"},
        {{"c", "f", "\xC2\xB0" "c", "\xC2\xB0" "f"}, ""},
        {{"h", "hr", "hrs", "hour", "hours"}, "h"},
        {{"s", "sec", "second", "seconds"},  "s"},
        {{"gal", "gallon", "gallons"},    "gal"},
        {{"l", "liter", "liters"},        "L"},
        {{"psi"},                         "psi"},
        {{"cc"},                          "cc"},
    };
    return kPatterns;
}

const char* const kLogTypes[] = {"Outage Log", "Alarm Log", "Run Log"};

const char* const kDynamicSkipFragments[] = {"controller settings"};

constexpr int kTwoDecimals = 100;


// =============================================================================
// String helpers
// =============================================================================

std::string lowercase(std::string text) {
    std::transform(text.begin(), text.end(), text.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    return text;
}


std::string trim(const std::string& text) {
    const size_t first = text.find_first_not_of(" \t\r\n");
    if (first == std::string::npos) {
        return "";
    }
    const size_t last = text.find_last_not_of(" \t\r\n");
    return text.substr(first, last - first + 1);
}


std::vector<std::string> split(const std::string& text, char separator) {
    std::vector<std::string> parts;
    size_t start = 0;
    while (true) {
        const size_t found = text.find(separator, start);
        parts.push_back(text.substr(start, found - start));
        if (found == std::string::npos) {
            return parts;
        }
        start = found + 1;
    }
}


std::vector<std::string> splitWhitespace(const std::string& text) {
    std::vector<std::string> words;
    std::string              current;
    for (char c : text) {
        if (std::isspace(static_cast<unsigned char>(c))) {
            if (!current.empty()) {
                words.push_back(current);
                current.clear();
            }
        } else {
            current.push_back(c);
        }
    }
    if (!current.empty()) {
        words.push_back(current);
    }
    return words;
}


bool contains(const std::string& text, const std::string& fragment) {
    return text.find(fragment) != std::string::npos;
}


bool isDigit(char c) {
    return std::isdigit(static_cast<unsigned char>(c)) != 0;
}


bool isAllDigits(const std::string& text) {
    return !text.empty() && std::all_of(text.begin(), text.end(), isDigit);
}


bool isUnknownText(const std::string& text) {
    const std::string lower = lowercase(text);
    for (const char* unknown : kUnknownValues) {
        if (lower == unknown) {
            return true;
        }
    }
    return false;
}


// Length of a run of digits starting at `index`.
size_t digitRun(const std::string& text, size_t index) {
    size_t count = 0;
    while (index + count < text.size() && isDigit(text[index + count])) {
        ++count;
    }
    return count;
}


// =============================================================================
// Pattern helpers (hand-written equivalents of upstream's regular expressions)
// =============================================================================

// \d{1,2}:\d{2} starting at `index`.
bool clockAt(const std::string& text, size_t index, bool requireSeconds) {
    const size_t hours = digitRun(text, index);
    if (hours < 1 || hours > 2 || index + hours >= text.size() || text[index + hours] != ':') {
        return false;
    }
    const size_t minutesAt = index + hours + 1;
    if (digitRun(text, minutesAt) < 2) {
        return false;
    }
    if (!requireSeconds) {
        return true;
    }
    const size_t secondsAt = minutesAt + 2;
    return secondsAt < text.size() && text[secondsAt] == ':' && digitRun(text, secondsAt + 1) >= 2;
}


// ^\d{a,b}[-/]\d{1,2}[-/]\d{c,d}
bool dateAtStart(const std::string& text, size_t firstMin, size_t firstMax, size_t lastMin, size_t lastMax) {
    const size_t first = digitRun(text, 0);
    if (first < firstMin || first > firstMax || first >= text.size()) {
        return false;
    }
    if (text[first] != '-' && text[first] != '/') {
        return false;
    }
    const size_t second = digitRun(text, first + 1);
    const size_t afterSecond = first + 1 + second;
    if (second < 1 || second > 2 || afterSecond >= text.size()) {
        return false;
    }
    if (text[afterSecond] != '-' && text[afterSecond] != '/') {
        return false;
    }
    const size_t third = digitRun(text, afterSecond + 1);
    return third >= lastMin && third <= std::max(lastMax, lastMin) && third > 0;
}


// ^\w+day\s+\w+\s+\d  ("Thursday December 4 ...")
bool weekdayDateAtStart(const std::string& text) {
    const std::vector<std::string> words = splitWhitespace(text);
    if (words.size() < 3) {
        return false;
    }
    const std::string first = lowercase(words[0]);
    return first.size() > 3 && first.compare(first.size() - 3, 3, "day") == 0 && isDigit(words[2][0]);
}


bool looksLikeDateOrTime(const std::string& text) {
    if (dateAtStart(text, 1, 2, 2, 4) || dateAtStart(text, 4, 4, 1, 2)) {
        return true;
    }
    if (weekdayDateAtStart(text) || clockAt(text, 0, false)) {
        return true;
    }
    for (size_t index = 0; index < text.size(); ++index) {
        if (clockAt(text, index, true)) {
            return true;
        }
    }
    return false;
}


// First match of ([+-]?[0-9]*\.?[0-9]+).
std::optional<double> firstNumber(const std::string& text) {
    for (size_t index = 0; index < text.size(); ++index) {
        const bool startsDigits = isDigit(text[index]);
        const bool startsDot    = text[index] == '.' && index + 1 < text.size() && isDigit(text[index + 1]);
        if (!startsDigits && !startsDot) {
            continue;
        }
        size_t start = index;
        if (start > 0 && (text[start - 1] == '+' || text[start - 1] == '-')) {
            --start;
        }
        size_t end = index + digitRun(text, index);
        if (end < text.size() && text[end] == '.' && digitRun(text, end + 1) > 0) {
            end += 1 + digitRun(text, end + 1);
        }
        return std::strtod(text.substr(start, end - start).c_str(), nullptr);
    }
    return std::nullopt;
}


std::optional<std::string> unitFromText(const std::string& value) {
    const std::string lower = lowercase(trim(value));
    for (const UnitPattern& pattern : unitPatterns()) {
        for (const std::string& suffix : pattern.suffixes) {
            if (lower.size() <= suffix.size() || lower.compare(lower.size() - suffix.size(), suffix.size(), suffix) != 0) {
                continue;
            }
            const std::string before = trim(lower.substr(0, lower.size() - suffix.size()));
            if (!before.empty() && (isDigit(before.back()) || before.back() == '.')) {
                if (pattern.unit[0] == '\0') {
                    return std::nullopt;
                }
                return std::string(pattern.unit);
            }
        }
    }
    return std::nullopt;
}


// =============================================================================
// JSON helpers
// =============================================================================

// Exact key presence, including keys whose value is null.
bool hasKey(JsonObjectConst object, const std::string& key) {
    for (JsonPairConst pair : object) {
        if (key == pair.key().c_str()) {
            return true;
        }
    }
    return false;
}


// A genmon numeric leaf: an object whose keys are a subset of {type, value, unit}
// and that has a value.
bool isGenmonEntity(JsonVariantConst node) {
    if (!node.is<JsonObjectConst>()) {
        return false;
    }
    JsonObjectConst object = node.as<JsonObjectConst>();
    if (!hasKey(object, "value")) {
        return false;
    }
    for (JsonPairConst pair : object) {
        const std::string key = pair.key().c_str();
        if (key != "type" && key != "value" && key != "unit") {
            return false;
        }
    }
    return true;
}


bool isNumber(JsonVariantConst value) {
    return value.is<double>() || value.is<long long>();
}


// Text form of a plain JSON value, as Python's str() would produce it.
std::string variantText(JsonVariantConst value) {
    if (value.is<const char*>()) {
        return value.as<const char*>();
    }
    if (value.is<bool>()) {
        return value.as<bool>() ? "True" : "False";
    }
    if (value.is<long long>()) {
        return std::to_string(value.as<long long>());
    }
    if (value.is<double>()) {
        return pythonNumber(value.as<double>(), true);
    }
    return "";
}


// The scalar inside a genmon numeric leaf, plus whether genmon tagged it float.
JsonVariantConst innerValue(JsonVariantConst value, bool& isFloat) {
    isFloat = false;
    if (value.is<JsonObjectConst>()) {
        isFloat = std::string(value["type"] | "") == "float";
        return value["value"];
    }
    isFloat = value.is<double>() && !value.is<long long>();
    return value;
}


JsonVariantConst findKey(JsonObjectConst object, const std::string& part) {
    JsonVariantConst exact = object[part];
    if (!exact.isNull() || hasKey(object, part)) {
        return exact;
    }
    const std::string lowerPart = lowercase(part);
    for (JsonPairConst pair : object) {
        if (lowercase(pair.key().c_str()) == lowerPart) {
            return pair.value();
        }
    }
    return JsonVariantConst();
}


bool hasKeyInsensitive(JsonObjectConst object, const std::string& part) {
    if (hasKey(object, part)) {
        return true;
    }
    const std::string lowerPart = lowercase(part);
    for (JsonPairConst pair : object) {
        if (lowercase(pair.key().c_str()) == lowerPart) {
            return true;
        }
    }
    return false;
}


struct Leaf {
    std::string      path;
    JsonVariantConst value;
};


void walk(JsonVariantConst node, const std::string& path, std::vector<Leaf>& leaves) {
    if (node.is<JsonObjectConst>()) {
        if (isGenmonEntity(node)) {
            if (!path.empty()) {
                leaves.push_back({path, node});
            }
            return;
        }
        for (JsonPairConst pair : node.as<JsonObjectConst>()) {
            const std::string childPath = path.empty() ? pair.key().c_str() : path + "/" + pair.key().c_str();
            if (pair.value().is<JsonObjectConst>() || pair.value().is<JsonArrayConst>()) {
                walk(pair.value(), childPath, leaves);
            } else {
                leaves.push_back({childPath, pair.value()});
            }
        }
    } else if (node.is<JsonArrayConst>()) {
        for (JsonVariantConst item : node.as<JsonArrayConst>()) {
            if (item.is<JsonObjectConst>()) {
                walk(item, path, leaves);
            }
        }
    }
}


std::string dynamicName(const std::string& path) {
    const std::vector<std::string> parts = split(path, '/');
    const auto lastTwo = [&parts]() {
        return parts.size() >= 2 ? parts[parts.size() - 2] + " " + parts.back() : parts.back();
    };

    bool isLog = false;
    for (const char* logType : kLogTypes) {
        isLog = isLog || contains(path, logType);
    }
    if (!isLog) {
        return lastTwo();
    }

    for (size_t index = 0; index < parts.size(); ++index) {
        if (!isAllDigits(parts[index])) {
            continue;
        }
        if (std::atoi(parts[index].c_str()) != 0) {
            return "";   // only the newest log entry becomes a sensor
        }
        if (index == 0) {
            return lastTwo();
        }
        std::string logType = parts[index - 1];
        const size_t suffix = logType.find(" Log");
        if (suffix != std::string::npos) {
            logType.erase(suffix, 4);
        }
        const std::string field = index < parts.size() - 1 ? parts.back() : "";
        return trim("Last " + logType + " " + field);
    }
    return lastTwo();
}


SensorDefinition dynamicSensor(const std::string& path, JsonVariantConst data) {
    SensorDefinition sensor;
    sensor.id       = pathToEntityId(path);
    sensor.name     = dynamicName(path);
    sensor.path     = path;
    sensor.category = "diagnostic";
    sensor.dynamic  = true;

    bool numeric = false;
    if (isGenmonEntity(data)) {
        sensor.unit = data["unit"] | "";
        const std::string type = data["type"] | "";
        numeric = type == "int" || type == "float" || isNumber(data["value"]);
    } else if (isNumber(data)) {
        numeric = true;
    } else {
        const std::string text = variantText(data);
        sensor.unit = unitFromText(text).value_or("");
        numeric     = !looksLikeDateOrTime(trim(text)) && firstNumber(trim(text)).has_value();
    }

    const std::string lowerName = lowercase(sensor.name);
    const std::string& unit = sensor.unit;
    if (unit == "V")                        sensor.deviceClass = "voltage";
    else if (unit == "A")                   sensor.deviceClass = "current";
    else if (unit == "W" || unit == "kW")   sensor.deviceClass = "power";
    else if (unit == "kWh")                 sensor.deviceClass = "energy";
    else if (unit == "Hz")                  sensor.deviceClass = "frequency";
    else if (unit == "h" || unit == "s")    sensor.deviceClass = "duration";
    else if (unit == "%")                   sensor.deviceClass = "";
    else if (contains(lowerName, "temp"))   sensor.deviceClass = "temperature";
    else if (contains(lowerName, "humidity")) sensor.deviceClass = "humidity";
    else if (contains(lowerName, "pressure")) sensor.deviceClass = "pressure";

    sensor.icon = "mdi:information-outline";
    if (contains(lowerName, "outage")) {
        sensor.icon = contains(lowerName, "date") ? "mdi:power-plug-off" : "mdi:timer-outline";
    } else if (contains(lowerName, "alarm")) {
        sensor.icon = "mdi:alert";
    } else if (contains(lowerName, "run")) {
        sensor.icon = "mdi:engine";
    }

    sensor.stateClass = numeric ? "measurement" : "";
    return sensor;
}


bool onlyNewestOutageEntry(const std::string& lowerPath) {
    const std::string marker = "outage log/";
    const size_t      found  = lowerPath.find(marker);
    if (found == std::string::npos) {
        return true;
    }
    const size_t start  = found + marker.size();
    const size_t digits = digitRun(lowerPath, start);
    if (digits == 0 || start + digits >= lowerPath.size() || lowerPath[start + digits] != '/') {
        return true;
    }
    return lowerPath.substr(start, digits) == "0";
}

}  // namespace


// =============================================================================
// Path lookup
// =============================================================================

JsonVariantConst valueAtPath(JsonVariantConst data, const std::string& path) {
    JsonVariantConst current = data;
    for (const std::string& part : split(path, '/')) {
        if (current.isNull()) {
            return JsonVariantConst();
        }
        if (current.is<JsonObjectConst>()) {
            JsonObjectConst object = current.as<JsonObjectConst>();
            if (!hasKeyInsensitive(object, part)) {
                return JsonVariantConst();
            }
            current = findKey(object, part);
            continue;
        }
        if (!current.is<JsonArrayConst>()) {
            return JsonVariantConst();
        }

        JsonArrayConst list  = current.as<JsonArrayConst>();
        bool           found = false;
        for (JsonVariantConst item : list) {
            if (item.is<JsonObjectConst>() && hasKeyInsensitive(item.as<JsonObjectConst>(), part)) {
                current = findKey(item.as<JsonObjectConst>(), part);
                found   = true;
                break;
            }
        }
        if (!found && isAllDigits(part)) {
            const size_t index = static_cast<size_t>(std::atoi(part.c_str()));
            if (index < list.size()) {
                current = list[index];
                found   = true;
            }
        }
        if (!found) {
            return JsonVariantConst();
        }
    }
    return current;
}


// =============================================================================
// State rules
// =============================================================================

std::optional<std::string> sensorState(JsonVariantConst value, const SensorDefinition& sensor) {
    if (value.is<JsonObjectConst>() && !hasKey(value.as<JsonObjectConst>(), "value")) {
        return std::nullopt;
    }

    bool             isFloat = false;
    JsonVariantConst scalar  = innerValue(value, isFloat);
    if (isNumber(scalar)) {
        return pythonNumber(scalar.as<double>(), isFloat);
    }

    const std::string text = trim(variantText(scalar));
    if (text.empty() || isUnknownText(text)) {
        return std::nullopt;
    }
    if (looksLikeDateOrTime(text)) {
        return text;
    }
    if (sensor.stateClass.empty() && sensor.deviceClass.empty()) {
        return text;
    }

    const std::optional<double> number = firstNumber(text);
    if (!number) {
        return text;
    }
    if (*number == std::floor(*number)) {
        return pythonNumber(*number, false);
    }
    return pythonNumber(std::round(*number * kTwoDecimals) / kTwoDecimals, true);
}


std::string binarySensorState(JsonVariantConst value, const BinarySensorDefinition& sensor) {
    // Numeric leaves are compared on their value, not the {unit,type,value}
    // wrapper, so payload_on_gt works with numeric JSON.
    bool              isFloat = false;
    const std::string text    = trim(variantText(innerValue(value, isFloat)));
    const std::string lower   = lowercase(text);

    if (sensor.onWhenNotEmpty) {
        return (!text.empty() && !isUnknownText(text)) ? "ON" : "OFF";
    }

    if (sensor.onWhenGreaterThan) {
        const std::vector<std::string> words = splitWhitespace(text);
        if (words.empty()) {
            return "OFF";
        }
        std::string digits;
        for (char c : words[0]) {
            if (isDigit(c) || c == '.' || c == '-') {
                digits.push_back(c);
            }
        }
        if (digits.empty()) {
            return "OFF";
        }
        return std::strtod(digits.c_str(), nullptr) > *sensor.onWhenGreaterThan ? "ON" : "OFF";
    }

    if (sensor.payloadOnIsList) {
        for (const std::string& on : sensor.payloadOn) {
            if (contains(lower, lowercase(on))) {
                return "ON";
            }
        }
        if (sensor.payloadOffInvert) {
            return "OFF";
        }
    }
    if (sensor.payloadOffIsList) {
        for (const std::string& off : sensor.payloadOff) {
            if (contains(lower, lowercase(off))) {
                return "OFF";
            }
        }
    }
    if (!sensor.payloadOnIsList && !sensor.payloadOn.empty() && lower == lowercase(sensor.payloadOn[0])) {
        return "ON";
    }
    return "OFF";
}


// =============================================================================
// Dynamic discovery
// =============================================================================

std::string pathToEntityId(const std::string& path) {
    std::string id;
    bool        pendingSeparator = false;
    for (char c : path) {
        if (c == '/' || std::isspace(static_cast<unsigned char>(c)) || c == '_') {
            pendingSeparator = !id.empty();
            continue;
        }
        const char lower = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
        if (!std::isalnum(static_cast<unsigned char>(lower))) {
            continue;
        }
        if (pendingSeparator) {
            id.push_back('_');
            pendingSeparator = false;
        }
        id.push_back(lower);
    }
    return id;
}


std::vector<SensorDefinition> discoverDynamicSensors(JsonVariantConst data, const EntityCatalog& catalog) {
    std::set<std::string> knownPaths;
    std::set<std::string> knownIds;
    for (const SensorDefinition& sensor : catalog.sensors) {
        knownPaths.insert(lowercase(sensor.path));
        knownIds.insert(sensor.id);
    }
    for (const BinarySensorDefinition& sensor : catalog.binarySensors) {
        knownPaths.insert(lowercase(sensor.path));
    }

    std::vector<Leaf> leaves;
    walk(data, "", leaves);

    std::vector<SensorDefinition> sensors;
    std::set<std::string>         seenIds;
    for (const Leaf& leaf : leaves) {
        const std::string lowerPath = lowercase(leaf.path);
        if (knownPaths.count(lowerPath) || leaf.path.rfind("Tiles/", 0) == 0) {
            continue;
        }
        bool skip = false;
        for (const char* fragment : kDynamicSkipFragments) {
            skip = skip || contains(lowerPath, fragment);
        }
        if (skip || !onlyNewestOutageEntry(lowerPath)) {
            continue;
        }

        bool              isFloat = false;
        JsonVariantConst  scalar  = innerValue(leaf.value, isFloat);
        const std::string text    = variantText(scalar);
        if (scalar.isNull() || (!isNumber(scalar) && (text.empty() || text == "--"))) {
            continue;
        }

        const std::string id = pathToEntityId(leaf.path);
        if (id.empty() || knownIds.count(id) || seenIds.count(id)) {
            continue;
        }
        SensorDefinition sensor = dynamicSensor(leaf.path, leaf.value);
        if (sensor.name.empty()) {
            continue;
        }
        seenIds.insert(id);
        sensors.push_back(sensor);
    }
    return sensors;
}


// =============================================================================
// Exercise controls
// =============================================================================

void parseExerciseTime(const std::string& text, ExerciseSettings& settings) {
    const std::vector<std::string> parts = splitWhitespace(text);
    if (parts.size() < 3) {
        return;
    }
    const std::string& frequency = parts[0];
    if (frequency == "Weekly" || frequency == "BiWeekly" || frequency == "Monthly") {
        settings.frequency = frequency;
    }

    std::string timePart;
    if (frequency == "Monthly") {
        if (parts.size() >= 4 && parts[1] == "Day") {
            if (isAllDigits(parts[2])) {
                settings.dayOfMonth = std::atoi(parts[2].c_str());
            }
            timePart = parts[3];
        } else {
            timePart = parts[2];
        }
    } else {
        for (const char* day : kWeekdays) {
            if (parts[1] == day) {
                settings.dayOfWeek = day;
            }
        }
        timePart = parts[2];
    }

    const std::vector<std::string> clock = split(timePart, ':');
    if (clock.size() >= 2 && isAllDigits(clock[0]) && isAllDigits(clock[1])) {
        settings.hour   = std::atoi(clock[0].c_str());
        settings.minute = std::atoi(clock[1].c_str());
    }
}


std::string exerciseCommand(ExerciseSettings& settings, bool enhanced) {
    if (!enhanced && settings.frequency != "Weekly") {
        settings.frequency = "Weekly";
    }
    char clock[8];
    std::snprintf(clock, sizeof(clock), "%02d:%02d", settings.hour, settings.minute);

    const std::string day = settings.frequency == "Monthly" ? std::to_string(settings.dayOfMonth) : settings.dayOfWeek;
    return "setexercise=" + day + "," + clock + "," + settings.frequency;
}


// =============================================================================
// Formatting
// =============================================================================

std::string pythonNumber(double value, bool isFloat) {
    char buffer[40];
    if (!isFloat) {
        std::snprintf(buffer, sizeof(buffer), "%lld", static_cast<long long>(std::llround(value)));
        return buffer;
    }
    // Shortest text that reads back as the same double, like Python's repr.
    for (int precision = 1; precision <= 17; ++precision) {
        std::snprintf(buffer, sizeof(buffer), "%.*g", precision, value);
        if (std::strtod(buffer, nullptr) == value) {
            break;
        }
    }
    std::string text = buffer;
    if (text.find_first_of(".eEn") == std::string::npos) {
        text += ".0";
    }
    return text;
}

}  // namespace genmon
