#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mymopeka.py
# PURPOSE: wrapper using bleson Bluetooth LE lib to read mopeka pro sensors
#
#  AUTHOR: Jason G Yates
#    DATE: 5-Dec-2023
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import sys
try:
    from genmonlib.mysupport import MySupport
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)
try:
    from enum import Enum
    from typing import Optional
    from bleson import get_provider, BDAddress
    from bleson.core.hci.type_converters import rssi_from_byte
    from bleson.core.hci.constants import GAP_MFG_DATA, GAP_NAME_COMPLETE

except Exception as e1:
    print("The required library bleson is not installed.")
    sys.exit(2)

# derived from https://github.com/spbrogan/mopeka_pro_check (abandond project)

# converting sensor value to height - contact Mopeka for other fluids/gases
MOPEKA_TANK_LEVEL_COEFFICIENTS_PROPANE = (0.573045, -0.002822, -0.00000535)

MOPEKA_MANUFACTURE_ID = 0x0059

class ScanningMode(Enum):
  FILTERED = 0      # look for sensors based on address and collect their data
  DISCOVERY = 1     # look for sensors that have the sync button pressed

class NoGapDataException(Exception):
    """ Special subclass to gracefully handle zero length GAP
    caller should catch these exception types specifically
    """
    pass

# ------------ MopekaAdvertisement class ---------------------------------------
class MopekaAdvertisement(MySupport):
    """ init from ble advertising data

        preamble: 3
        Access Address: 6
        GAP Packet: N
        GAP Packet[1]: N
        GAP_Packet[2]: N

        GAP Packet:
            length: 1 (length of packet not including the length byte)
            type: 1
            Payload: N
        """
    rssi: int
    name: Optional[str]
    mac: BDAddress

    # Private Members
    _raw_mfg_data: bytes
    def __init__(self, 
                 data: bytes, 
                 debug = None,
                 log = None,
                 console = None):
        
        try:
            self.debug = debug 
            self.log = log 
            self.console = console
            self.rssi = rssi_from_byte(data[-1])
            self.mac = BDAddress(data[3:9])
            self.name = None
            self._raw_mfg_data = None
            self.HardwareId = None

            self.HardwareIDs =  {
                0x03 : "Pro Check, Bottom-up propane sensor",
                0x04 : "Pro-200, top down BLE sensor, wired power",
                0x05 : "Pro Check H20, bottom-up water sensor",
                0x08 : "PRO+ Bottom-up Boosted BLE sensor, all commodities",
                0x09 : "PRO+ Bottom-up BLE+Cellular Sensor, all commodities",
                0x0A : "Top-down Boosted BLE sensor",
                0x0B : "Top-down BLE+Cellular Sensor",
                0x0C : "Pro Universal Sensor, bottom up, all commodities"
            }
            gap_data = data[10:-1]  # trim the data to just the ad data
            offset = 0
        except Exception as e1:
            self.LogErrorLine("Error in MopekaAdvertisement: " + str(e1))
            raise Exception("Invalid Sensor Data")

        # parse the GAP reports in a loop
        while offset < len(gap_data):
            length = gap_data[offset]
            # process gap data starting with type byte (first byte after size)
            self._process_gap(gap_data[offset + 1 : offset + 1 + length])
            offset += 1 + length

        if len(gap_data) < 1:
            # catch packets that have no GAP data as
            # the mopeka sensor does send these and they
            # should not be considered an error.
            raise NoGapDataException("No GAP data")

        if self._raw_mfg_data is None:
            # Make sure we found the required MFG_DATA for Mopeka Sensor
            raise Exception("Incomplete Sensor Data")

        self.LogDebug("data: " + str(list(map(hex, data))))
        self.LogDebug("Sensor Type: " + self.HardwareIDs.get(self.HardwareId, "Unknown"))
        self.LogDebug("Battery Volts: " + str(self.BatteryVoltage) + " V")
        self.LogDebug("Battery Percent: " + str(self.BatteryPercent) + "%")
        self.LogDebug("Temp: " + str(self.TemperatureInFahrenheit) + " F")
        self.LogDebug("Reading MM: " + str(self.TankLevelInMM) + " mm")
        self.LogDebug("Reading inches: " + str(self.TankLevelInInches) + " inches")
        self.LogDebug("Reading Quality: " + str(self.ReadingQualityStars))

    def _process_gap(self, data: bytes) -> None:
        """ Process supported BLE GAP reports.

        data should be buffer starting with type and have length matching
        the report length.
        """

        if data[0] == GAP_MFG_DATA:
            self._process_gap_mfg_data(data)

        elif data[0] == GAP_NAME_COMPLETE:
            self._process_gap_name_complete(data)

        else:
            self.LogDebug(
                "Unsupported GAP report type 0x%X on sensor %s"
                % (data[0], str(self.mac))
            )

    def _process_gap_name_complete(self, data:bytes) -> None:
        """ process GAP data of type GAP_NAME_COMPLETE """
        self.name = data[1:].decode("ascii")

    def _process_gap_mfg_data(self, data:bytes) ->None:
        """ process GAP data of type GAP_MFG_DATA

        data should be buffer in format defined by Mopeka
        """

        MfgDataLength = len(data)
        if MfgDataLength != 13:
            raise Exception(f"Unsupported Data Length (0x{MfgDataLength:X})")

        self.ManufacturerId = data[1] + (data[2] << 8)
        if self.ManufacturerId != MOPEKA_MANUFACTURE_ID:
            raise Exception(
                f"Advertising Data has Unsupported Manufacturer ID 0x{self.ManufacturerId}"
            )

        self.HardwareId = (data[3])

        if not self.HardwareId in self.HardwareIDs.keys():
            raise Exception(
                f"Advertising Data has Unsupported Hardware ID {self.HardwareId}"
            )

        self._raw_battery = data[4] & 0x7F

        self.SyncButtonPressed = bool(data[5] & 0x80 > 0)
        """ True if Sync Button is currently pressed """

        self._raw_temp = data[5] & 0x7F
        self._raw_tank_level = ((int(data[7]) << 8) + data[6]) & 0x3FFF

        self.ReadingQualityStars = data[7] >> 6
        """ Confidence or Quality of the reading on a scale of 0-3.  Higher is more confident """

        self._raw_x_accel = data[11]
        self._raw_y_accel = data[12]

        # Set raw data for debug late.  Do it last as it can also be used
        # as successful parsing indicator
        self._raw_mfg_data = data


    @property
    def BatteryVoltage(self) -> float:
        """Battery reading in volts"""
        return self._raw_battery / 32.0

    @property
    def BatteryPercent(self) -> float:
        """Battery Percentage based on 3 volt CR2032 battery"""
        percent = ((self.BatteryVoltage - 2.2) / 0.65) * 100
        if percent > 100.0:
            return 100.0
        if percent < 0.0:
            return 0.0
        return round(percent, 1)

    @property
    def TemperatureInCelsius(self) -> int:
        """Temperature in Celsius

        Note: This temperature has not been characterized against ambient temperature
        """
        return self._raw_temp - 40

    @property
    def TemperatureInFahrenheit(self) -> float:
        """Temperature in Fahrenheit

        Note: This temperature has not been characterized against ambient temperature
        """
        return ((self.TemperatureInCelsius * 9) / 5) + 32

    @property
    def TankLevelInMM(self) -> int:
        """ The tank level/depth in mm for propane gas"""
        return int(
            self._raw_tank_level
            * (
                MOPEKA_TANK_LEVEL_COEFFICIENTS_PROPANE[0]
                + (MOPEKA_TANK_LEVEL_COEFFICIENTS_PROPANE[1] * self._raw_temp)
                + (
                    MOPEKA_TANK_LEVEL_COEFFICIENTS_PROPANE[2]
                    * self._raw_temp
                    * self._raw_temp
                )
            )
        )

    @property
    def TankLevelInInches(self) -> float:
        """ The tank level/depth in inches"""
        return round(self.TankLevelInMM / 25.4, 2)

    def __str__(self) -> str:
        return ("MopekaAdvertisement -  " +
                f"RSSI: {self.rssi}dBm  " +
                f"Battery: {self.BatteryVoltage} volts {self.BatteryPercent}%  " +
                f"Button Pressed: {self.SyncButtonPressed}  " +
                f"Temperature {self.TemperatureInCelsius}C {self.TemperatureInFahrenheit}F  " +
                f"Confidence Stars {self.ReadingQualityStars}  " +
                f"Fluid Height {self.TankLevelInMM} mm")

    def Dump(self):
        """ Helper routine that prints ad data plus all mfg data"""
        self.console(self)
        self.console("MfgData: ", end="")
        for a in self._raw_mfg_data:
            self.console("0x%02X" % a, end="  ")
        self.console("\n")


