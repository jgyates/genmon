"""Build esp32/docs/images/upstream/ from genmon's Diagrams/ folder.

Copies the upstream photos and diagrams that apply to an ESP32 build of an
Evolution / Nexus monitor, resized for the web, and stamps a banner on every
image that shows a Raspberry Pi explaining that an ESP32 takes its place.
The manifest below is the single list of what is included and why, so an
upstream sync only has to add or adjust entries and re-run the script.

Usage:
    python esp32/tools/build_doc_images.py [--check]

Requires Pillow (see esp32/tools/requirements.txt). With --check nothing is
written; the exit status is 1 if an output is missing, a source has
disappeared, or an image in the output folder is not in the manifest.
"""

# =============================================================================
# Imports
# =============================================================================

from __future__ import annotations

import argparse
import logging
import pathlib
import sys
import textwrap
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont, ImageOps


# =============================================================================
# Constants
# =============================================================================

ESP32_ROOT   = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT    = ESP32_ROOT.parent
SOURCE_DIR   = REPO_ROOT / "Diagrams"
OUTPUT_DIR   = ESP32_ROOT / "docs" / "images" / "upstream"

MAX_EDGE_PX  = 1600     # longest side of photos after resizing
JPEG_QUALITY = 82
BANNER_RGB   = (20, 24, 32)
TEXT_SCALE   = 0.032    # font size as a fraction of image width
MIN_FONT_PX  = 16
WRAP_CHARS   = 64

FONT_CANDIDATES = (
    "DejaVuSans-Bold.ttf",                       # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",             # macOS
    "C:/Windows/Fonts/arialbd.ttf",              # Windows
)

PI_NOTE = "Shown with a Raspberry Pi. In genmon-esp32 an ESP32 DevKitC replaces the Pi."

LOGGER = logging.getLogger("build_doc_images")


# =============================================================================
# Types
# =============================================================================

@dataclass(frozen=True)
class Entry:
    """One upstream image to publish in the ESP32 docs."""

    source: str              # path under Diagrams/
    output: str              # file name under docs/images/upstream/
    note: str | None = None  # banner text; set for every image showing a Pi


# =============================================================================
# Manifest
# =============================================================================

# Upstream images deliberately left out: genmon logos, the Pi web UI
# screenshot, H-100 / G-Panel, MEBAY, PowerZone and RS-485 material, fuel
# gauge sensors and the printable enclosure labels (none apply to an ESP32
# monitoring an Evolution or Nexus controller).
MANIFEST = (
    # fmt: off
    # Controllers and where the serial port is
    Entry("Evolution_Controller.jpg",                                    "evolution-controller.jpg"),
    Entry("Nexus_Controller.jpg",                                        "nexus-controller.jpg"),
    Entry("2008-PreNexusController.jpg",                                 "pre-nexus-controller.jpg"),
    Entry("casestudy/PowerPactController.jpeg",                          "powerpact-controller.jpg"),
    Entry("Controller_connection(Nexus).jpg",                            "nexus-serial-connector.jpg"),
    Entry("liquid_cooled_generac_back_of_controller.jpeg",               "liquid-cooled-controller-back.jpg"),
    Entry("evo_controller_power.jpg",                                    "controller-power-connector.jpg"),

    # Cable and connector
    Entry("Molex_Pinout.png",                                            "molex-pinout.png"),
    Entry("casestudy/MLPinout.png",                                      "mobilelink-pinout.png"),
    Entry("casestudy/MLCable.jpeg",                                      "mobilelink-cable.jpg"),
    Entry("casestudy/MobileLink2G.jpeg",                                 "mobilelink-module.jpg"),
    Entry("casestudy/repinning-cable.png",                               "repinning-diagram.png",
          "Target connector is the PintSize Pi HAT's. For an ESP32, wire 388 (TX) and 387 (RX) to the MAX3232 instead."),
    Entry("Cable (full- Liquid cooled models require longer cable).jpg", "cable-full.jpg"),
    Entry("Cable (End that connecets to Evolution Controller).jpg",      "cable-controller-end.jpg"),
    Entry("Cable (End that connecets to Evolution Controller) (2).jpg",  "cable-controller-end-2.jpg"),
    Entry("casestudy/crimppins.jpeg",                                    "crimping-pins.jpg"),
    Entry("casestudy/Tools.jpeg",                                        "tools.jpg"),

    # Wiring as built for the Pi
    Entry("wiring_schematic.png",                                        "pi-wiring-schematic.png",
          "Raspberry Pi version. For the ESP32 use GPIO17 (TX), GPIO16 (RX), 3V3 and GND: see wiring_esp32.svg."),
    Entry("Cable_Connections.jpg",                                       "pi-cable-connections.jpg",
          "Pi 3 header on the left. On the ESP32: 3V3 to VCC, GND to GND, GPIO17 to TXD, GPIO16 to RXD."),
    Entry("Example_Project.JPG",                                         "example-project.jpg", PI_NOTE),
    Entry("serial_loopback.jpeg",                                        "serial-loopback.jpg", PI_NOTE),
    Entry("casestudy/PintSizeMeHat.jpeg",                                "pintsize-hat.jpg",
          "PintSize HAT on a Pi Zero. In genmon-esp32 an ESP32 DevKitC plus MAX3232 module replace both boards."),
    Entry("casestudy/PintSizeMePinout.png",                              "pintsize-hat-pinout.png",
          "Pinout of the Pi HAT's connector (not the controller's). An ESP32 build does not use this connector."),

    # Enclosure, power and Wi-Fi
    Entry("Inside enclosure.jpg",                                        "inside-enclosure.jpg", PI_NOTE),
    Entry("Enclosure (1).jpg",                                           "enclosure-mounted.jpg"),
    Entry("Enclosure (Antenna on Left-Data on Right).jpg",               "enclosure-cables.jpg"),
    Entry("Magnets on back of enclosure.jpg",                            "enclosure-magnets.jpg"),
    Entry("casestudy/pizero-enclosure.jpeg",                             "enclosure-outdoor-box.jpg"),
    Entry("Battery To USB Power Supply.jpg",                             "battery-to-usb-supply.jpg"),
    Entry("Antenna.jpg",                                                 "external-antenna.jpg"),
    Entry("casestudy/tplink-repeater.jpeg",                              "wifi-repeater.jpg"),
    # fmt: on
)


