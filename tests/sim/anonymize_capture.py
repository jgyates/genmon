#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: anonymize_capture.py
# PURPOSE: Makes a register capture (a genmon register dump, e.g. from "send
#          registers") safe to add to the repository for the simulator tests
#          (tests/test_genmon_sim.py):
#
#            - only the register data gensim reads is kept (Registers or
#              Holding, Strings, FileData, Coils, Inputs). Everything else is
#              left out: site name, settings, install date, Raspberry Pi and
#              network details, statistics.
#            - serial numbers are replaced with made up ones of the same length
#              (digits 1234567890..., letters X), at the places each
#              controller type keeps them (for a custom controller: the entries
#              of its data/controller file with "serial" in the title).
#            - every other readable text in the register data is listed, to
#              check by hand before the file is added.
#
#   USAGE: from the root of the repository:
#              python3 tests/sim/anonymize_capture.py <capture> <output>
#                  --controller generac_evo_nexus|h_100|powerzone_pro|custom
#                  [--import-config <data/controller file, for custom>]
#                  [--comment "<what the capture is>"]
#
# -------------------------------------------------------------------------------

import argparse
import binascii
import collections
import json
import os
import re
import sys

REPO_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# the sections gensim reads (tests/sim/gensim.py ReadJSONFile)
SECTIONS = ["Registers", "Holding", "Strings", "FileData", "Coils", "Inputs"]
# a capture in the repository has only these keys
ALLOWED_KEYS = ["Comment"] + SECTIONS

# where each controller type keeps the serial number: (section, register)
SERIALS = {
    "generac_evo_nexus": [("Registers", "01f4")],  # Evolution and Nexus
    "h_100": [("FileData", "0040")],                # name plate
    "powerzone_pro": [],                            # not in the registers read
}


def fake_text(text):
    """A made up value of the same length and form: digits 1234567890...,
    letters X, other characters (spaces, padding, dashes) kept."""
    digits = "1234567890"
    out, count = [], 0
    for char in text:
        if char.isdigit():
            out.append(digits[count % len(digits)])
            count += 1
        elif char.isalpha():
            out.append("X")
        else:
            out.append(char)
    return "".join(out)


def fake_hex_text(value):
    """value: hex of ASCII text (as in the registers); the text made up."""
    data = binascii.unhexlify(value)
    text = data.decode("latin-1")
    return binascii.hexlify(fake_text(text).encode("latin-1")).decode()


def fake_hex_number(value):
    """value: hex of a number; a made up number of the same size."""
    digits = len(value)
    number = int(("1234567890" * 4)[:digits], 10) % (16 ** digits)
    return "%0*x" % (digits, number)


def custom_serials(import_config):
    """(section, register, type) of the serial number entries of a custom
    controller file."""
    path = import_config
    if not os.path.isfile(path):
        path = os.path.join(REPO_DIR, "data", "controller", import_config)
    with open(path) as f:
        controller = json.load(f)
    found = []

    def walk(item):
        if isinstance(item, dict):
            if "reg" in item and re.search(r"serial", str(item.get("title", "")), re.I):
                kind = item.get("reg_type", "holding")
                section = {"input": "Inputs", "coil": "Coils"}.get(kind, "Holding")
                found.append((section, item["reg"].lower(), item.get("type", "")))
            for value in item.values():
                walk(value)
        elif isinstance(item, list):
            for value in item:
                walk(value)

    walk(controller)
    return found


def readable_text(capture):
    """(section, register, text) of each readable text of 4 or more
    characters in the register data."""
    found = []
    for section in SECTIONS:
        for register, value in capture.get(section, {}).items():
            try:
                data = binascii.unhexlify(value)
            except (binascii.Error, TypeError, ValueError):
                continue
            for match in re.finditer(rb"[ -~]{4,}", data):
                text = match.group().decode()
                if text.strip():
                    found.append((section, register, text))
    return found


def anonymize(capture, controller, import_config=None, comment=None):
    """The anonymized capture, and a list of what was replaced."""
    out = collections.OrderedDict()
    if comment:
        out["Comment"] = comment
    for section in SECTIONS:
        if section in capture:
            out[section] = collections.OrderedDict(capture[section])
    for section in ["Strings", "FileData"]:
        out.setdefault(section, collections.OrderedDict())

    if controller == "custom":
        if not import_config:
            raise ValueError("a custom controller needs --import-config")
        places = [(s, r, t) for s, r, t in custom_serials(import_config)]
    elif controller in SERIALS:
        places = [(s, r, "ascii") for s, r in SERIALS[controller]]
    else:
        raise ValueError("unknown controller type: " + str(controller))

    replaced = []
    for section, register, kind in places:
        # the holding registers are "Registers" in some captures
        sections = [section] + (["Registers"] if section == "Holding" else [])
        for name in sections:
            value = out.get(name, {}).get(register)
            if not value:
                continue
            if kind == "ascii":
                new = fake_hex_text(value)
            else:
                new = fake_hex_number(value)
            out[name][register] = new
            replaced.append((name, register, value, new))
    return out, replaced


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture")
    parser.add_argument("output")
    parser.add_argument("--controller", required=True,
                        help="genmon.conf controllertype: " + ", ".join(list(SERIALS) + ["custom"]))
    parser.add_argument("--import-config", help="the data/controller file of a custom controller")
    parser.add_argument("--comment", help="what the capture is (kept in the file)")
    args = parser.parse_args()

    with open(args.capture) as f:
        capture = json.load(f, object_pairs_hook=collections.OrderedDict)
    out, replaced = anonymize(capture, args.controller, args.import_config, args.comment)

    with open(args.output, "w") as f:
        json.dump(out, f, indent=1)
        f.write("\n")

    left_out = [key for key in capture if key not in out]
    print("Left out: " + (", ".join(left_out) if left_out else "nothing"))
    for section, register, old, new in replaced:
        print("Replaced serial number %s %s: %r -> %r" % (
            section, register, binascii.unhexlify(old).decode("latin-1", "replace").strip()
            if all(c in "0123456789abcdef" for c in old.lower()) and len(old) % 2 == 0 else old,
            binascii.unhexlify(new).decode("latin-1", "replace").strip()))
    texts = readable_text(out)
    if texts:
        print("Readable text left in the registers (check none of it identifies anyone):")
        for section, register, text in texts:
            print("  %s %s: %r" % (section, register, text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
