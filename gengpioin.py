#!/usr/bin/env python
#-------------------------------------------------------------------------------
#    FILE: gengpioin.py
# PURPOSE: genmon.py support program to allow GPIO inputs to control
# remote start, stop snd start/transfer functionality
# status LEDs
#
#  AUTHOR: Jason G Yates
#    DATE: 10-Apr-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------

import datetime, time, sys, signal, os, threading, socket
import atexit, getopt
try:
    from genmonlib.mylog import SetupLogger
    from genmonlib.myconfig import MyConfig
    from genmonlib.myclient import ClientInterface
    from genmonlib.mythread import MyThread
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    print("\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n")
    print("Please see the project documentation at https://github.com/jgyates/genmon.\n")
    print("Error: " + str(e1))
    sys.exit(2)
import RPi.GPIO as GPIO

# https://sourceforge.net/p/raspberry-gpio-python/wiki/Inputs/
# These are the GPIP pins numbers on the Raspberry PI GPIO header
# https://www.element14.com/community/servlet/JiveServlet/previewBody/73950-102-10-339300/pi3_gpio.png
INPUT_STOP = 11             # STOP GPIO 17
INPUT_START = 13            # START GPIO 27
INPUT_START_TRANSFER = 15   # START/TRANSFER GPIO 22



#-----------------MyGPIO class -------------------------------------------------
class MyGPIOInput(MySupport):
    #-----------------init------------------------------------------------------
    def __init__(self, gpio = None, trigger = GPIO.FALLING, resistorpull = GPIO.PUD_UP, log = None, callback = None, uselibcallbacks = False, bouncetime = None):
        super(MyGPIOInput, self).__init__()
        self.Trigger = trigger
        self.ResistorPull = resistorpull
        self.GPIO = gpio
        self.log = log
        self.TimeoutSeconds = 1
        self.BounceTime = bouncetime
        self.Callback = callback
        self.UseLibCallbacks = uselibcallbacks
        self.Exiting = False

        try:

            GPIO.setmode(GPIO.BOARD)
            GPIO.setwarnings(True)
            GPIO.setup(gpio, GPIO.IN, pull_up_down=resistorpull)

            if callback != None and callable(callback):
                if self.BounceTime > 0:
                    GPIO.add_event_detect(gpio  = self.GPIO, edge = self.Trigger, bouncetime = self.BounceTime)
                else:
                    GPIO.add_event_detect(gpio  = self.GPIO, edge = self.Trigger)
                if self.UseLibCallbacks:
                    GPIO.add_event_callback(gpio = self.GPIO, callback = self.Callback)
                else:
                    # setup callback
                    self.Threads["GPIOInputMonitor"] = MyThread(self.GPIOInputMonitor, Name = "GPIOInputMonitor", start = False)
                    self.Threads["GPIOInputMonitor"].Start()

        except Exception as e1:
            self.LogErrorLine("Error in MyGPIOInput:init: " + str(gpio) + " : " + str(e1))

    #-----------------GPIOInputMonitor------------------------------------------
    def GPIOInputMonitor(self):

        try:
            while not self.Exiting:
                if GPIO.event_detected(self.GPIO):
                    self.LogError('Edge detected on pin ' + str(self.GPIO))
                    if self.Callback != None and callable(self.Callback):
                        self.Callback(self.GPIO)
                if self.WaitForExit("GPIOInputMonitor", 1):
                    return

        except Exception as e1:
            self.LogErrorLine("Error GPIOInputMonitor: " + str(self.GPIO)  + ": "+ str(e1))
    #-----------------Close-----------------------------------------------------
    def Close(self):
        try:
            self.Exiting = True
            if not self.UseLibCallbacks:
                self.KillThread("GPIOInputMonitor")
            GPIO.remove_event_detect(self.GPIO)

        except Exception as e1:
            self.LogErrorLine("Error in Close: " + str(e1))

#----------  Signal Handler ----------------------------------------------------
def signal_handler(signal, frame):

    try:
        for Channels in GPIOObjectList:
            Channels.Close()
        GPIO.cleanup()
        MyClientInterface.Close()

    except Exception as e1:
        LogErrorLine("Error: signal_handler: " + str(e1))
    sys.exit(0)

#------------------- StopCallback ----------------------------------------------
def StopCallBack(channel):

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=stop")
        LogError("Sent Remote Stop Command")
    except Exception as e1:
        LogErrorLine("Error StopCallback: " + str(e1))


#------------------- StartCallBack ---------------------------------------------
def StartCallBack(channel):

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=start")
        LogError("Sent Remote Start Command")
    except Exception as e1:
        LogErrorLine("Error StartCallback: " + str(e1))


#------------------- StartTransferCallBack -------------------------------------
def StartTransferCallBack(channel):

    try:
        MyClientInterface.ProcessMonitorCommand("generator: setremote=starttransfer")
        LogError("Sent Remote Start and Transfer Command")
    except Exception as e1:
        LogErrorLine("Error StartTransferCallback: " + str(e1))

#---------------------LogError--------------------------------------------------
def LogError(Message):
    if not log == None:
        log.error(Message)
