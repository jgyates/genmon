# Change Log
All notable changes to this project will be documented in this file.

## V1.19.04 -2024-08-21
- Corrected issue with saving service journal with HTTPS enabled
- Added new alarm code for Nexus
- Change to pysnmp library v6.x changed so locking to version 5.1.0
- Updated method to reduce the power log
- Minor update to force legacy writes for exercise cycles with older firmware on Evolution 1.0
- Added option to genmqtt add on to optionally retain data at the broker
- Updated Briggs support to include text output for better MQTT support
- Corrected on bug in fuel calculation for 32kW Evolution based Propane Liquid Cooled units
- Corrected bug in Briggs and Stratton controller definition. Changed name of some gauges to better describe the value.
- Added new alarm code for Nexus Evolution
- Minor mod to maintenance page update to allow for faster loading
- Corrected one issue with power log error check
- added check for python being installed in the install script
- Corrected one error in definition of modbus exception code
- Updated install to use version of pyopenssl from earlier in 2024 to avoid and error introduced with the new version
- Minor update to correct formatting issue with bus voltage on PowerZone Sync
- Added new alarm ID for internal controller fault for Evolution / Nexus
- Updated External Temp Sensor add on to support non zero minimum values
- More updates to allow for correct display on PowerZone Sync

## V1.19.03 -2024-04-19
- New add on program genmqttin.py. See wiki and add on page for details
- Update to serialconfig.py to support file location changes with config.txt and cmdline.txt in latest Raspberry Pi firmware versions
- Minor update to genmonmaint.sh to use Ubuntu serial device names if Non Raspberry pi OS detected 
- Minor update for better error handling when getting CPU temp
- Minor update for better error reporting with email failures
- Corrected issue with login page errors in developer console
- Update to mymail.py to support optional HTML format of outbound email
- Update to genmopeka.py add on to ignore invalid readings from mopeka sensor.
- Fixed issue with latest version of voipms. Install now uses version 0.2.5.
- Added additional parameter checking on add on programs
- Minor update for PowerPact model (removed display of unsupported sensors: current and power)
- Added option in genexercise.conf to start monthly exercise on xth week day of the month (see genexercise.conf in repository for more details)

## V1.19.02 -2024-02-14
- Update for Kohler APM603 support
- Added new commands for EvoLC
- Added Gauges for Current Legs for Evolution Air Cooled
- Added Advanced Setting to check for Load Imbalanced for Evo AC (built in CTs) and External CTs for Evo and Nexus. See "Unbalanced Load Capacity" on Advanced Settings page
- Corrected bug that was introduced in last version that prevented some buttons in the web interface from showing the color as disabled
- Minor error handling update in Fuel Logger thread
- Minor update to controller detection for custom controller models
- Update for 26kw Evo2 air cooled model
- Update to genmonmaint.sh for managed python environments
- update for paho-mqtt version change
- Optimizations for EvoLC current calculations and Nexus exercise time calculations 
- Update to better identify Evolution and Nexus air cooled models
- Update to allow L1 and L2 current to be exported via MQTT and update L1 and L2 gauge nominal values
- Added Outage Recurring Notices option, see Advanced Settings page
- Update to force Enhanced Exercise for known supported controllers
- Minor update to genslack add on for error handling improvements
- Update to outage log processing to prevent invalid fuel usage for outages lasting less than one second

## V1.19.01 -2023-12-06
- Update to genmonmaint.sh to ask about serial connection type on install (thanks @skipfire)
- Corrected issue with genloader to remove check for mopeka library that was replaced
- Fixed issue with 'Force Integer' setting on SNMP add on to convert external tank sensors to integer properly
- Modifications to support Raspberry Pi 5: detect pi model, enabled serial port, for pi5 default port is /dev/ttyAMA0, not /dev/serial0
- Minor update to Briggs and Stratton maintenance alarm definition 
- Update to genmqtt add on to support MTLS
- Update for ComAp controller
- Minor change to the way alarms are displayed for custom controllers
- Updates for better error handling for custom controller
- Add the ability to have minimum delay between short messages (e.g. callmebot signal)
- Minor update for Deepsea controller switch state
- More updates for ComAp controller
- Update to gentankutil to add option to check battery and missed readings. See Add On page to enable this functionality.
- Minor update to error handling of fuel gauge 
- Added new option to return JSON for numerics on MQTT addon genmqtt.py
- Alarm code and log code updates for Nexus AC and Evo LC

## V1.19.00 -2023-11-09
- Updates to genmonmain.sh, startgenmon.sh and genloader.sh for Debian bookworm. 
- Minor update to serialconfig.py to make serial0 instead of serial1 work on bookworm
- Updates to custom controller code to support additional modbus functions (coils and input registers)
- Updated modbusdump to support new modbus functions
- Updated Briggs custom controller support to use modbus function 4 in a more compatible way
- Fixed issue with Alternate Date format option and log page heatmap
- Enhancements to genexercise https://github.com/jgyates/genmon/issues/968 and https://github.com/jgyates/genmon/issues/958
- custom controller updates to support writing values to the controllers via buttons with parameters
- Added daily option to genexercise
- Minor change to how modbus is handled when closing / restarting to prevent lockup on H-100 controller receiving a partial modbus packet
- Update to bookworm mods to support python 3.5
- Minor update to genmonmaint.sh to allow calling from outside the genmon folder
- Update for more fine grained status changes (more email notifications) for H100
- Added the ability to set the time for custom controllers 
- Minor update to gensnmp to compensate for invalid setting in genmon.conf
- Added reading time to Briggs and Stratton custom controller config
- Updated genmopeka.py add on to support more mopeka sensors and stop using old mopeka python library
- Minor update to disable MFA if HTTPS is not enabled
- Corrected with with MQTT Numerics for custom controllers

