// =============================================================================
// controller_info.cpp - Controller family detection from the product code
// =============================================================================

// =============================================================================
// Includes
// =============================================================================

#include "controller_info.h"

#include <cstdio>


namespace genmon {

namespace {

// =============================================================================
// Constants
// =============================================================================

struct ProductCode {
    uint16_t    code;
    bool        evolution;
    bool        liquidCooled;
    const char* name;
};

constexpr ProductCode kProductCodes[] = {
    {0x02, false, false, "Pre-Nexus, Air Cooled"},
    {0x03, false, false, "Nexus, Air Cooled"},
    {0x04, false, false, "Nexus, Air Cooled (4)"},
    {0x05, false, false, "Nexus, Air Cooled (5)"},
    {0x06, false, true,  "Nexus, Liquid Cooled"},
    {0x07, false, true,  "Nexus, Liquid Cooled (7)"},
    {0x08, false, true,  "Nexus, Liquid Cooled (8)"},
    {0x09, true,  false, "Evolution, Air Cooled"},
    {0x0A, true,  false, "Synergy Evolution, Air Cooled"},
    {0x0B, true,  false, "Evolution, Air Cooled (11)"},
    {0x0C, true,  true,  "Evolution, Liquid Cooled"},
    {0x12, true,  false, "Power Pact Evolution, Air Cooled"},
    {0x13, true,  false, "Power Pact Evolution, Air Cooled (19)"},
    {0x14, true,  false, "Power Pact Evolution, Air Cooled (20)"},
    {0x15, true,  false, "Evolution 2.0, Air Cooled"},
    {0x16, true,  true,  "Evolution 4.5L, Liquid Cooled"},
    {0x19, true,  false, "Power Zone 200, Air Cooled"},
};

// Codes at or below this are Nexus-era when the exact code is unknown.
constexpr uint16_t kHighestNexusCode = 0x06;


// =============================================================================
// Helpers
// =============================================================================

const ProductCode* findProductCode(uint16_t code) {
    for (const ProductCode& entry : kProductCodes) {
        if (entry.code == code) {
            return &entry;
        }
    }
    return nullptr;
}


bool resolve(Detect override, bool detected) {
    switch (override) {
        case Detect::Yes: return true;
        case Detect::No:  return false;
        default:          return detected;
    }
}

}  // namespace


// =============================================================================
// Core logic
// =============================================================================

ControllerInfo detectController(uint16_t productCode,
                                Detect   evolutionOverride,
                                Detect   liquidCooledOverride,
                                bool     enhancedExerciseSetting,
                                bool     legacyExerciseWriteSetting) {
    ControllerInfo info;
    info.detected     = true;
    info.productCode  = productCode;
    info.powerZone200 = productCode == 0x19;
    info.synergy      = productCode == 0x0A;
    info.evolution2   = productCode == 0x15;
    info.powerPact    = productCode >= 0x12 && productCode <= 0x14;
    info.preNexus     = productCode == 0x02;
    info.evolution45L = productCode == 0x16;

    const ProductCode* known = findProductCode(productCode);
    info.knownCode = known != nullptr;

    const bool detectedEvolution = known ? known->evolution    : productCode > kHighestNexusCode;
    const bool detectedLiquid    = known ? known->liquidCooled : false;

    info.evolution    = resolve(evolutionOverride, detectedEvolution);
    info.liquidCooled = resolve(liquidCooledOverride, detectedLiquid);

    // Nexus firmware only accepts the indexed-command form of the exercise write.
    info.legacyExerciseWrite = legacyExerciseWriteSetting || !info.evolution;

    info.enhancedExercise = enhancedExerciseSetting || info.evolution2 || info.powerPact ||
                            info.synergy || info.powerZone200;
    return info;
}


std::string controllerFamilyName(const ControllerInfo& info) {
    std::string name;
    if (info.evolution) {
        if (info.powerZone200)      name = "Power Zone 200, ";
        else if (info.synergy)      name = "Synergy Evolution, ";
        else if (info.powerPact)    name = "Power Pact Evolution, ";
        else if (info.evolution2)   name = "Evolution 2.0, ";
        else if (info.evolution45L) name = "Evolution 4.5L, ";
        else                        name = "Evolution, ";
    } else {
        name = info.preNexus ? "Pre-Nexus, " : "Nexus, ";
    }
    name += info.liquidCooled ? "Liquid Cooled" : "Air Cooled";
    return name;
}


std::string productCodeName(uint16_t productCode) {
    const ProductCode* known = findProductCode(productCode);
    if (known) {
        return known->name;
    }
    char buffer[24];
    std::snprintf(buffer, sizeof(buffer), "Unknown 0x%02X", productCode);
    return buffer;
}

}  // namespace genmon