#---------------------FatalError------------------------------------------------
def FatalError(Message):
    if not log == None:
        log.error(Message)
    raise Exception(Message)
#---------------------LogErrorLine----------------------------------------------
def LogErrorLine(Message):
    if not log == None:
        LogError(Message + " : " + GetErrorLine())
#---------------------GetErrorLine----------------------------------------------
def GetErrorLine():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)
#------------------- Command-line interface for gengpioin ----------------------
if __name__=='__main__':
    address=ProgramDefaults.LocalHost

    try:
        console = SetupLogger("gengpioin_console", log_file = "", stream = True)

        if os.geteuid() != 0:
            console.error("You need to have root privileges to run this script.\nPlease try again, this time using 'sudo'. Exiting.")
            sys.exit(2)

        HelpStr = '\nsudo python gengpioin.py -a <IP Address or localhost> -c <path to genmon config file>\n'
        try:
            ConfigFilePath = ProgramDefaults.ConfPath
            opts, args = getopt.getopt(sys.argv[1:],"hc:a:",["help","configpath=","address="])
        except getopt.GetoptError:
            console.error("Invalid command line argument.")
            sys.exit(2)

        for opt, arg in opts:
            if opt == '-h':
                console.error(HelpStr)
                sys.exit()
            elif opt in ("-a", "--address"):
                address = arg
            elif opt in ("-c", "--configpath"):
                ConfigFilePath = arg
                ConfigFilePath = ConfigFilePath.strip()
    except Exception as e1:
        console.error("Error in init: " + str(e1) + " : " + GetErrorLine())
        sys.exit(1)
    try:
        port, loglocation = MySupport.GetGenmonInitInfo(ConfigFilePath, log = console)
        log = SetupLogger("client", os.path.join(loglocation, "gengpioin.log"))
    except Exception as e1:
        log.error("Error setting up log: " + str(e1))
        sys.exit(1)
    try:
        # Set the signal handler
        signal.signal(signal.SIGINT, signal_handler)

        Threads = {}
        UseCallbacks = False
        DefaultTrigger = GPIO.FALLING
        DefaultPullup = GPIO.PUD_UP
        DefaultBounce = 0

        if os.path.isfile(os.path.join(ConfigFilePath, 'gengpioin.conf')):
            config = MyConfig(filename = os.path.join(ConfigFilePath, 'gengpioin.conf'), section = 'gengpioin', log = log)
            Trigger = config.ReadValue('trigger', default = "falling")
            if Trigger.lower() == "rising":
                DefaultTrigger = GPIO.RISING
            elif Trigger.lower() == "both":
                DefaultTrigger = GPIO.BOTH
            else:
                DefaultTrigger = GPIO.FALLING

            ResistorPull = config.ReadValue('resistorpull', default = "up")
            if ResistorPull.lower() == "down":
                DefaultPullup = GPIO.PUD_DOWN
            elif ResistorPull.lower() == "off":
                DefaultPullup = GPIO.PUD_OFF
            else:
                DefaultPullup = GPIO.PUD_UP

            DefaultBounce = config.ReadValue('bounce', return_type = int, default = 0)
            UseGPIOLibraryCallbacks = config.ReadValue('uselibcallbacks', return_type = bool, default = True)

        Settings = ""
        if DefaultPullup == GPIO.PUD_OFF:
            Settings += " Resitor Pull Off "
        elif DefaultPullup == GPIO.PUD_UP:
            Settings += " Resitor Pull Up "
        elif DefaultPullup == GPIO.PUD_DOWN:
            Settings += " Resitor Pull Down "
        else:
            Settings += " Resitor Pull Unknown "

        if DefaultTrigger == GPIO.RISING:
            Settings += " Trigger Rising "
        elif DefaultTrigger == GPIO.FALLING:
            Settings += " Trigger Falling "
        elif DefaultTrigger == GPIO.BOTH:
            Settings += " Trigger Both "
        else:
            Settings += " Trigger Unknown "

        log.error("Settings: " + Settings + " bounce = " + str(DefaultBounce))
        MyClientInterface = ClientInterface(host = address, port = port, log = log)

        #setup GPIO using Board numbering
        GPIO.setmode(GPIO.BOARD)

        #log.info( GPIO.RPI_INFO)
        #log.info(GPIO.VERSION)

        ChannelList = { INPUT_STOP : StopCallBack,
                        INPUT_START : StartCallBack,
                        INPUT_START_TRANSFER: StartTransferCallBack
                    }

        GPIO.setwarnings(True)

        GPIOObjectList = []

        for Channel, ChannelCallback in ChannelList.items():
            GPIOObjectList.append(MyGPIOInput(
                    gpio = Channel,
                    trigger = DefaultTrigger,
                    resistorpull = DefaultPullup,
                    log = log,
                    callback = ChannelCallback,
                    uselibcallbacks = UseGPIOLibraryCallbacks,
                    bouncetime = DefaultBounce))

        while True:
            time.sleep(3)

    except Exception as e1:
        log.error("Error : " + str(e1))
        console.error("Error: " + str(e1))