# =============================================================================
# Helpers
# =============================================================================

def load_font(size: int) -> ImageFont.ImageFont:
    """Return a bold TrueType font if one is installed, else Pillow's default."""
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    LOGGER.warning("no bold TrueType font found; using Pillow's default font")
    return ImageFont.load_default(size)


def resized(image: Image.Image) -> Image.Image:
    """Return `image` scaled so its longest edge is at most MAX_EDGE_PX."""
    if max(image.size) <= MAX_EDGE_PX:
        return image
    copy = image.copy()
    copy.thumbnail((MAX_EDGE_PX, MAX_EDGE_PX), Image.Resampling.LANCZOS)
    return copy


def add_banner(image: Image.Image, note: str) -> Image.Image:
    """Return `image` with `note` in a dark strip added below it.

    The strip extends the canvas rather than covering the picture, so
    diagrams keep every label readable.
    """
    base      = image.convert("RGB")
    font_size = max(MIN_FONT_PX, int(base.width * TEXT_SCALE))
    font      = load_font(font_size)
    lines     = textwrap.wrap(note, width=WRAP_CHARS)
    padding   = font_size // 2
    line_h    = int(font_size * 1.3)
    banner_h  = padding * 2 + line_h * len(lines)

    canvas = Image.new("RGB", (base.width, base.height + banner_h), BANNER_RGB)
    canvas.paste(base, (0, 0))
    draw = ImageDraw.Draw(canvas)
    for index, line in enumerate(lines):
        draw.text((padding, base.height + padding + index * line_h), line, font=font, fill=(255, 255, 255))
    return canvas


def build(entry: Entry) -> None:
    """Write one manifest entry to OUTPUT_DIR."""
    source = SOURCE_DIR / entry.source
    target = OUTPUT_DIR / entry.output

    with Image.open(source) as original:
        image = resized(ImageOps.exif_transpose(original))
        if entry.note:
            image = add_banner(image, entry.note)

        if target.suffix.lower() in (".jpg", ".jpeg"):
            image.convert("RGB").save(target, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        else:
            image.save(target, "PNG", optimize=True)
    LOGGER.info("wrote %s%s", target.relative_to(REPO_ROOT), " (annotated)" if entry.note else "")


def problems() -> list[str]:
    """Return everything --check would fail on."""
    found    = []
    expected = {entry.output for entry in MANIFEST}
    for entry in MANIFEST:
        if not (SOURCE_DIR / entry.source).exists():
            found.append(f"upstream image missing: Diagrams/{entry.source}")
        if not (OUTPUT_DIR / entry.output).exists():
            found.append(f"not built: {entry.output}")
    if OUTPUT_DIR.exists():
        for stray in sorted(p.name for p in OUTPUT_DIR.iterdir() if p.is_file() and p.name not in expected):
            found.append(f"not in manifest: {stray}")
    return found


# =============================================================================
# Entry Point
# =============================================================================

def main() -> int:
    """Build the documentation images, or with --check verify them."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="verify outputs; write nothing")
    arguments = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if arguments.check:
        issues = problems()
        for issue in issues:
            LOGGER.error(issue)
        return 1 if issues else 0

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for entry in MANIFEST:
        build(entry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
