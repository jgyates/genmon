# Changelog
All notable changes to this project will be documented in this file. Major releases are documented [here](https://github.com/jgyates/genmon/releases)

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
- Update for 2008 model Pre-Nexus controllers (i.e. made in 2008 and do not have Nexus printed on them). Previously these controllers were not supported. See https://github.com/jgyates/genmon/wiki/Appendix-4-Known-Issues item 6 for more details.

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
- Updated current calculation algorithm for Evolution Liquid Cooled. See https://github.com/jgyates/genmon/wiki/Appendix-4-Known-Issues for additional details.

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
- Added support for serial over TCP/IP (additional hardware required) See [this page for details](https://github.com/jgyates/genmon/wiki/Appendix-6----Serial-over-IP)
- Added advanced Modbus error handling for H-100 controllers
