# Changelog
All notable changes to this project will be documented in this file. Major releases are documented [here](https://github.com/jgyates/genmon/releases)


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
