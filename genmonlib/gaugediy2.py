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

import time, sys, os, math
import smbus

# Adds higher directory to python modules path. (for when this module is used by DIY2TankSensorCalibrate.py)
sys.path.append(os.path.dirname(sys.path[0]))  

try:
    from genmonlib.myconfig import MyConfig

except Exception as e1:
    print("\n\nThis program (gaugediy2.py) requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)
   
class GaugeDIY2():

    RESET_ADDRESS = 0b0000000
    RESET_COMMAND = 0b00000110
    POINTER_CONVERSION = 0b0
    POINTER_CONFIGURATION = 0b1

    MAX_AP_TABLE = 10      #Maximum number of entries in angle vs percentage table
    ANG_PCT_PNT_ = "ang_pct_pnt_"  #config keyword for angle/percentage table

    ap_table = []

    def __init__(self, config):
        #read in parameters from config file
        self.PollTime = config.ReadValue('poll_frequency', return_type = float, default = 60)

        self.i2c_channel = config.ReadValue('i2c_channel', return_type = int, default = 1) 
        assert self.i2c_channel in [1,2], "'i2c_channel' must be 1 or 2"

        self.i2c_address = config.ReadValue('i2c_address', return_type = int, default = 72)  # 0x48

        self.adc_COS_inp = config.ReadValue('adc_COS_inp', return_type = int, default = 0)
        assert  self.adc_COS_inp in [0,1,2,3], "'adc_COS_inp' must be 0,1,2, or 3" 

        self.adc_SIN_inp = config.ReadValue('adc_SIN_inp', return_type = int, default = 1)
        assert self.adc_SIN_inp in [0,1,2,3], "'adc_SIN_inp' must be 0,1,2, or 3" 

        self.adc_VDD_inp = config.ReadValue('adc_VDD_inp', return_type = int, default = None)
        assert self.adc_VDD_inp in [0,1,2,3,None], "'adc_VDD_inp' must be 0,1,2, or 3"

        self.ap_table = []
        for i in range(1, self.MAX_AP_TABLE+1):
            ap = config.ReadValue(f"{self.ANG_PCT_PNT_}{i}")
            if ap != None:
                apl = ap.split(",")
                try:
                    p = float(apl[1])
                    assert p >= 0.0 and p <= 100.0, f"{self.ANG_PCT_PNT_}{i} percent ({p}) must be between 0 and 100"
                    self.ap_table.append((float(apl[0]), p))
                except:
                    print(f"Invalid value in config file '{config.FileName}', line for: {self.ANG_PCT_PNT_}{i} {ap}")

        if len(self.ap_table) > 1: self.ap_table.sort(key = lambda x: x[1])
 
# ---------- GaugeDIY2::InitADC--------------------------------------
    def InitADC(self):
        err_msg = ""
        try:
            self.voltage_factor = 4.096 / 32767.0 #this if for gain = 1 

            # I2C channel, default is 1 which is connected to the GPIO SDA/SCL pins
            self.I2Cbus = smbus.SMBus(self.i2c_channel)

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
            err_msg += "Error calling InitADC: " + str(e1) + "\n"
            print(err_msg)

        if len(self.ap_table) < 2:
            err_msg += f"{self.ANG_PCT_PNT_}x table needs at least 2 entries, only {len(self.ap_table)} found"

        self.init_OK = err_msg == ""

        return err_msg

# ---------- GaugeDIY2::_read_voltage--------------------------------------
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

# ---------- GaugeDIY2::read_gauge_angle--------------------------------------
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

# ---------- GaugeDIY2::GetGaugeData--------------------------------------
    def GetGaugeData(self):
        try:
            return self.convert_angle_to_percent(self.read_gauge_angle())
        except:
            return None

# ---------- GaugeDIY2::convert_angle_to_percent--------------------------------------
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

# ---------- GaugeDIY2::GetAvgGaugeAngle--------------------------------------
    def GetAvgGaugeAngle(self, average_n = 10, secs = 1.0, show_status = False):
        """Get 'average_n' readings in 'secs' seconds and return average"""

        #Note: show_status is True when called from DIY2TankSensorCalibrate.py
        if show_status: print("Reading sensor", end ="", flush = True)

        a = 0.0
        for i in range(average_n):
            a += self.read_gauge_angle()
            if show_status: print(".",end = "", flush = True)
            time.sleep(secs / average_n)

        if show_status: print()
    
        # round to nearest 0.2%
        return round(a/average_n*5.0,0) / 5.0

#--End class GaugeDIY2() ---------------------------------------------------------------------------------------'