# ------------ MopekaBTSensor class ---------------------------------------------
class MopekaBTSensor(MySupport):
    def __init__(self,
                 address,
                 log = None,
                 console = None,
                 debug = None):

        self.log = log 
        self.console = console
        self.debug = debug
        self.address = address
        self.bd_address = BDAddress(address)
        self.last_reading = None
        self.num_readings = 0

    # ------------ MopekaBTSensor:AddReading -----------------------------------
    def AddReading(self, reading_data):

        self.last_reading = reading_data
        self.num_readings += 1

# ------------ MopekaBT class --------------------------------------------------
class MopekaBT(MySupport):
    def __init__(self, 
                 log = None,
                 console = None,
                 debug = None,
                 mode = ScanningMode.FILTERED,
                 hci_index = 0,
                 min_reading_quality = 0):

        self.log = log 
        self.console = console
        self.debug = debug
        self.sensors = dict()               # filtered mode
        self.discovered_sensors = dict()    # discovery mode
        self.mode = mode
        self.scan_active = False
        self.hci_index = hci_index  # select BT controller if multiple controlelrs in system
        self.controller = None
        self.ignored_advertisments = 0
        self.processed_advertisments = 0
        self.rejected_advertisments = 0
        self.skipped_advertisments = 0
        self.zero_lenght_advertisments = 0
        self.min_reading_quality = min_reading_quality
        if self.min_reading_quality > 3:
            self.min_reading_quality = 3
        if self.min_reading_quality < 0:
            self.min_reading_quality = 0
    # ------------ MopekaBT:ModeType -------------------------------------------
    @property
    def ModeType(self):
        if self.mode == ScanningMode.FILTERED:
            return "Filtered"
        elif self.mode == ScanningMode.DISCOVERY:
            return "Discovery"
        else:
            return "Unknown"
    
    # ------------ MopekaBT:LogStats -------------------------------------------
    def LogStats(self):

        self.LogDebug("Processed Ads:" + str(self.processed_advertisments))
        self.LogDebug("Rejected Ads:" + str(self.rejected_advertisments))
        self.LogDebug("Skipped Ads:" + str(self.skipped_advertisments))
        self.LogDebug("Zero Length Ads:" + str(self.zero_lenght_advertisments))
        self.LogDebug("Ignored Ads:" + str(self.ignored_advertisments))

    # ------------ MopekaBT:IncommingPacketCallback ----------------------------
    def IncommingPacketCallback(self, hci_packet):
        try:
            if self.mode == ScanningMode.FILTERED:
                # Filtered Mode is scanning and only processing known sensors
                bd_address = BDAddress(hci_packet.data[3:9])
                sensor = self.sensors.get(bd_address, None)
                if not sensor == None:
                    try:
                        ma = MopekaAdvertisement(hci_packet.data, log = self.log, debug = self.debug, console = self.console)
                        if ma._raw_mfg_data != None:
                            if ma.ReadingQualityStars  >= self.min_reading_quality:    # reject zero quality
                                sensor.AddReading(ma)
                                self.processed_advertisments += 1
                            else:
                                self.rejected_advertisments +=1
                            
                        else:
                            self.skipped_advertisments += 1

                    except NoGapDataException:
                        # This is not an error.  The sensor sends ads with zero data, ignore
                        self.zero_lenght_advertisments += 1

                    except Exception as e:
                        self.LogErrorLine("Failed to process advertisement from defined sensor.  Exception: %s" % e)
                        self.ignored_advertisments += 1
                else:
                    self.ignored_advertisments += 1

            elif self.mode == ScanningMode.DISCOVERY:
                # looking for Mopeka Sensors if their sync button is pressed
                bd_address = BDAddress(hci_packet.data[3:9])
                sensor = self.sensors.get(bd_address, None)
                if sensor == None:
                    # packet from untracked device
                    try:
                        ma = MopekaAdvertisement(hci_packet.data, log = self.log, debug = self.debug, console = self.console)
                        self.processed_advertisments += 1

                        if(ma.SyncButtonPressed):
                            # Only sensors with button pressed should be discovered
                            # Recommendation by Mopeka
                            sensor = MopekaBTSensor(bd_address.address, log = self.log, debug = self.debug, console = self.console)
                            sensor.AddReading(ma)
                            self.discovered_sensors[bd_address] = sensor

                    except:
                        self.ignored_advertisments += 1
                        # Not a Mopeka Sensor or supported sensor
        except Exception as e1:
            self.LogErrorLine("Error in MopekaBT:IncommingPacketCallback: " + str(e1))

    # ------------ MopekaBT:Start ----------------------------------------------
    def Start(self):

        try:
            if self.scan_active:
                self.LogDebug("MopekaBT:Start: Scan already started")
                return

            if self.mode == ScanningMode.FILTERED and len(self.sensors) == 0:
                return

            # if adapter is none do initial setup before starting.
            if self.controller == None:
                self.controller = get_provider().get_adapter(self.hci_index)
                self.controller._handle_meta_event = self.IncommingPacketCallback
            
            self.scan_active = True
            self.controller.start_scanning()
            self.LogDebug("Start Scan " + self.ModeType)
        except Exception as e1:
            self.LogErrorLine("Error in MopekaBT:Start: " + str(e1))
    
    # ------------ MopekaBT:Stop -----------------------------------------------
    def Stop(self):

        try:
            if not self.scan_active:
                self.LogDebug("MopekaBT:Stop: Scan already stopped")
                return
            
            if self.scan_active:
                self.controller.stop_scanning()

            self.scan_active = False
            self.LogDebug("Stop Scan " + self.ModeType)
        except Exception as e1:
            self.LogErrorLine("Error in MopekaBT:Stop: " + str(e1))

    # ------------ MopekaBT:AddSensor ------------------------------------------
    def AddSensor(self, sensor:MopekaBTSensor):

        try:
            self.LogDebug("Adding sensor:" + str(sensor.address))
            self.sensors[sensor.bd_address] = sensor
            return True
        except Exception as e1:
            self.LogErrorLine("Error in MopekaBT:AddSensor: " + str(sensor.address) + ": " + str(e1))
            return False

    # ------------ MopekaBT:Close ----------------------------------------------
    def Close(self):

        if self.scan_active:
            self.Stop()
        self.LogDebug("Closing MopekaBT")
