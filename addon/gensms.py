#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: gensms.py
# PURPOSE: genmon.py support program to allow SMS (txt messages)
# to be sent when the generator status changes
#
#  AUTHOR: Jason G Yates
#    DATE: 05-Apr-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import os
import signal
import sys
import time

try:
    # this will add the parent of the genmonlib folder to the path
    # if we are one level below the genmonlib parent (e.g. in the addon folder)
    file_root = os.path.dirname(os.path.realpath(__file__))
    parent_root = os.path.abspath(os.path.join(file_root, os.pardir))
    if os.path.isdir(os.path.join(parent_root, "genmonlib")):
        sys.path.insert(1, parent_root)

    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.myclient import ClientInterface
    from genmonlib.mymsgqueue import MyMsgQueue
    from genmonlib.mynotify import GenNotify
    from genmonlib.mysupport import MySupport
except ImportError as e_imp_genmon:
    # Logger not available yet, print to stderr
    sys.stderr.write(
        "\n\nFATAL ERROR: This program requires the genmonlib modules.\n"
        "These modules should be located in the 'genmonlib' directory, typically one level above the 'addon' directory.\n"
        "Please ensure the genmonlib directory and its contents are correctly placed and accessible.\n"
        "Consult the project documentation at https://github.com/jgyates/genmon for installation details.\n"
    )
    sys.stderr.write(f"Specific import error: {e_imp_genmon}\n")
    sys.exit(2)

try:
    from twilio.rest import Client
    from twilio.base.exceptions import TwilioRestException # More specific Twilio exception
except ImportError as e_imp_twilio:
    sys.stderr.write(
        "\n\nFATAL ERROR: This program requires the twilio module to be installed.\n"
        "Please install it, e.g., using 'pip install twilio'.\n"
        "Consult the project documentation at https://github.com/jgyates/genmon for more details.\n"
    )
    sys.stderr.write(f"Specific import error: {e_imp_twilio}\n")
    sys.exit(2)

# ----------  Signal Handler ----------------------------------------------------
def signal_handler(signal_received, frame): # Use more descriptive argument names
    log.info(f"Signal {signal_received} received, initiating shutdown.")
    try:
        if 'GenNotify' in globals() and GenNotify: # Check if defined
            GenNotify.Close()
        if 'Queue' in globals() and Queue: # Check if defined
            Queue.Close()
    except Exception as e_signal: # Avoid reusing e1
        log.error(f"signal_handler: Error during close operations: {e_signal}")
    log.info("Shutdown complete.")
    sys.exit(0)


# ----------  OnRun -------------------------------------------------------------
def OnRun(Active):

    if Active:
        console.info("Generator Running")
        Queue.SendMessage("Generator Running")
    else:
        console.info("Generator Running End")


# ----------  OnRunManual -------------------------------------------------------
def OnRunManual(Active):

    if Active:
        console.info("Generator Running in Manual Mode")
        Queue.SendMessage("Generator Running in Manual Mode")
    else:
        console.info("Generator Running in Manual Mode End")


# ----------  OnExercise --------------------------------------------------------
def OnExercise(Active):

    if Active:
        console.info("Generator Exercising")
        Queue.SendMessage("Generator Exercising")
    else:
        console.info("Generator Exercising End")


# ----------  OnReady -----------------------------------------------------------
def OnReady(Active):

    if Active:
        console.info("Generator Ready")
        Queue.SendMessage("Generator Ready")
    else:
        console.info("Generator Ready End")


# ----------  OnOff -------------------------------------------------------------
def OnOff(Active):

    if Active:
        console.info("Generator Off")
        Queue.SendMessage("Generator Off")
    else:
        console.info("Generator Off End")


# ----------  OnManual ----------------------------------------------------------
def OnManual(Active):

    if Active:
        console.info("Generator Manual")
        Queue.SendMessage("Generator Manual")
    else:
        console.info("Generator Manual End")


