#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: gaugediy2.py
# PURPOSE: Handles reading propane tank dial gauge using the Infinieon TLE5501 E0001 TMR-based
#          angle sensor used in gentankdiy2.py and the ADS1015 12bit A/D converter or
#          ADS1115 16bit A/D converter
#
#  AUTHOR: Curtis Case
#    DATE: 19-Oct-2020
# Free software. Use at your own risk.
# MODIFICATIONS:
#------------------------------------------------------------

from __future__ import print_function

import time, sys, os, math
import smbus

from genmonlib.myconfig import MyConfig
from genmonlib.mysupport import MySupport

class GaugeDIY(MySupport):
    # ---------- GaugeDIY::__init__---------------------------------------------
    def __init__(self, config, log = None, console = None):
        super(GaugeDIY, self).__init__()

        self.config = config
        self.log = log
        self.consle = console
        #read in parameters from config file

        self.debug = self.config.ReadValue('debug', return_type = bool, default = False)

        self.PollTime = self.config.ReadValue('poll_frequency', return_type = float, default = 60)

        self.i2c_channel = self.config.ReadValue('i2c_channel', return_type = int, default = 1)
        assert self.i2c_channel in [1,2], "'i2c_channel' must be 1 or 2"

        self.i2c_address = self.config.ReadValue('i2c_address', return_type = int, default = 72)  # 0x48

    # ---------- GaugeDIY::InitADC----------------------------------------------
    def InitADC(self):

        return True
    # ---------- GaugeDIY::GetGaugeData----------------------------------------
    def GetGaugeData(self):
        return 0.0
    # ---------- GaugeDIY::Close------------------------------------------------
    def Close(self):
        pass
# ---------- GaugeDIY1:---------------------------------------------------------
class GaugeDIY1(GaugeDIY):
    # The device is the ADS1115 I2C ADC
    # reference python http://www.smartypies.com/projects/ads1115-with-raspberrypi-and-python/ads1115runner/
    RESET_ADDRESS = 0b0000000
    RESET_COMMAND = 0b00000110
    POINTER_CONVERSION = 0x0
    POINTER_CONFIGURATION = 0x1
    POINTER_LOW_THRESHOLD = 0x2
    POINTER_HIGH_THRESHOLD = 0x3
    # ---------- GaugeDIY::__init__---------------------------------------------
    def __init__(self, config, log = None, console = None):

        super(GaugeDIY1, self).__init__(config, log = log, console = console)

        self.mv_per_step = self.config.ReadValue('mv_per_step', return_type = int, default = 125)
        self.Multiplier = self.config.ReadValue('volts_to_percent_multiplier', return_type = float, default = 20.0)

    # ---------- GaugeDIY::InitADC----------------------------------------------
    def InitADC(self):
        try:

            # I2C channel 1 is connected to the GPIO pins
            self.I2Cbus = smbus.SMBus(self.i2c_channel)

            # Reset ADC
            self.I2Cbus.write_byte(self.RESET_ADDRESS, self.RESET_COMMAND)

            # set config register  and start conversion
            # ANC1 and GND, 4.096v, 128s/s
            # Customized - Port A0 and 4.096 V input
            # 0b11000011; # bit 15-8  = 0xC3
            # bit 15 flag bit for single shot
            # Bits 14-12 input selection:
            # 100 ANC0; 101 ANC1; 110 ANC2; 111 ANC3
            # Bits 11-9 Amp gain. Default to 010 here 001 P19
            # Bit 8 Operational mode of the ADS1115.
            # 0 : Continuous conversion mode
            # 1 : Power-down single-shot mode (default)
            CONFIG_VALUE_1 = 0xC3
            # bits 7-0  0b10000101 = 0x85
            # Bits 7-5 data rate default to 100 for 128SPS
            # Bits 4-0  comparator functions see spec sheet.
            CONFIG_VALUE_2 = 0x85
            self.I2Cbus.write_i2c_block_data(self.i2c_address, self.POINTER_CONFIGURATION, [CONFIG_VALUE_1,CONFIG_VALUE_2] )

            self.LogDebug("I2C Init complete: success")

        except Exception as e1:
            self.LogErrorLine("Error calling InitADC: " + str(e1))
            return False

        return True
    # ---------- GaugeDIY::GetGaugeData----------------------------------------
    def GetGaugeData(self):
        try:

            val = self.I2Cbus.read_i2c_block_data(self.i2c_address, self.POINTER_CONVERSION, 2)

            self.LogDebug(str(val))
            # convert display results
            reading = val[0] << 8 | val[1]

            if (reading < 0):
                reading = 0

            #reading = self.I2Cbus.read_word_data(self.i2c_address, self.i2c_channel)
            volts = round(float(reading * (float(self.mv_per_step) / 1000000.0)),2)
            gauge_data = float(self.Multiplier) * volts
            self.LogDebug("Reading Gauge Data: %4.2f%%" % gauge_data)
            return gauge_data

        except Exception as e1:
            self.LogErrorLine("Error calling  GetGaugeData: " + str(e1))
            return 0.0
    # ---------- GaugeDIY::Close------------------------------------------------
    def Close(self):
        try:
            self.I2Cbus.close()
        except Exception as e1:
            self.LogErrorLine("Error in GagueDIY1:Close: " + str(e1))

