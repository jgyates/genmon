#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: DIY2TankSensorCalibrate.py
# PURPOSE: Get calibration values for the Infinieon TLE5501 E0001 TMR-based angle sensor
#          used in gentankdiy2.py and write them in gentankdiy2.conf file.
#
#  AUTHOR: Curtis Case @curtis1757
#    DATE: 10-Oct-2020
# Free software. Use at your own risk.
# MODIFICATIONS:
#------------------------------------------------------------
import time, sys, os, getopt, math

# This program assumes the directory genmonlib is one level higher
sys.path.append(os.path.dirname(sys.path[0]))   # Adds higher directory to python modules path.

try:
    from genmonlib.myconfig import MyConfig
    from genmonlib.gaugediy import GaugeDIY2
    from genmonlib.mylog import SetupLogger
    from genmonlib.mycommon import MyCommon

except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)

#---------------------input_float-----------------------------------------------
def input_float(prompt, ndec = 2):
    """Get a float number from the user"""

    while True:
        try:
            s = input(prompt)
            v = float(s)

            return round(v, ndec)
        except Exception as e1:
            if s == "": return None
            print("{0}, try again".format(e1))

#---------------------check_ap_table--------------------------------------------
def check_ap_table():
    """Checks to mke sure the angle-percentage table is linear"""

    if gauge.ap_table != None and len(gauge.ap_table) > 2:
        increasing = gauge.ap_table[0][0] < gauge.ap_table[-1][0]
        for i in range(1,len(gauge.ap_table)):
            if (increasing and  gauge.ap_table[i-1][0] < gauge.ap_table[i][0]) or \
               (not increasing and  gauge.ap_table[i-1][0] < gauge.ap_table[i][0]):

                print(("error in calibration table at row {0}, {1:.2f}" +
                      " is {2} than {3:.2f}\n" +
                      "value not added to calibration table.").format(i, gauge.ap_table[i-1][0], 'greater' if increasing else 'less', gauge.ap_table[i][0]))

                guage.ap_table.pop(i)

#---------------------show_ap_table---------------------------------------------
def show_ap_table():
    if gauge.ap_table != None and len(gauge.ap_table) > 0:
        i = 1
        print("{0:>6s}{1:>8s}{2:>8s}".format('Index', 'Angle', 'Percent'))
        for a, p in gauge.ap_table:
            print("{0:6d}{1:8.2f}{2:8.1f}".format(i, a, p))
            i+=1
    else:
        print("calibration table is empty")