# ----------  OnAlarm -----------------------------------------------------------
def OnAlarm(Active):

    if Active:
        console.info("Generator Alarm")
        Queue.SendMessage("Generator Alarm")
    else:
        console.info("Generator Alarm End")


# ----------  OnService ---------------------------------------------------------
def OnService(Active):

    if Active:
        console.info("Generator Service Due")
        Queue.SendMessage("Generator Service Due")
    else:
        console.info("Generator Servcie Due End")


# ----------  OnUtilityChange ---------------------------------------------------
def OnUtilityChange(Active):

    if Active:
        console.info("Utility Service is Down")
        Queue.SendMessage("Utility Service is Down")
    else:
        Queue.SendMessage("Utility Service is Up")
        console.info("Utility Service is Up")


# ----------  OnSoftwareUpdate --------------------------------------------------
def OnSoftwareUpdate(Active):

    if Active:
        console.info("Software Update Available")
        Queue.SendMessage("Software Update Available")
    else:
        Queue.SendMessage("Software Is Up To Date")
        console.info("Software Is Up To Date")


# ----------  OnSystemHealth ----------------------------------------------------
def OnSystemHealth(Notice):
    Queue.SendMessage("System Health : " + Notice)
    console.info("System Health : " + Notice)


# ----------  OnFuelState -------------------------------------------------------
def OnFuelState(Active):
    if Active:  # True is OK
        console.info("Fuel Level is OK")
        Queue.SendMessage("Fuel Level is OK")
    else:  # False = Low
        Queue.SendMessage("Fuel Level is Low")
        console.info("Fuel Level is Low")


# ----------  OnPiState ---------------------------------------------------------
def OnPiState(Notice):
    Queue.SendMessage("Pi Health : " + Notice)
    console.info("Pi Health : " + Notice)


# ----------  SendNotice --------------------------------------------------------
def SendNotice(Message):

    try:

        if sitename != None and len(sitename):
            Message = sitename + ": " + Message

        client = Client(account_sid, auth_token)

        # send to multiple recipient(s)
        for recipient in to_number_list:
            recipient = recipient.strip()
            message = client.messages.create(
                to=recipient, from_=from_number, body=Message
            )
            console.info(message.sid)
        return True
    except TwilioRestException as e_twilio: # Specific Twilio API exception
        log.error(f"SendNotice: Twilio API error sending SMS: {e_twilio}")
        console.error(f"SendNotice: Twilio API error: {e_twilio}")
        return False
    except Exception as e_send_sms: # Catch any other unexpected error
        log.error(f"SendNotice: Unexpected error sending SMS: {e_send_sms}")
        console.error(f"SendNotice: Unexpected error: {e_send_sms}")
        return False