# ---------- GaugeDIY2:----------------------------------------------------------
class GaugeDIY2(GaugeDIY):

    RESET_ADDRESS = 0b0000000
    RESET_COMMAND = 0b00000110
    POINTER_CONVERSION = 0b0
    POINTER_CONFIGURATION = 0b1

    MAX_AP_TABLE = 10      #Maximum number of entries in angle vs percentage table
    ANG_PCT_PNT_ = "ang_pct_pnt_"  #config keyword for angle/percentage table

    ap_table = []
    # ---------- GaugeDIY2::__init__--------------------------------------------
    def __init__(self, config, log = None, console = None):

        super(GaugeDIY2, self).__init__(config, log = log, console = console)

        self.adc_COS_inp = self.config.ReadValue('adc_COS_inp', return_type = int, default = 0)
        assert  self.adc_COS_inp in [0,1,2,3], "'adc_COS_inp' must be 0,1,2, or 3"

        self.adc_SIN_inp = self.config.ReadValue('adc_SIN_inp', return_type = int, default = 1)
        assert self.adc_SIN_inp in [0,1,2,3], "'adc_SIN_inp' must be 0,1,2, or 3"

        self.adc_VDD_inp = self.config.ReadValue('adc_VDD_inp', return_type = int, default = None)
        assert self.adc_VDD_inp in [0,1,2,3,None], "'adc_VDD_inp' must be 0,1,2, or 3"

        self.init_OK = False

        self.ap_table = []
        for i in range(1, self.MAX_AP_TABLE+1):
            ap = self.config.ReadValue("{0}{1}".format(self.ANG_PCT_PNT_, i))
            if ap != None:
                apl = ap.split(",")
                try:
                    p = float(apl[1])
                    assert p >= 0.0 and p <= 100.0, "{0}{1} percent ({2}) must be between 0 and 100".format(self.ANG_PCT_PNT_, i, p)
                    self.ap_table.append((float(apl[0]), p))
                except Exception as e1:
                    self.LogConsole("Invalid value in config file '{0}', line for: {1}{2} {3}".format(self.configFileName, self.ANG_PCT_PNT_, i, ap))
                    self.LogErrorLine("Error in GaugeDIY2:Init " + str(e1))

        if len(self.ap_table) > 1: self.ap_table.sort(key = lambda x: x[1])

    # ---------- GaugeDIY2::InitADC---------------------------------------------
    def InitADC(self):
        err_msg = ""
        try:
            self.voltage_factor = 4.096 / 32767.0 #this if for gain = 1

            # I2C channel, default is 1 which is connected to the GPIO SDA/SCL pins
            try:
                self.I2Cbus = smbus.SMBus(self.i2c_channel)
            except Exception as e1:
                self.LogErrorLine("Unable to open SMBus device for I2C channel " + str(self.i2c_channel))
                return False

            # Reset ADC
            self.I2Cbus.write_byte(self.RESET_ADDRESS, self.RESET_COMMAND)

            #See TI doc 'ads1015.pdf' page 24 for details-------

            #bit 15 = 1 -> Start a single conversion
            #bit 14:12 -> Input multiplexer configuration (set in read_voltage = pin + 4)
            #bit 11:9 = 001 -> Programmable gain amplifier = 1 for FSR = +/-4.096V
            #bit 8 = 1 -> Device operating Mode = Single-shot mode
            #bit 7:5 = 100 -> Data rate, not used in Single-shot
            #bit 4 = 0 -> Comparator mode (not used)
            #bit 3 = 0 -> Comparator polarity  (not used)
            #bit 2 = 0 -> Latching comparator  (not used)
            #bit 1:0 = 11 -> Comparator queue and disable = disable
            self.CONFIG_VALUE = 0b1000001110000011

            if self.adc_VDD_inp == None:
                vdd = 3.3
            else:
                vdd = self._read_voltage(self.adc_VDD_inp)

                #If VDD not between 3 and 5.5 then assume even though a channel number
                #was given, it is either not connected or not connected to VDD
                if vdd < 3.0:
                    vdd = 3.3
                elif vdd > 5.5:
                    vdd = 5.0

            self.vdd2 = vdd / 2.0

        except Exception as e1:
            self.LogConsole("Error in GaugeDIY2:InitADC " + str(e1))
            self.LogErrorLine("Error in GaugeDIY2:InitADC " + str(e1))
            return False

        if len(self.ap_table) < 2:
            err_msg += "{0}x table needs at least 2 entries, only {1} found".format(self.ANG_PCT_PNT_, len(self.ap_table))
            self.LogConsole(err_msg)
            return False

        self.init_OK = True

        return True

