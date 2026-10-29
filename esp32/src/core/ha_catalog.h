// =============================================================================
// ha_catalog.h - Home Assistant entity definitions from upstream genmon
// =============================================================================
//
// Loads data/homeassistant/base.json, then generac_evo_nexus.json and an
// optional userdefined.json on top (later files replace entries with the same
// entity_id), exactly as upstream's genhomeassistant add-on does. The JSON is
// compiled in by esp32/tools/gen_upstream_data.py.

#pragma once


// =============================================================================
// Includes
// =============================================================================

#include <optional>
#include <string>
#include <vector>


namespace genmon {

// =============================================================================
// Types
// =============================================================================

// Fields every entity kind may carry that decide whether it is published.
struct EntityFilter {
    std::vector<std::string> controllers;    // empty: all controllers
    bool                     monitorStats = false;
    bool                     weather      = false;
};

struct SensorDefinition {
    std::string  id;
    std::string  name;
    std::string  path;
    std::string  deviceClass;
    std::string  unit;
    std::string  icon;
    std::string  stateClass;
    std::string  category;
    bool         enabledByDefault = true;
    bool         dynamic          = false;   // discovered by walking the reports
    EntityFilter filter;
};

struct BinarySensorDefinition {
    std::string              id;
    std::string              name;
    std::string              path;
    std::string              deviceClass;
    std::string              icon;
    std::string              category;
    std::vector<std::string> payloadOn;
    std::vector<std::string> payloadOff;
    bool                     payloadOnIsList  = false;
    bool                     payloadOffIsList = false;
    bool                     payloadOffInvert = false;
    bool                     onWhenNotEmpty   = false;
    std::optional<double>    onWhenGreaterThan;
    EntityFilter             filter;
};

struct ButtonDefinition {
    std::string  id;
    std::string  name;
    std::string  command;
    std::string  icon;
    EntityFilter filter;
};

struct SwitchDefinition {
    std::string  id;
    std::string  name;
    std::string  commandOn;
    std::string  commandOff;
    std::string  icon;
    std::string  statePath;
    std::string  payloadOn = "on";
    EntityFilter filter;
};

struct SelectDefinition {
    std::string              id;
    std::string              name;
    std::string              icon;
    std::string              commandTemplate;
    std::vector<std::string> options;
    EntityFilter             filter;
};

struct NumberDefinition {
    std::string  id;
    std::string  name;
    std::string  icon;
    std::string  unit;
    std::string  commandTemplate;
    double       min  = 0.0;
    double       max  = 100.0;
    double       step = 1.0;
    EntityFilter filter;
};

struct EntityCatalog {
    std::vector<SensorDefinition>       sensors;
    std::vector<BinarySensorDefinition> binarySensors;
    std::vector<ButtonDefinition>       buttons;
    std::vector<SwitchDefinition>       switches;
    std::vector<SelectDefinition>       selects;
    std::vector<NumberDefinition>       numbers;
};

struct EntityPolicy {
    std::string              controllerType;          // "evolution" or "nexus"
    std::vector<std::string> blacklist = {"tiles"};   // lowercase substrings
    bool                     includeMonitorStats = true;
    bool                     includeWeather      = true;
};


// =============================================================================
// Functions
// =============================================================================

// Parses and merges definition documents in order; later documents replace
// earlier entries with the same id. Malformed documents are skipped and
// reported through `errors`.
EntityCatalog loadCatalog(const std::vector<const char*>& documents, std::vector<std::string>& errors);

// The compiled-in upstream definitions.
EntityCatalog loadBuiltInCatalog(std::vector<std::string>& errors);

// Mirrors genhomeassistant's _entity_allowed(): blacklist on name, id or
// path; controller list; monitor-stats and weather switches.
bool entityAllowed(const std::string&  id,
                   const std::string&  name,
                   const std::string&  path,
                   const EntityFilter& filter,
                   const EntityPolicy& policy);

}  // namespace genmon