## V1.18.18 -2023-07-05
- Added new add on program gencallmebot (thanks @buschauer)
- Added preliminary support for PowerZone 410 controller
- Modification to allow JSON for Numerics for external temp sensors when using MQTT add on
- Corrected issue with some systems not updating from the About page properly (if you have this issue you may need to update once via ssh to get the fix)
- Update to gensnmp.py to allow integer values to be returned when applicable
- Update to gensnmp,py to support custom controller definitions
- Added advanced setting for alternate date format
- Updated jquery to 3.7 (thanks @buschauer)
- Minor update to mytile.py to improve handling of gauges with values out of range
- modified gengpio.py add on to optionally support GPIO signaling for out of range CPU temperature 
- Update for Power Zone 410. 
- Update for custom controller functionality (logs, identity, register labels)
- Minor update to myserial.py to improve error handling and recovery
- Added functionality for custom defined controllers via JSON
- Minor formatting update to web UI spacing to better accommodate custom controllers
- Updated alarm code for Evolution 2.0
- Added genmon.conf entries for using loopback IP address for listen address in server
- Update to current calculation for liquid cooled Evolution
- Update to gensnmp.py to allow user defined SNMP entries
- Fixed issue with page reload after saving service journal 
- Change for external CT gauge display when using gencthat.py add on
- Fixed bug that may prohibit some add on programs from working at the same time
- Added more bounds checking to gentemp.py
- Corrected issue with Settings page not allows Even parity to be set on custom controllers
- Corrected security issue related to ldap login with genserv.py

## V1.18.17 -2023-04-06
- Added feature request to allow external temperature sensors to be displayed as gauges
- Update for horizontal 120 gal tanks in mopeka sensor add on
- update to genmonmaint.sh for noprompt copyfiles (thanks @skipfire)
- Updated tooltip comment
- Added ability to set data rate other than 9600 (for Liquid Cooled Evolution Controllers with 4.5L engine and possibly new custom controllers)
- Updates for Evolution 4.5L models 48k, 60k and 80k (thanks @basshook)
- Updates for unknown alarms for 4.5L controller
- Updates to About page to better handle slower upgrades
- Minor update to gensnmp to allow the disabling of IPv6

## V1.18.16 -2022-12-06
- Change to allow CPU temp gauge for any linux system
- Update to support version info in Alpine Linux (thanks @gregmac)
- Added new add on program gencustomgpio.py (see https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencustomgpiopy-optional)
- Updated genmqtt to better handle the outage log
- Added site name to short messages for gensms, genpushover and genslack
- Added the ability to send SMS via https://voip.ms (see https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_voippy-optional)
- Added additional remote command to reset active alarms for Evolution 2.0 air cooled controllers
- Updated install script to changing cryptography requirements
- Updated icons for new add ons (thanks @buschauer)
- Update to attempt to display WiFi signal strength consistent across various network drivers
- Minor update in genloader to better support older distros of Raspbian
- Updated response to remote email commands to avoid email loop problem

## V1.18.15 -2022-09-18
- Correct issue with power graph
- Added priorities parameter to Pushover add on (see add on page for settings)
- Minor update for PowerZone remote start
- Added short notifications for CPU Throttling, CPU cap and CPU undervoltage on pi platforms
- Minor update to JSON for Briggs and Stratton Controller
- Added the ability to set baud rate, stop bits and parity for custom controllers
- Increased wait time on errors for Openweathermap from one to three minutes to reduce log data from filling up during an internet outage
- Formatting changes and pre-commit integration (thanks @rcmurphy/)
- Change to allow CPU temp gauge for any linux system
- Update to support version info in Alpine Linux (thanks @gregmac)

## V1.18.14 -2022-08-21
- Minor update to improve fuel calculations for outages
- Updated serialconfig.py to optionally allow bluetooth to be used with the normal serial port operations.
- Corrected one bug in serialconfig.py
- Minor update to custom controller support to handle failed comms display notice
- Added Mopeka Pro Propane Sensor Add On
- Minor update to better enforce the "Ignore Unknowns" advanced option for Evolution 2.0
- Added outage reporting for custom controllers. See wiki for more details.
- Improved serial error handling for USB devices
- Improved error handling for custom controller comm errors
- Moved add on program files to the addon folder, updated genloader to support this move
- NOTE: This upgrade make take longer to install, please be patient as it is a larger-ish download and install process
- Removed fluids from installing with genloader. To use the genmopeka addon you must manually install fluids via the install script
- Correct issue with power graph
- Added priorities parameter to Pushover add on (see add on page for settings)
- Minor update for PowerZone remote start

## V1.18.13 -2022-07-25
- Minor update for SMTP compatibility (thanks @lps-rocks)
- Minor update to IMAP incoming email handling (thanks @rwskinner)
- Update to allow modbus function code 4 instead of 3 for some customer controller support (thanks @marklitwin)
- Updated alarm code for Evo 2.0
- Updated alarm code for Synergy
- Added support Briggs & Stratton GC-1032 Controller via custom controller method (thanks @marklitwin)
- Minor javascript update to correct security warning (thanks @buschauer)
- Code cleanup
- Improved error handing in mymail.py to better support older versions of SSL libraries
- Added run hours in the last year to the maint page. Note that this the last 365 days, not the last calendar year.
- Added option for serial parity on Advanced Settings page for Briggs and Stratton controllers