#---------------------main------------------------------------------------------
if __name__=='__main__':
    HelpStr = """python DIY2TankSensorCalibrate.py  [OPTIONS] ...

Usage: python DIY2TankSensorCalibrate.py  [OPTION] ...

Gets information to modify 'gentankDIY2.conf' file

Valid [OPTIONS] are:
    -c <config file path>
"""
    try:
        console = SetupLogger("DIY2_console", log_file = "", stream = True)
        opts, args = getopt.getopt(sys.argv[1:],"hc:",["help","config="])

    except getopt.GetoptError:
        print (HelpStr)
        sys.exit(2)

    configfilename = "gentankdiy.conf"
    configfile = os.path.join(MyCommon.DefaultConfPath, configfilename)

    for opt, arg in opts:
        if opt == '-h':
            print (HelpStr)
            sys.exit()
        elif opt in ("-c"):
            configfile = os.path.join(arg, configfilename)


    if not os.path.isfile(configfile):
        console.error("Missing config file: {0}".format(configfile))
        sys.exit(1)

    console.error("Using config file %s" % configfile)

    config = MyConfig(filename = configfile, section = 'gentankdiy')

    gauge = GaugeDIY2(config, console = console, log = console)

    if not gauge.InitADC():
        console.error("Error initializing ADC, exiting")
        exit(2)

    average_n = 10

    while True:
        print("""
Enter command:
1 - Show current calibration table
2 - Clear all entries from calibration table
3 - Enter lowest and highest readings possible
4 - Add new entry(s) to calibration table
5 - Delete entry(s) in calibration table
6 - Save '{configfile}'
7 - Show current dial reading using current calibration table
0 - exit
""")
        c = str(input("Command: ")).strip()

        if c == '1':
            show_ap_table()

        elif c == '2':
            gauge.ap_table.clear()

        elif c == '3':
            p = input_float("Set dial as low as possible and enter the percent value (typically 5%)\n" +
                            "when enter is pressed after the value is entered the dial angle will be read and recorded: ")
            if p != None:
                a = gauge.GetAvgGaugeAngle(average_n, 1.0, True)
                gauge.ap_table = [(a,p)]

                p = input_float("Set dial as high as possible and enter the percent value (typically 100%)\n" +
                                 "when enter is pressed after the value is entered the dial angle will be read and recorded: ")
                if p != None:
                    if p < gauge.ap_table[0][1]:
                        print("Error: the low entry must be less than the high entry, {0:.1f} is not less than {1:.1f}".format(gauge.ap_table[0][1]), p)
                    else:
                        a = gauge.GetAvgGaugeAngle(average_n, 1.0, True)
                        gauge.ap_table.append((a,p))

                        print()
                        show_ap_table()
                        print("Next use option 4 to add calibration points between {0:.1f} and {1:.1f}".format(gauge.ap_table[0][1], gauge.ap_table[1][1]))
                        print("suggested to use major markings on dial, ie 10, 20, 30, 40, 50, 60, 70")

        elif c == '4':
            if gauge.ap_table == None or len(gauge.ap_table) < 2:
                print("must use option 3 first to set lowest and highest dial values")
            else:
                if len(gauge.ap_table) >= gauge.MAX_AP_TABLE:
                    print("already maximum of {0} entries, delete some (5) or all (2)".format(gauge.MAX_AP_TABLE))
                else:
                    while len(gauge.ap_table) < gauge.MAX_AP_TABLE:
                        while True:
                            p = input_float("Set dial to desired value to read the associated angle for\n" +
                                            "(or just 'Return' to stop entering values). When enter is pressed \n" +
                                            "after a value is entered the dial angle will be read and recorded: ")
                            if p == None: break
                            if p < 0.0 or p > 100.0:
                                print("value must be between 0 and 100")
                            else:
                                break

                        if p == None: break

                        a = gauge.GetAvgGaugeAngle(average_n, 1.0, True)
                        gauge.ap_table.append((a,p))

                        gauge.ap_table.sort(key = lambda x: x[1])

                        check_ap_table()

                        print("\nadded angle {0:.2f} to represent dial value {1:.1f}% to calibration table\n".format(a, p))

        elif c == '5':
            show_ap_table()
            if  gauge.ap_table != None and len(gauge.ap_table) > 0:
                while True:
                     i = input_float("Enter Index of entry to be deleted:")
                     if i == None: break
                     if i >= 1 and i <= len(gauge.ap_table):
                        gauge.ap_table.pop(i-1)
                        print("updated calibration table:")
                        show_ap_table()
                     else:
                        print("Index must be from 1 to {0}, try again".format(len(gauge.ap_table)))

        elif c == '6':
            if gauge.ap_table != None:
                if len(gauge.ap_table) < 2:
                    print("must have at least 2 entries in calibration table, file not written")
                else:
                    for i in range(1,gauge.MAX_AP_TABLE+1):
                        config.WriteValue("ang_pct_pnt_{0}".format(i), "", remove = True)

                    i = 1
                    for a, p in gauge.ap_table:
                        config.WriteValue("ang_pct_pnt_{0}".format(i), "{0:8.2f},{1:6.1f}".format(a, p))
                        i += 1

                    print("wrote {0} calibration entries in '{1}'".format(len(gauge.ap_table), configfile))

        elif c == '7':
            a = gauge.read_gauge_angle()
            print("Current dial angle is {0:.2f} degrees which is {1:.1f}%".format(a, gauge.convert_angle_to_percent(a)))

        elif c == '0':
           sys.exit(0)
        else:
            print("unknown command '{0}'".format(c))

    sys.exit(1)
