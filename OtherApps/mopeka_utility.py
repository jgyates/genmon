#-------------------------------------------------------------------------------
#    FILE: mopekautility.py
# PURPOSE: app for mopeka pro sensor support
#
#  AUTHOR: Jason G Yates
#    DATE: 2-Aug-2022
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import sys, os, signal, time
from subprocess import PIPE, Popen


 # ----------SignalClose--------------------------------------------------------
def SignalClose(signum, frame):

    
    sys.exit(1)

#-------------------------------------------------------------------------------
def CheckServiceOutput(Output):

    try:
        for line in iter(Output.splitlines()):
            if sys.version_info[0] >= 3:
                line = line.decode() 
            if "Loaded:" in line:
                line = line.strip()
                lineitems = line.split(";")
                if len(lineitems) >= 2 and "disabled" in lineitems[1].lower():
                    return True
                else:
                    return False
        return False
    except Exception as e1:
        print("Program Error: (CheckServiceOutput): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)

#-------------------------------------------------------------------------------
def ServiceIsEnabled(servicename):
    try:
        process = Popen(['systemctl', "status" , servicename], stdout=PIPE)
        output, _error = process.communicate()
        rc = process.returncode
        return not CheckServiceOutput(output)

    except Exception as e1:
        print("Program Error (ServiceIsEnabled): " + str(e1) + " " + GetErrorInfo())
        sys.exit(2)


#------------------GetErrorInfo-------------------------------------------------
def GetErrorInfo():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)
#------------------main---------------------------------------------------------
if __name__ == '__main__':

    if os.geteuid() != 0:
        print("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
        sys.exit(2)

    try:
        try: 
            import bleson       # used by mopeka lib
        except Exception as e1:
            print("The requires library bleson is not installed." + str(e1)  + " " + GetErrorInfo())
            print("Install the library with this command: sudo pip3 install mopeka_pro_check")
            print("\n")
            sys.exit(2)
        try:
            from mopeka_pro_check.service import MopekaService, MopekaSensor, GetServiceInstance
        except Exception as e1:
            print("The required library mopeka_pro_check is not installed." + str(e1)  + " " + GetErrorInfo())
            print("Install the library with this command: sudo pip3 install mopeka_pro_check")
            print("\n")
            sys.exit(2)
        
        signal.signal(signal.SIGTERM, SignalClose)
        signal.signal(signal.SIGINT, SignalClose)

        service = GetServiceInstance()
        service.SetHostControllerIndex(0)

        print("\nNOTE: This program will look for Mopeka Pro Sensors. The SYNC button must be pressed and held for the discovery process to work.\n")
        print("Starting Discovery....")
        service.DoSensorDiscovery()
        try:
            service.Start()
        except Exception as e1:
            print("Error starting discovery. Validate that Blootooth is enabled: " + str(e1)  + " " + GetErrorInfo())
            print("\n")
            sys.exit(2)

        time.sleep(5)
        service.Stop()

        print("Discovery Stats %s\n" % str(service.ServiceStats))
        print(f"\n\nFinished Discovery.  Found {len(service.SensorDiscoveredList)} new sensor(s):\n\n")
        
        for sensor in service.SensorDiscoveredList.values():
            print("Sensor Address:  " + str(sensor._mac))
            print("Battery Percentage:  " + str(sensor._last_packet.BatteryPercent) + "%%")
            print("Sensor Temperature:  " + str(sensor._last_packet.TemperatureInCelsius) + " C")
            print("Tank Level Reading:  " + str(sensor._last_packet.TankLevelInMM) + "mm")
            print("\n")

        if len(service.SensorDiscoveredList):
            print("Use the sensor address above as the tank address parameter in the genmon add on settings.\n")
            
    except Exception as e1:
        print("Program Error (main): " + str(e1) + " " + GetErrorInfo())
        print("\n")
        sys.exit(2)