# ------------------- Command-line interface for gengpio ------------------------
if __name__ == "__main__":
    # Initialize log and console to None or basic handlers initially,
    # as SetupAddOnProgram might fail before they are properly set.
    log = None
    console = None
    ConfigFilePath = ProgramDefaults.ConfPath # Default, might be overridden by SetupAddOnProgram

    try:
        (
            console,
            ConfigFilePath, # This will be updated by SetupAddOnProgram
            address,
            port,
            loglocation,
            log, # This will be the proper logger
        ) = MySupport.SetupAddOnProgram("gensms")

        # Set the signal handler now that log is configured
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        config_file_full_path = os.path.join(ConfigFilePath, "gensms.conf")
        log.info(f"Reading configuration from {config_file_full_path}")

        config = MyConfig(
            filename=config_file_full_path,
            section="gensms",
            log=log,
        )

        account_sid = config.ReadValue("accountsid", default="")
        auth_token = config.ReadValue("authtoken", default="")
        to_number = config.ReadValue("to_number", default="")
        from_number = config.ReadValue("from_number", default="")

        if not account_sid or not auth_token or not to_number or not from_number:
            err_msg = f"Missing one or more critical parameters (accountsid, authtoken, to_number, from_number) in {config_file_full_path}"
            log.error(err_msg)
            console.error(err_msg)
            sys.exit(1)
        
        to_number_list = [num.strip() for num in to_number.split(",") if num.strip()]
        if not to_number_list:
            err_msg = f"No valid recipient phone numbers (to_number) found in {config_file_full_path}"
            log.error(err_msg)
            console.error(err_msg)
            sys.exit(1)

    except FileNotFoundError: # Specifically for gensms.conf
        err_msg_fnf = f"Configuration file 'gensms.conf' not found in path: {ConfigFilePath}"
        if log: log.error(err_msg_fnf)
        else: sys.stderr.write(err_msg_fnf + "\n")
        if console: console.error(err_msg_fnf)
        sys.exit(1)
    except (KeyError, ValueError) as e_conf_read: # For issues reading specific config values
        err_msg_conf = f"Error reading critical configuration from gensms.conf: {e_conf_read}"
        if log: log.error(err_msg_conf)
        else: sys.stderr.write(err_msg_conf + "\n")
        if console: console.error(err_msg_conf)
        sys.exit(1)
    except Exception as e_setup: # Catch-all for other setup errors before main loop
        err_msg_setup = f"An unexpected error occurred during initial setup: {e_setup}"
        if log: log.error(err_msg_setup, exc_info=True) # exc_info for stack trace
        else: sys.stderr.write(err_msg_setup + "\n")
        if console: console.error(err_msg_setup)
        sys.exit(1)
        
    try:
        log.info(f"Connecting to genmon server at {address}:{port}")
        Generator = ClientInterface(host=address, port=port, log=log) # ClientInterface should handle its own connection errors
        sitename = Generator.ProcessMonitorCommand("generator: getsitename")
        Queue = MyMsgQueue(config=config, log=log, callback=SendNotice)

        GenNotify = GenNotify(
            host=address,
            port=port,
            onready=OnReady,
            onexercise=OnExercise,
            onrun=OnRun,
            onrunmanual=OnRunManual,
            onalarm=OnAlarm,
            onservice=OnService,
            onoff=OnOff,
            onmanual=OnManual,
            onutilitychange=OnUtilityChange,
            onsoftwareupdate=OnSoftwareUpdate,
            onsystemhealth=OnSystemHealth,
            onfuelstate=OnFuelState,
            onpistate=OnPiState,
            log=log,
            loglocation=loglocation,
            console=console,
            config=config,
        )

        while True:
            # Main loop: GenNotify handles interactions.
            # If GenNotify exits or has an unrecoverable error, it might raise an exception
            # or its thread might terminate, which could be handled here if needed.
            # For now, assume GenNotify and Queue run until signal_handler causes sys.exit.
            if InstanceSMS.Exiting: # Check a flag if MySMS class has one
                log.info("Exiting flag set on MySMS instance. Shutting down main loop.")
                break
            time.sleep(1) # Keep main thread alive

    except (socket.error, ConnectionRefusedError, TimeoutError, OSError) as e_network: # Network errors for ClientInterface
        log.error(f"Main: Network error connecting to genmon server: {e_network}", exc_info=True)
        console.error(f"Main: Network error: {e_network}")
    except KeyboardInterrupt: # User interruption (Ctrl+C)
        log.info("Main: Keyboard interrupt received. Shutting down...")
        # signal_handler should be invoked by SIGINT, but this is a fallback.
        signal_handler(signal.SIGINT, None)
    except Exception as e_main_loop: # Catch any other unexpected error in the main execution block
        log.error(f"Main: An unexpected error occurred in the main loop: {e_main_loop}", exc_info=True)
        console.error(f"Main: Unexpected error: {e_main_loop}")
    finally:
        log.info("Main: gensms.py is shutting down.")
        # Ensure resources are cleaned up if not handled by signal_handler already
        if 'GenNotify' in globals() and GenNotify and hasattr(GenNotify, 'Close'): GenNotify.Close()
        if 'Queue' in globals() and Queue and hasattr(Queue, 'Close'): Queue.Close()