# ---------- GaugeDIY2::_read_voltage-------------------------------------------
    def _read_voltage(self, pin):
        #Start conversion for the selected input (pin)
        self.I2Cbus.write_word_data(self.i2c_address, self.POINTER_CONFIGURATION, self.CONFIG_VALUE | ((pin + 0x04) << 4))

        # Wait for conversion to complete
        while not  self.I2Cbus.read_word_data(self.i2c_address, self.POINTER_CONFIGURATION) & 0x8000:
           pass

        #Get 2 byte value
        val = self.I2Cbus.read_i2c_block_data(self.i2c_address, self.POINTER_CONVERSION, 2)

        #Convert 2 bytes to voltage, note: 4 LSB's on ADS1015 will be 0's
        return (val[0] << 8 | val[1])  * self.voltage_factor

    # ---------- GaugeDIY2::read_gauge_angle------------------------------------
    def read_gauge_angle(self):

        try:
            assert self.init_OK

            # Get sin and cos values, subtracting out the offset
            COS_P = self._read_voltage(self.adc_COS_inp) - self.vdd2
            SIN_P = self._read_voltage(self.adc_SIN_inp) - self.vdd2

            # Calculate dial pointer angle from sin and cos
            return math.degrees(math.atan2(COS_P, SIN_P))

        except Exception as e1:
            return 0.0

    # ---------- GaugeDIY2::GetGaugeData----------------------------------------
    def GetGaugeData(self):
        try:
            return self.convert_angle_to_percent(self.read_gauge_angle())
        except:
            return 0.0

    # ---------- GaugeDIY2::convert_angle_to_percent----------------------------
    def convert_angle_to_percent(self, ain):

        # Determine percentage reading from dial pointer angle
        if self.ap_table == None or len(self.ap_table) < 2: return -1.0

        apt = list(self.ap_table)

        if apt[0][0] > apt[-1][0]: apt.reverse()

        ts = -.01 if apt [0][1] > apt[-1][1] else 0.1

        if ain < apt[0][0]:

            # value less than first angle in our table
            return apt[0][1] - ts

        elif ain > apt[-1][0]:

            # value greater than last angle in our table
            return apt[-1][1] + ts
        else:

            # Angle is in our table, find bounding elements and do
            # linear interpolation between them to determine percentage
            for i in range(1,len(apt)):
                if ain < apt[i][0]:

                    # round to nearest 0.2%
                    return round((apt[i-1][1]+(ain-apt[i-1][0])*((apt[i][1]-apt[i-1][1])/(apt[i][0]-apt[i-1][0])))*5.0, 0)  / 5.0

    # ---------- GaugeDIY2::GetAvgGaugeAngle------------------------------------
    def GetAvgGaugeAngle(self, average_n = 10, secs = 1.0, show_status = False):
        """Get 'average_n' readings in 'secs' seconds and return average"""

        #Note: show_status is True when called from DIY2TankSensorCalibrate.py
        if show_status:
            self.LogConsole("Reading sensor", end ="")
            sys.stdout.flush()

        a = 0.0
        for i in range(average_n):
            a += self.read_gauge_angle()
            if show_status: self.LogConsole(".",end = "")
            sys.stdout.flush()
            time.sleep(secs / average_n)

        if show_status: self.LogConsole()

        # round to nearest 0.2%
        return round(a/average_n*5.0,0) / 5.0

    # ---------- GaugeDIY::Close------------------------------------------------
    def Close(self):
        try:
            self.I2Cbus.close()
        except Exception as e1:
            self.LogErrorLine("Error in GagueDIY2:Close: " + str(e1))