## V1.18.12 -2022-06-21
- Commented optional enhancements to gengpio.py
- Added the ability to monitor and trigger on genmon socket commands (https://github.com/jgyates/genmon/wiki/Appendix-C--Interfacing-Generator-Monitor-to-External-Applications#extend-genmonpy)
- Added option to change port used for gensnmp
- Service Log improvements (https://github.com/jgyates/genmon/issues/709) thanks @lwbeam
- Update alarm codes for Nexus AC
- Updated gentankdiy with accuracy improvements. Thanks @davisgoodman and @zekyl314, see new wiring diagram https://github.com/jgyates/genmon/wiki/Appendix-L-Adding-a-Propane-Fuel-Gauge-to-Genmon
- Updated alarm codes for Ignition Fault
- Corrected problem when disabling platform stats

## V1.18.11  -2022-04-19
- Update to parse international domains correctly in mymail.py
- Update to allow unicode characters in site name emails on 64 bit systems
- Added support for up to four tanks for DIY gauge type 1
- Added the ability to extend genserv.py (https://github.com/jgyates/genmon/wiki/Appendix-C--Interfacing-Generator-Monitor-to-External-Applications)
- Fix one bug related to MQTT support option "JSON for Numerics"
- Corrected on bug in Maintenance display for Evo Liquid Cooled units
- Added temporary login lockout of maximum failed web login attempts are exceeded. See Advanced settings for parameters.
- Correcting typos (thanks @curtis1757 )

## V1.18.10  -2022-03-23
- Update to correct minor issue with H-Panel and G-Panel systems reading of Engine kW Hours causing a modbus exception.
- Added phase info to support data when registers are submitted
- Update to support correct voltage output for Evolution Air Cooled 3 Phase models
- Corrected problem with Frequency for air cooled models introduced in 1.18.09

## V1.18.09  -2022-03-10
- Update to mymail.py to prevent mail from a category with no recipient from being put in the send queue.
- Update to gengpio.py to address bug that broke gpio functionality
- improved error checking in generator specific modules
- Update to serial logging to include sequence info in error logs

## V1.18.08  -2022-02-25
- Added more validation checking in genpushover.py
- Changed the default value for Strict setting usage for the CT Hat Add on (Default is now off)
- More minor updates for custom controller support and DeepSea Controllers
- Fixed on minor issue for python 2.x transitioning to python 3.x
- Added gencthat.log to the download log command
- Added a button on the maintenance page to download and archive of the log files
- Minor error checking update in genexercise.py
- Corrected numerous spelling errors in displayed strings
- Fixed issue with javascript not displaying all tool tips correctly

## V1.18.07  -2022-02-16
- Added retry capability for short message add ons (gensms, genslack and genpushover). Messages are retried every 2 min for 10 minutes.
- Minor update to add on cleanup code

## V1.18.06  -2022-02-07
- Update for custom controller support to add buttons to the maintenance page
- Genloader update that checks / corrects an issue with the improper version of openweathermap library. This may cause a delay for a few seconds one time while applying this update.
- Corrected rounding inconsistency in temp display (thanks @lps-rocks)
- Update to work around change to kernel handing of raspberry pi throttling status display to compensate for kernel changes (thanks @lps-rocks)
- Update to External CT add on to reduce noise (thanks @skipfire)
- Added option to disable the display of estimated fuel remaining if an external gauge is used and propane fuel is used (thanks @lps-rocks)
- removed throttled_check.py utility for maintenance reasons. This functionality is included in genmon.
- Consolidate common code for displaying status and maintenance information (general housekeeping)

## V1.18.05  -2022-01-28
- Updated gensnmp.py SNMP add on. Improvements for SMIv2 and snmpcheck compliance. **NOTE** SNMP values have changed see the wiki for details on the new values. https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional
- Normally I would not change the SNMP OIDs as this will impact people who have deployed this plugin, however this update does provide more compatibility with the SNMP standard and now a MIB file is provided.
- The default enterprise ID is now 58399. If you are using the old enterprise ID of 9999 it is recommended (but not required) that you change it to 58399.
- Minor update for custom_controller types.
- Added custom controller for Deep Sea Generator, thanks @Ntampata

## V1.18.04  -2022-01-11
- Upgrade may take a little longer, depending on your raspbian versions due to a new library for SPI devices needs to be installed.
- New Add On for Pintsize.me Raspberry pi HAT for adding external Current Transformers. This allows models without adequate power or current reporting to support a power graph and fuel estimations.
- More Info Here: https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencthatpy-optional
- Fixed minor issue with serialtest.py
- Added support for multiple tanks in gentankutil.py
- Updated Evolution Liquid Cooled Alarm Log code for ignition fault
- Corrected issue with log calendar heat map not showing the current month (thanks @buschauer)

## V1.18.03  -2021-12-06
- Fixed issue with exclusive serial port check with older versions of pyserial (pre pyserial v3.3)

## V1.18.02  -2021-12-05
- Fixed bug in set exercise functions for Evo / Nexus related to Python 3

## V1.18.01  -2021-11-24
- Added notification filter options for gensms, gensms_modem, genslack, genpushover, genemail2sms addons. See Add On page to set filter options
- Fixed bug in gensms_modem and custom controller code for python3
- Added optional gauges for WiFi signal strength and Raspberry Pi CPU temperature. Both can be disabled on the advanced settings page.

## V1.18.00  -2021-11-09
- python3 is now the default instead of python2. This upgrade may take longer to install since python3 libraries will need to be installed so please be patient if genmon does not respond immediately after the upgrade. See https://github.com/jgyates/genmon/issues/598 for more details

## V1.17.05  -2021-11-08
- Update to gengpio.py to allow for disabling to GPIO

## V1.17.04  -2021-10-15
- Added support for Evolution 2.0 14kW

## V1.17.03  -2021-10-08
- Added code in serial number lookup to handled invalid serial numbers in web response
- Updated code to ignore specific status codes in Evo 2.0 (Advanced Settings -> Ignore Unknown Values)

## V1.17.02  -2021-08-28
- Corrected bug in MFA web security login

## V1.17.01  -2021-08-01
- Added values for 18kw Evo 2.0 generator, new alarm entry for Evo 2.0 Wiring Error

## V1.17.0  -2021-07-30
- Added extensible method to support new types of generator controllers.

## V1.16.13  -2021-07-10
- Added the ability to print the service log
- Updated alarm code for Service A and Service B due for Evolution
- Updates for two DIY gauges on DIY gauge add on (thanks @speters0)
- Added new alarm code for wiring error

## V1.16.12  -2021-07-01
- Added option to change the GPIO pins used with the add on gengpioin. Change the settings in the gengpioin.conf file.
- Changed the frequency of the firmware update check for Evolution 2.0 to every hours instead of many times per hour. This reduces the chance of invalid notices when communication errors are occurring.
- Update to gentankdiy to optionally support two tanks (see /conf/gentankdiy.conf for details). This applies to the DIY gauge type 1 only. Type 2 still only supports only one gauge.

## V1.16.11  -2021-06-16
- Added option to notify of transfer state changes on H and G Panel controllers. Note: the proper connections from your switch to the controller must be setup for this to work properly.

## V1.16.10  -2021-06-11
- Added gengpio.conf file to set GPIO pins to values other than the default.

## V1.16.09  -2021-05-25
- Corrected bug in web app that displays weather on the lower right. Error occurred if weather reporting was disabled (thanks @speters0)

## V1.16.08  -2021-05-22
- Added restart, reboot and shutdown feature on the advanced page.
- Minor updates for formatting and error reporting

## V1.16.07  -2021-05-19
- Added  engine displacement data Evo2 16kw
- Updated fuel calculation for some Evo2 models

## V1.16.06  -2021-05-10
- Added Advanced Option to allow for a delay in outage notices (Evolution and Nexus only)
- Minor update to UI to correct incorrect display on Nexus controllers when setting the exercise time

## V1.16.05  -2021-04-07
- Minor python 3 updates to myplatform.py
- Fixed bug in short message notifications of low fuel

## V1.16.04  -2021-03-17
- Update for Evolution Synergy to fix frequency values (https://github.com/jgyates/genmon/issues/521)
- Minor update for PowerZone
- Added new alarm code for Evolution

## V1.16.03  -2021-03-03
- Updated fix for modbus file handling (only specific to industrial controllers). Powerzone controllers handle modbus file register access a little differently and this update handles that difference.

## V1.16.02  -2021-03-02
- Corrected bug in H-100, G-Panel and PowerZone modbus file handling

## V1.16.01  -2021-03-01
- Minor update to code that checks for previously installed modules
- Minor update to genloader to check if module is loaded before attempting to load

## V1.16.00  -2021-02-28
- Initial support for Generac PowerZone, log support not currently supported
- Update to genmqtt and gensnmp for powerzone support

## V1.15.20 - 2021-02-26
- Update for gensms add on to allow multiple recipients
- Update for OtherApps/modbusdump.py for modbus TCP support
- Minor tweak to gentankutil for maintenance reasons
- added support for Modbus TCP (existing support for Modbus serial over TCP is still supported also)

## V1.15.19 - 2021-02-10
- Updated mynotify.py to add notifications for software update, low fuel notice, and internal errors (e.g. communication errors etc.). This allows genslack, genpushover, gensms, gensms_modem, gensyslog and genemail2sms to support these additional notices.

## V1.15.18 - 2021-02-05
- Corrected bug in on_disconnect in genmqtt.py (thanks @notjj)
- Updated log entry for Nexus Air Cooled

## V1.15.17 - 2021-01-31
- Added MQTT last will and testament support for notifications of offline client.
- Added IP address in start up message
- Updated power log reduction code to improve situations where power log is filled with zeros
- Added advanced option for H-100 to calculate the output power based on average current, average voltage and power factor.


## V1.15.16 - 2021-01-15
- Added model recognition for Evolution 2.0 24kW  (Thanks @chia9876)
- Made username for web login case insensitive for admin and read only users

## V1.15.15 - 2021-01-11
- Update to allow I2C channel values greater than 2 for gentankdiy

## V1.15.14 - 2021-01-01
- minor Python 3 update
- Change that removes / prevents non ascii from power log or outage log

## V1.15.13 - 2020-12-14
- Remove output voltage display for pre-nexus controllers
- Minor update to genexercise.py to allow exercising when service is due alarm is active
- correct minor bug in in mymail.py

## V1.15.12 - 2020-12-14
- Minor updates to receiving mail for python 3 compatibility
- Minor updates to help with debugging

## V1.15.11 - 2020-11-15
- A new library was added so the restart after the upgrade may take a few seconds longer than ususal
- Improvements for start/stop of programs.
- Added new check to disallow loading multiple instances of any genmon program unless multi_instance option is set to True. see https://github.com/jgyates/genmon/wiki/Appendix-J-Multiple-Instances-of-Genmon for additional details.
- Update in javascript to handle user defined JSON data with null entries
- shutdown cleanup improved for genmqtt.py and gensnmp.py
- removed restart code / while loop in genserv.py that is likely the cause of intermittent corruption of conf file
- Added option to use alternate reading for frequency for Nexus Liquid Cooled units

## V1.15.10 - 2020-11-09
- Added new tank sensor type for gentankdiy.py add on (thanks @curtis1757)
- Misc code optimizations for maintenance purposes
- Fixed bug in shutdown code
- Minor change improve error checking in genlaoder
- Additional error checking for power log entries
- Added new alarm message for Evolution 2

## V1.15.09 - 2020-11-05
- Rounded value written to power log to 3 decimal places (Evolution)
- Corrected issue with email errors relating to RFC2821 (see https://tools.ietf.org/html/rfc2821#section-3.3)
- More improvements to better detect and recover modbus sync issues when using serial over TCP with weak wifi signals
- Improvement in gensnmp.py to clean up on restarts (thanks @liltux)
- Minor cleanup on genmqtt.py
- Cleanup saving of settings web app redirect when using secure login (thanks @curtis1757)
- Additional checks added for weather API city lookup
- gensnmp.py updates to allow an option to not display units for numeric values in SNMP responses, bug fix

## V1.15.08 - 2020-10-27
- Additional parameter validation for values read from conf file
- More recovery / error handling for long latency modbus response

## V1.15.07 - 2020-10-25
- Added new alarm code for Evolution
- Improvement on error recovery on time out errors (mostly occurring on bad wifi connections with serial over TCP)

## V1.15.06 - 2020-10-20
- added python functions to aid in portability (os.path.join)
- Corrected typo in web interface (thanks @danielforster)
- More minor corrections for python 3.x
- Moved location of version info in source tree for maintenance reasons. This required a small change in the software update check code

## V1.15.05 - 2020-10-18
- Added alarm code for Fuse Problem with Evolution Air Cooled
- Reverted to older config file write functions as the new ones did not provide the benefit expected
- Corrected one typo
- Fix for checking for software update bug
- Additional minor fix for python 3.x

## V1.15.04 - 2020-10-16
- Minor update to correct issue with software update check when using python 3.x
- Minor improvements that could help bad wifi when using serial over TCP over wifi
- Update to install script that will make move from python 2.7 to 3.x easier

## V1.15.03 - 2020-10-11
- Minor update to correct issue with writing config file
- Added additional checks to look for corrupt config file and restore the file if corrupted
- Changed some add on fields to hide passwords
- Allow external tank data to be used in calculating time remaining until tank empty
- Correct typos
- Update to gensnmp.py to fix issue with H100 alarm list
- Update to include fuel remaining based on estimated and current load assumptions
- Added Fuel In Tank output on Maintenance page

## V1.15.02 - 2020-10-07
- Minor fix to allow some pre-Nexus models to correctly perform a model lookup

## V1.15.01 - 2020-10-05
- Minor update that changes the format of register and log submissions to comply with RFC 2821 #4.5.3.1.

## V1.15.00 - 2020-10-02
- Implemented fix for Evolution 2 firmware 1.1x
- Added client id parameter for genmqtt add on

## V1.14.33 - 2020-09-28
- Updated myplatform.py to reflects some raspbian updates
- moves some constants around in the modbus code in preparation for future modifications
- Updated gensnmp.py to include OID for H and G Panel alarm list

## V1.14.32 - 2020-09-20
- Added multi-factor authentication to web interface settings

## V1.14.31 - 2020-09-17
- Added ESSID to WiFi platform information
- Updated myplaform.py to detect Pi4 and display CPU temp

## V1.14.30 - 2020-09-11
- Updagte to MQTT support to allow list of strings to be a parameter
- Added advanced parameter to better support weak wifi signals on serial over TCP
- Made Evolution 2.0 Ambient temp sensor display respond to Use Metric setting

## V1.14.29 - 2020-09-02
- Added more info to upgrade and communications failure notice emails

## V1.14.28 - 2020-08-31
- Added logout button in top right if using username/password to login to the web interface. Thanks @buschauer
- Made the service journal editable. Thanks @buschauer

## V1.14.27 - 2020-08-29
- Design update in preparation for future updates

## V1.14.26 - 2020-08-19
- Minor modification to gentankutil add on to compensate for changed web login at tankutility.com

## V1.14.25 - 2020-08-19
- Added new alarm code for Nexus Liquid Cooled and Evolution Air Cooled

## V1.14.24 - 2020-08-17
- Corrected bug introduced in V1.14.23 that prevented logging of outages

## V1.14.23 - 2020-08-09
 - Minor update to add on gensnmp (added estimated hours in tank remaining)
 - Added ability to have MQTT topics without spaces in add on genmqtt
 - Added support for DIY fuel gauge (https://github.com/jgyates/genmon/wiki/Appendix-L-Adding-a-Propane-Fuel-Gauge-to-Genmon)
 - Added advanced setting to disallow logging of short outages

## V1.14.22 - 2020-08-03
 - Corrected bug in model lookup code for python 3.x

## V1.14.21 - 2020-08-02
- Updated backup function to include all add on program settings
- Corrected problems with fuel consumption calculation for Evolution
- Added estimated hours remaining in tank for fuel consumption
- Added fuel consumption method for industrial controllers, see https://github.com/jgyates/genmon/wiki/Appendix-H-Monitoring-Fuel-and-Power-Usage
- Added option to display fuel sensor gauge for industrial controllers
- Fixed LDAP bug, thanks @magomez96

## V1.14.20 - 2020-07-30
- Added support for 11kw Nexus that was missing in generator identification

## V1.14.19 - 2020-07-29
- Added new support function to get full register data from the browser. Useful for debugging if email is not working.

## V1.14.18 - 2020-07-24
- Added new advanced setting to extend email retry delay on failed attempt to send emails
- Added reading of two new registers for possible display of new settings (Two Wire Start for Evo)

## V1.14.17 - 2020-07-10
- Added new alarm code for Evo (instantaneous alarm for High Temp)
- Added software update to Monitor->Generator Monitor Stats->Update Available

## V1.14.16 - 2020-07-05
- Added Add-On module for displaying external temperature sensor data from 1 wire interfaces. See https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentemppy-optional
- Corrected problem with ldap3 library reporting not present when it actually is installed

## V1.14.15 - 2020-06-28
- Added more error handling for modbus exceptions
- Added firmware version to Evo log file submissions

## V1.14.14 - 2020-06-18
- Updated Evo AC power calculation based on new data from @sefs85, you can revert to the old method in advanced settings "Use Legacy Power Calculation". Unless you have a 22kw Evolution (which has no CTs install form the factory so it can not read the current) it is recommended that you use this new method. You will likley need to remove any Current Divider or Current Offset settings on the advance page.

## V1.14.13 - 2020-06-16
- Corrected on python3 issue with genloader when attempting to load uninstalled libraries.

## V1.14.12 - 2020-06-02
- Added support for LDAP based login (@skipfire) (see /conf/genmon.conf for settings)

## V1.14.11 - 2020-05-28
- Minor update to fix corrupted genloader.conf, file if it occurs
- updated genmonmaint.sh that will improve crontab update

## V1.14.10 - 2020-05-20
- More updates for Python3
- corrected type in comment in mymodbus.py

## V1.14.09 - 2020-05-18
- Corrected minor issue with startgenmon.sh and python3
- changed command line to be more consistant across options

## V1.14.08 - 2020-05-18
- Updated the logic in the code to detect communication failures to include failed comms on a reboot.
- Corrected python3 install script (@liltux)
- Corrected minor issue with startgenmon.sh and python3

## V1.14.07 - 2020-05-18
- Added advanced setting for userdefined.json path other than the default.

## V1.14.06 - 2020-04-29
- Added error log code for Nexus

## V1.14.05 - 2020-04-18
- Corrected on bug introduced in 1.14.05

## V1.14.04 - 2020-04-18
- Updated MQTT support to allow sending commands to genmon

## V1.14.03 - 2020-02-17
- Updated MQTT support to allow numeric values for Maintenance and Outage related data (Evo/Nexus)

## V1.14.02 - 2020-02-08
- Added SNMP graphic on add on page

## V1.14.01 - 2020-02-02
- Minor change to logic in gensnmp.py to avoid namespace collision
- Correct typo

## V1.14.00 - 2020-02-01
- Added SNMP Add On. See https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional for details
- Changed a few labels of exported JSON data to better support SNMP and avoid namespace conflicts. There is a small chance this could effect some MQTT users depending on how deeply you have relied on namespace paths.
- Added option to send an email if a software update is available. This can be disabled on the settings page.
- Note: The update may take slightly longer since a new library has to be installed during the update process.

## V1.13.38 - 2020-01-17
- Changed text to "Inspect Battery" for Nexus models

## V1.13.37 - 2020-01-16
- Workaround for bug in gauge display for Safari mobile browsers

## V1.13.36 - 2020-01-11
- Corrected bug in reporting of weather (rain and snow in last 1 or 3 hours)

## V1.13.35 - 2020-01-09
- Added SMTP Auth Disable configuration setting

## V1.13.34 - 2020-01-09
- Corrected fuel calculation issue for NG systems

## V1.13.33 - 2019-12-18
- Added new alarm data for Evolution 2.0

## V1.13.32 - 2019-11-16
- Added new alarm log entry for Nexus

## V1.13.31 - 2019-11-14
- Added alarm code for "Battery Problem"

## V1.13.30 - 2019-11-03
- Update to allow outage log to display 100 instead of 50 entries

## V1.13.29 - 2019-08-20
- Fixed a few typos

## V1.13.28 - 2019-07-20
- Minor update to gentankutil.py
- Added add-on for Amazon Alexa

## V1.13.27 - 2019-07-20
- Updated icon on add-on page
- Added fuel metric to Maintenance page for models that support fuel monitoring

## V1.13.26 - 2019-07-19
- Added email notification for Evolution 2 firmware

## V1.13.25 - 2019-07-12
- Added initial support for fuel consumption for Evolution Air Cooled Natural Gas units. Note: NG 30 day fuel consumption is located on the maintenance page. Fuel gauge is supported for NG.

## V1.13.24 - 2019-07-10
- Added URL to logout if using secure web settings: https://addressofpi/logout

## V1.13.23 - 2019-07-07
- Changes to all unicode comments to be stored in service journal

## V1.13.22 - 2019-07-06
- Added config file options to set nominal line voltage values for non US grids (Evo and Nexus only)

## V1.13.21 - 2019-06-28
- Slight modification to the logic used when detecting the type of alarm for Evolution controllers due to the last alarm code register not updating after a Service Due alarm.

## V1.13.20 - 2019-06-26
- Added option "Ignore Unknown Values" that will ignore unknown values of modbus register 0001 for Evolution 2.0 controllers. This setting is in the advanced section in the web interface.

## V1.13.19 - 2019-06-25
- Added more logging for better diagnostics when fatal errors occur (e.g. invalid serial port specified)
- Corrected one problem with invalid file name for log file when sending logs

## V1.13.18 - 2019-06-19
- Fixed problem in gentankutil.py

## V1.13.17 - 2019-06-19
- Added support for external fuel tank API for tankutility.com propane fuel monitor

## V1.13.16 - 2019-06-16
- Changed warning message when power log is reaching size limit
- Displayed estimated fuel on the Maintenance page on EvoLC diesel units that support fuel sensor
- Added power log file size details to Monitor page

## V1.13.15 - 2019-06-15
- Corrected problem logging with gengpioin.py

## V1.13.14 - 2019-06-14
- Corrected problem with gengpioin.py and gengpio.py that were introduced in V1.13.08

## V1.13.13 - 2019-06-11
- Updated default values for current calculation for Evolution Liquid Cooled
- Added option in serial library for seven data bits (current unused in this project)
- Corrected minor issue in mail library when used in stand alone mode

## V1.13.12 - 2019-05-22
- Added low bandwidth page: http://IPADDRESS:8000/low

## V1.13.11 - 2019-05-20
- Fix that will hopefully correct issues when upgrading from 1.13.07 or earlier

## V1.13.10 - 2019-05-19
- Increased delay when copying files during upgrades from 1.13.07 or earlier. This should not effect upgrades that are after V1.13.07

## V1.13.09 - 2019-05-12
- Created delay after file copy to allow file to settle before restarting on first restart after upgrade.

## V1.13.08 - 2019-05-08
- To be extra safe, please perform a backup on your data before installing the update as some files will be moved during the upgrade
- Added alarm codes for Nexus
- Update to support multiple genmon instances
- move all working copies of conf files from /etc/ to /etc/genmon/
- moved kwlog.txt, outage.txt and service journal data file from ./genmon to /etc/genmon/
- Added new command line options to most programs to pass in full path to config files
- Added TCP port command line option to ClientInterface.py
- updates to the wiki
- modified command line options for genmonmaint.sh to support alternate config locations. See https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmonmaintsh for details

## V1.13.07 - 2019-05-03
- Fixed bug in genexercise.py that prevented a "Start/Transfer" exercise cycle from stoping

## V1.13.06 - 2019-05-03
- Fixed problem with Nexus controllers not properly showing "Start and Transfer" button in web interface
- Modified Enhanced Exercise add on program to support Nexus controllers

## V1.13.05 - 2019-05-03
- Corrected typo in gengpio.py
- Added additional error checking in genmon.js

## V1.13.04 - 2019-05-01
- Corrected display anomaly in web UI

## V1.13.03 - 2019-04-30
- Removed the ability to set quiet mode for Nexus and Air Cooled Evolution as this does not appear to be supported in the firmware.
s
## V1.13.02 - 2019-04-26
- Improved startup error handling to better respond if there are serial issues preventing the software from identifying the controller

## V1.13.01 - 2019-04-22
- Corrected one typo
- Added code for debugging purposes

## V1.13.00 - 2019-04-20
- Added Add On for Email to SMS support

## V1.12.33 - 2019-04-17
- Support for Evolution Liquid Cooled Three phase

## V1.12.32 - 2019-03-30
- Added H-100 and G-Panel Regulator, Governor and Engine data
- Added new alarm code for Nexus

## V1.12.31 - 2019-03-29
- Added more register reads in H and G Panel controller (need register submissions to complete adding more data to UI)
- Corrected bug in /OtherApps/modbusdump.py
- Update for 2008 model Pre-Nexus controllers (i.e. made in 2008 and do not have Nexus printed on them). Previously these controllers were not supported. See https://github.com/jgyates/genmon/wiki/Appendix-D-Known-Issues item 6 for more details.

## V1.12.30 - 2019-03-20
- H and G Panel update to address log responsiveness

## V1.12.29 - 2019-03-19
- Add user defined URL to email messages (see advanced page)
- Modified H-100 email format to include explanation of email

## V1.12.28 - 2019-03-18
- Update for H and G Panel remote start / stop commands

## V1.12.27 - 2019-03-15
- Corrected problem with genercise.py to reduce unneeded writing to log file.

## V1.12.26 - 2019-03-12
- Initial support for HTS, MTS, STS transfer switches for H-Panel and G-Panel controllers

## V1.12.25 - 2019-03-10
- Added the ability to use floating point values for run hours in the service journal

## V1.12.24 - 2019-03-08
- Remove Line State for G Panel and H Panel if Smart Transfer Switch option is enabled

## V1.12.23 - 2019-03-06
- Minor update to email password validation
- Change to allow test email to be sent without a password
- Added option in Evolution Enhanced Exercise Add On to allow use of generator time instead of system time.

## V1.12.22 - 2019-03-02
- Fix bug in H-Panel code that was introduced with V1.12.21

## V1.12.21 - 2019-02-25
- Added Service Journal for creating a user journal of service and repair activities
- Modified backup to  include the Service Journal.
- Added new Add On functionality for enhanced exercise features (Transfer Exercise). This is available for Evolution Controllers only.
- Updated gengpio.py to add GPIO pins for Monitor Health and Internet Connectivity Status

## V1.12.20 - 2019-02-24
- Updated alarm data for H-Panel for Emergency Stop

## V1.12.19 - 2019-02-21
- Added sender name in email settings
- Fixed test email functional to support disabling TLS

## V1.12.18 - 2019-02-08
- Added battery check service due date for EvoAC

## V1.12.17 - 2019-02-07
- Initial update for maintenance log feature. GUI still needs work.
- Corrected the display of the Run/Event log and Alarm log for the H-Panel and G-Panel Industrial controllers. This now displays the logs with the newest entries first.

## V1.12.16 - 2019-02-02
- Removed reset alarm from web interface for EvoAC as more testing is needed on this feature.

## V1.12.15 - 2019-01-25
- Added option to disable TLS encryption

## V1.12.14 - 2019-01-23
- Corrected issue with outage log reporting incorrect fuel usage for outages of zero duration

## V1.12.13 - 2019-01-22
- Added method to generate self signed key instead of using the Flask key by default. This will make Secure WebServer more reliable
- Corrected typo in /conf/gengpioin.conf

## V1.12.12 - 2019-01-21
- Fixed problem with outage notifications in mynotify.py (effects add on programs) introduced in 1.12.2
- Added more info relating to fuel estimation to help in troubleshooting issues.
- Fixed formatting issue with login page for secure web settings
- Improved message in low fuel warning email (only for controllers with fuel estimate calculations)

## V1.12.11 - 2019-01-15
- Added new alarm code for NexusLC

## V1.12.10 - 2019-01-09
- Added entry to outage log for fuel consumption if fuel consumption supported by your generator

## V1.12.9 - 2019-01-06
- Fixed one problem with genloader.py load ordering
- More updates for Python3 support

## V1.12.8 - 2019-01-06
- Updated install script to force pyowm version 2.9.0. Version 2.10 is python 3 only
- Minor update to genmon.js to better convert JSON to HTML

## V1.12.7 - 2019-01-02
- Update for gengpioin.py triggers, added software debounce option to UI
- Minor mod to genserv.py for debugging purposes
- Updated code that returns numeric values for MQTT so JSON is not parsed twice

## V1.12.6 - 2018-12-31
- Added additional debug print for troubleshooting
- Added new field for future features
- Corrected spacing in an existing log entry

## V1.12.5 - 2018-12-28
- Update to allow GPIO Input parameters for pull up/down resistor and GPIO input trigger

## V1.12.4 - 2018-12-28
- Fixed bug with openweathermap icon

## V1.12.3 - 2018-12-27
- Changed link to download openweathermap icon
- Added functionality to mynotify.py for future features

## V1.12.2 - 2018-12-23
- Changed format of JSON for better compatibility with external apps and exporting data
- Minor mods to issue template
- Corrected problem with simulation code
- Added feature to test the email send settings
- Fixed issue with graphic on logs page
- Added run hours in last 30 days on Maintenance page for system that support power log

## V1.12.1 - 2018-12-18
- Added error code for change air filter alarm

## V1.12.0 - 2018-12-13
- Python 3 updates, still recommend using Python 2.7 as it has been tested more, but this update allows for greater compatibility with Python 3.5

## V1.11.35 - 2018-12-13
- Minor update to EvoLC ambient temp sensor (see Unsupported Sensors)
- WIP updates for email test

## V1.11.34 - 2018-12-10
- Added more parameter validation for TankSize
- Updated favicon.ico for web interface
- Added code for future features
- Added fuel consumption polynomials for RG022,RG027,RG032,RG038,RG048

## V1.11.33 - 2018-12-10
- Corrected bug in error handling in mymail.py

## V1.11.32 - 2018-12-09
- Fixed bug in CurrentDivider not accepting a decimal value between 0 and 1

## V1.11.31 - 2018-12-08
- Added SSL/TLS option for MQTT add on program (genmqtt.py)

## V1.11.30 - 2018-12-05
- Created button on About page to download configuration files for backup purposes

## V1.11.29 - 2018-12-02
- Fixed on bug for fuel level reporting

## V1.11.28 - 2018-11-29
- WIP updates for Python3

## V1.11.27 - 2018-11-25
- Added Liquid Cooled Fuel consumption curves for RD015, RD030 and RD050
- Update for low fuel notifications for EvoLC

## V1.11.26 - 2018-11-22
- Added option for EvoLC Diesel to use fuel sensor data for Fuel Gauge

## V1.11.25 - 2018-11-21
- Added Fuel Level Sensor reading for EvoLC Diesel Units on Maintenance page
- Readability updates and fixed typo in comments

## V1.11.24 - 2018-11-14
- Minor update for EvoLC current / power calculation

## V1.11.23 - 2018-11-13
- Minor update to improve EvoAC current reading by reducing erroneous momentary current values.

## V1.11.22 - 2018-11-07
- Minor update to include program run duration time in data submitted in automated feedback error reporting
- Added missing tooltip on advanced page

## V1.11.21 - 2018-11-06
- Added advanced option to subtract fuel form reported fuel estimate. See https://github.com/jgyates/genmon/wiki/Appendix-8-Monitoring-Fuel-and-Power-Usage
- Added email warning when estimated fuel in tank reaches 20% and 10%
- Corrected potential problem with a warning email about the power log being sent multiple times

## V1.11.20 - 2018-11-06
- Updated current calculation algorithm for Evolution Liquid Cooled. See https://github.com/jgyates/genmon/wiki/Appendix-D-Known-Issues for additional details.

## V1.11.19 - 2018-10-31
- Added email notice when communications with controller has been lost (and restored)
- Corrected one minor issue with mynotify.py
- Improvement to H-100 / G-Panel handling of string data
- Update for PowerPack, enabled fuel monitoring (if supported by controller)
- Improved bounds checking on modbus protocol

## V1.11.18 - 2018-10-29
- Initial support for Generac G-Panel Industrial Generators
- Update for H-100 Industrial Generators
- Minor update to Current  / Power calculation on Evolution. This will potentially fix some system that were not reporting Current and Power properly

## V1.11.17 - 2018-10-29
- Removed 'sudo' from wireless stats check

## V1.11.16 - 2018-10-29
- Added advanced (genmon.conf) to use the absolute value of the CT reading when making current calculations.

## V1.11.15 - 2018-10-28
- Optimized fuel and power log file system reads
- Added additional debug prints for troubleshooting Current Output on some systems

## V1.11.14 - 2018-10-27
- Added advanced page for web UI

## V1.11.13 - 2018-10-26
- Minor update for Power Pact, removed Service Due data

## V1.11.12 - 2018-10-25
- Initial support for Evolution Power Pact

## V1.11.11 - 2018-10-23
- Removed Reset Alarm remote command for Nexus Controllers in the web interface. Does not appear to work on Nexus. The command is still there if using ClientInterface.py on the command line if anyone is interested in testing this on a Nexus.
- Non functional modifications to H-100 code to prep for new features.

## V1.11.10 - 2018-10-22
- Minor update to reporting of engine state for H-100
- Update for unit test functions
- Improved format of register submission to facilitate testing
- Fixed one bug introduced in 1.11.9 for Nexus / Evo
- Minor mod to battery gauge, now goes to zero volts instead of 10 on the low end

## V1.11.9 - 2018-10-21
- Updates for H-100
- H-100 Log Entries
- Alarm Acknowledge added
- Updated modbus modules to better support modbus file reads
- Corrected problem with reset alarm command on Evo/Nexus
- Added option to disable power log and current output display

## V1.11.8 - 2018-10-16
- Improvements for genmqtt.py to allow for integer and float values to be passed as JSON strings
- Added option for Smart Transfer Switch. This will disable the weekly exercise and remote start in the UI since the transfer switch will handled this.

## V1.11.7 - 2018-10-13
- Add new remote command to reset the current alarm (see  Maintenance page)
- Fixed bug in power log for H-100, if you experience problems, reset the power log or delete the file kwlog.txt and restart.
- Moved Update Software in the web interface to the About page
- Moved Submit Registers in the web interface to the About page
- Added Submit Log Files button on the About page
- Added change log to the web interface About page

## V1.11.6 - 2018-10-13
- Changed loading method in genloader.py to work around I/O error with Flask library. As a result the output of the flask library is redirected to /dev/null so it will not be displayed on the console. If you started the software manually from the console and then exited the console and attempted to restart from the web UI (with a settings change) the Flask library used by genserv.py would cause an exception (I/O error). This works around this issue.
- Added more error checking / logging in modbus protocol code. This makes serial over TCP more robust.
- Fixed minor issue in genlog.py
- Improved error logging in myclient.py

## V1.11.5 - 2018-10-12
- Removed restart on I/O error in genserv.

## V1.11.4 - 2018-10-11
- Corrected bug in type in genserv.py. Corrects problem with settings page not displaying.

## V1.11.2 - 2018-10-11
- Moved data files to /data directory
- Moved conf files to /conf directory (runtime still expected files in /etc)
- Moved kwlog2csv.py to OtherApps

## V1.11.1 - 2018-10-10
- Added option for smart_transfer_switch in genmon.conf

## V1.11.0 - 2018-10-9
- Added 'Add-On' and 'About' to web interface. 'Add-On' section allows enabling, disabling and setting options for add on programs

## V1.10.14 - 2018-10-8
- Corrected bug in H-100 set time / date function
- Minor updates for parameter checking for add on programs
- Increased delay in genloader.py after stopping and before starting modules on restart

## Changes post 1.10.0
- Added program genslack.py. This program will send notifications via the [Slack](www.slack.com) messaging service. Thanks @naterenbarger for this addition.
- Updated install script to support all add-on program library requirements
- Added support for Evolution 2.0
- Added support for serial over TCP/IP (additional hardware required) See [this page for details](https://github.com/jgyates/genmon/wiki/Appendix-F----Serial-over-IP)
- Added advanced Modbus error handling for H-100 controllers
