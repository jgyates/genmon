# genmon-esp32 documentation

Build guide and reference for monitoring a Generac Evolution or Nexus generator with an ESP32.
For an overview, building and flashing the firmware, first-time setup, Home Assistant and the
HTTP API, see the [main README](../README.md).

## Build guide

1. [Hardware](hardware.md): parts list, optional protection, tools
2. [Controllers](controllers.md): identify the controller, find its serial port, power it down safely
3. [Cable](cable.md): connector pinout, reusing the MobileLink harness, building a cable
4. [Wiring](wiring.md): the ESP32 wiring diagram, checking signal levels, DB9 modules
5. [Enclosure, power and Wi-Fi](enclosure.md): mounting, powering from the battery, antennas
6. [First-time setup](../README.md#first-time-setup) and [moving from a Raspberry Pi](../README.md#moving-from-genmon-on-a-raspberry-pi)
7. [Troubleshooting](troubleshooting.md): no data, loopback test, Wi-Fi, Home Assistant

## Images

`images/wiring_esp32.svg` is drawn for this port. Everything in `images/upstream/` comes from
upstream genmon's `Diagrams/` folder, resized for the web by
[`tools/build_doc_images.py`](../tools/build_doc_images.py). Images that show a Raspberry Pi carry
a banner noting that an ESP32 takes its place.

| Image | From upstream | Pi note |
|---|---|---|
| `evolution-controller.jpg` | `Evolution_Controller.jpg` | |
| `nexus-controller.jpg` | `Nexus_Controller.jpg` | |
| `pre-nexus-controller.jpg` | `2008-PreNexusController.jpg` | |
| `powerpact-controller.jpg` | `casestudy/PowerPactController.jpeg` | |
| `nexus-serial-connector.jpg` | `Controller_connection(Nexus).jpg` | |
| `liquid-cooled-controller-back.jpg` | `liquid_cooled_generac_back_of_controller.jpeg` | |
| `controller-power-connector.jpg` | `evo_controller_power.jpg` | |
| `molex-pinout.png` | `Molex_Pinout.png` | |
| `mobilelink-pinout.png` | `casestudy/MLPinout.png` | |
| `mobilelink-cable.jpg` | `casestudy/MLCable.jpeg` | |
| `mobilelink-module.jpg` | `casestudy/MobileLink2G.jpeg` | |
| `repinning-diagram.png` | `casestudy/repinning-cable.png` | ✓ (targets a Pi HAT) |
| `cable-full.jpg` | `Cable (full- Liquid cooled models require longer cable).jpg` | |
| `cable-controller-end.jpg`, `cable-controller-end-2.jpg` | `Cable (End that connecets to Evolution Controller)*.jpg` | |
| `crimping-pins.jpg` | `casestudy/crimppins.jpeg` | |
| `tools.jpg` | `casestudy/Tools.jpeg` | |
| `pi-wiring-schematic.png` | `wiring_schematic.png` | ✓ |
| `pi-cable-connections.jpg` | `Cable_Connections.jpg` | ✓ |
| `example-project.jpg` | `Example_Project.JPG` | ✓ |
| `serial-loopback.jpg` | `serial_loopback.jpeg` | ✓ |
| `pintsize-hat.jpg` | `casestudy/PintSizeMeHat.jpeg` | ✓ |
| `pintsize-hat-pinout.png` | `casestudy/PintSizeMePinout.png` | ✓ |
| `inside-enclosure.jpg` | `Inside enclosure.jpg` | ✓ |
| `enclosure-mounted.jpg` | `Enclosure (1).jpg` | |
| `enclosure-cables.jpg` | `Enclosure (Antenna on Left-Data on Right).jpg` | |
| `enclosure-magnets.jpg` | `Magnets on back of enclosure.jpg` | |
| `enclosure-outdoor-box.jpg` | `casestudy/pizero-enclosure.jpeg` | |
| `battery-to-usb-supply.jpg` | `Battery To USB Power Supply.jpg` | |
| `external-antenna.jpg` | `Antenna.jpg` | |
| `wifi-repeater.jpg` | `casestudy/tplink-repeater.jpeg` | |

Not carried over, because they don't apply to an ESP32 monitoring an Evolution or Nexus
controller: the genmon logos, the Pi web UI screenshot (`Web_UI_Status.png`), H-100 / G-Panel,
MEBAY, PowerZone and RS-485 material, fuel-gauge sensor photos, and the printable enclosure labels
(`enclosure label*.pdf/pptx`, still usable as-is from upstream's `Diagrams/`).

To rebuild the images after an upstream change, from the repository root:

```bash
python esp32/tools/build_doc_images.py
```

`--check` verifies that every listed image is built and that nothing unlisted is in the folder.
Requires Pillow (`esp32/tools/requirements.txt`).

Upstream's [wiki](https://github.com/jgyates/genmon/wiki) is still the reference for
controller-specific background that isn't repeated here.
