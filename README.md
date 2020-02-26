# genmon
# Generator Monitoring Application using a Raspberry Pi and WiFi

This project will monitor a backup generator that utilizes the Generac Controllers over a WiFi or wired connection.  The following generator controllers are supported:

* Generac [Nexus](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Nexus_Controller.jpg) and [Evolution](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Evolution_Controller.jpg) (1.0 and 2.0) Controller (Used in Generac's residential product line)
* Honeywell and Eaton use the Generac Controllers, they call them Sync 1.0 (Nexus), Sync 2.0 (Evolution 1.0) and Sync 3.0 (Evolution 2.0)
* Generac [H-100](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/H-100_Controller.png) Industrial Controllers
* The H-100 controller is used in industrial generators from Generac and Eaton.
* Generac G-Panel based Industrial Controllers
* Generac PowerPact
* [2008 Era Generac Pre-Nexus](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/2008-PreNexusController.jpg) controllers. See [this](https://github.com/jgyates/genmon/wiki/Appendix-D-Known-Issues) page for more info.

The project is written mostly in python and has been tested with a Raspberry Pi 3 (Pi Zero, Pi Zero W, Pi 2 and Pi 3b+ have also been validated). To use this project you would need to create a physical enclosure for your raspberry pi and possibly [make a cable](https://github.com/jgyates/genmon/wiki/3.1--Making-a-Cable) to connect the raspberry pi to the generator controller or purchase [pre-assembled hardware](https://github.com/jgyates/genmon/wiki#pre-assembled-hardware). If you are comfortable doing these things and you have a backup generator that has a supported controller then this project may be of interest to you.

## Functionality
The software supports the following features:

* Monitoring of the generator to to detect and report the following:
    * Maintenance, Start / Stop and Alarm Logs (No Maintenance log exist on Nexus or Industrial Gens)
    * Display Generator Serial Number
    * Generator warnings and faults
    * Generator Status:
        * Engine State
            - Generator Switch State (Auto, On, Off)
            - Generator Engine State (Stopped, Starting, Exercising, Running Manual, Running Utility Loss, Stopped due to Alarm, Cooling Down)
            - Battery Voltage and Charging Status
            - Relay Output State: (Starter, Fuel Relay, Battery Charger, others for liquid cooled models)
            - Engine RPM, Hz and Voltage Output
            - Generator Controller Time
            - Line State
                - Utility Voltage Level
                - Transfer Switch State (Evolution liquid cooled model and Industrial Gens with HTS/MTS/STS Transfer Switches models only)
        * Outage Information
            - Time since last outage
            - Current Utility Voltage
            - Min and Max Utility Voltage since program started
        * Maintenance Information
            - Weekly Exercise time, day (biweekly and monthly if supported by your generator)
            - Hours till next scheduled service
            - Total Run Hours
            - Firmware and Hardware versions
        * Various statics from the generator monitor including time since program launched,
              MODBUS / serial communications health and program health.
* Email notification of :
    - Engine state change
    - Switch state change
    - Critical or Warning messages from the generator
- Web based application for viewing status of the generator
- Limited and Full Rights login for web interface
- SMS notifications of Generator state and power outages (via Twilio SMS API or Expansion Cellular Modem)
- Push notifications (via pushover.net)
- syslog logging of generator events
- Command Line application (all the functionality of email).
- Ability to set exercise time
- Ability to set generator time
- Ability to start, stop, exercise and start / active the transfer switch (i.e. power your house off the generator) remotely.
- Power, Current output on selected models
- Fuel consumption on selected models
- MQTT integration for third party home automation support
- Service Journal for logging maintenance, repair, etc
- Backup configuration files
- Enhanced Exercise options for Evolution/Nexus controller (Exercise Transfer Switch)
- Optional low bandwidth URL (http://ipaddress:8000/low)
- Firmware update notification for Evolution 2.0
- SNMP monitoring

![Generator Monitor Web Interface](https://raw.githubusercontent.com/jgyates/genmon/master/Diagrams/Web_UI_Status.png)

## Support
This project is free to use under the posted license agreement. It was written and is supported by one person with testing and some documentation supported by users of the software. I originally created this project for my personal use however I decided to make the project available to anyone interested, however I do accept tips via paypal:

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/cgi-bin/webscr?cmd=_donations&business=8Z4TSR22RLMWQ&lc=US&item_name=jgyates&item_number=jgyates&currency_code=USD&bn=PP%2dDonationsBF%3abtn_donate_LG%2egif%3aNonHosted)

## Pre-Assembled Hardware
This project is open source and ideal for those who like to tinker, however pre-assembled hardware and cables are available for anyone interested on via ebay.com from this source:

* [Pre-Assembled Pi and Cable using the built in internal antenna](https://www.ebay.com/itm/264200240940)
* [Pre-Assembled Pi and Cable with external wi-fi Antenna](https://www.ebay.com/itm/GenPi-Generac-Gen-Monitor-powered-by-GenMon-W-New-Easy-Setup-W-Ext-Ant/264297841518)
* [Pre-loaded SD Card](https://www.ebay.com/itm/GenPi-Generac-Monitor-by-GenMon-W-New-Setup-SDcard-w-Software-Only/264216642416)


## Testing
This software was written by one person with full time access to one generator. The primary model used for testing and development is a liquid cooled model with an evolution controller. The software was written with every intention of working on liquid and air-cooled models with the Evolution or Nexus controller however the author has not tested all scenarios. Testing has been performed with both Evolution and Nexus Controllers (air cooled and liquid cooled) with help of the community, however not all firmware versions and models have been tested.

In an effort to expand compatibility and functionality, from time to time I may use the [issue tracker](https://github.com/jgyates/genmon/issues) of this project to request input from people using the software. This input will will allow greater compatibility and new features to be added.

## Placement of your Raspberry Pi
If you have a large generator, the placement of your Raspberry Pi could be important due to [EMI](https://en.wikipedia.org/wiki/Electromagnetic_interference). Larger generators can produce more EMI when starting. For example a 48kw diesel generator may generate enough EMI to cause CRC errors when the generator starts if the Raspberry Pi enclosure is close to the engine. If you see CRC errors, check the validity of your cable. The errors may be caused by vibration of loose molex connectors in your cable. Also, if the Raspberry Pi enclosure is moved away from the engine and closer to the controller, this will likely reduce EMI if that is causing any CRC errors. EMI may not be an issue with smaller liquid cooled generators. There are several ways to resolve EMI issues however the best solution is dependent on your particular site needs (generator, how much space you need for your Pi, how much space you have available, etc). The project [wiki](https://github.com/jgyates/genmon/wiki/2:-Hardware) has information regarding a typical enclosure for the Raspberry Pi, however the example enclosure is not RF shielded.

## Connectivity
This application was written to be agnostic of the underlying network media (i.e. WiFi, Ethernet, etc). Testing and development was performed with WiFi. WiFi access points were connected to an uninterruptible power supply (UPS) so connectivity is not lost power is transferred from the utility to the generator.

## Setting Up Your Raspberry Pi (Serial Port)
Since there are several version of the raspberry Pi out and also several options regarding the operating system, I will leave this section somewhat minimal. I used a Raspberry Pi 3 with [Raspbian](https://www.raspberrypi.org/downloads/raspbian/) Lite. There are many resources on the web for setting up a Raspberry Pi so I will only include links for setting up the serial port. The Linux device name of the serial port changed or at least the symbolic link changed starting with the Raspberry Pi 3 from /dev/ttyAMA0 to /dev/serial0 so if you are using the on board serial port you will want to validate the device name and make sure genmon.conf reflects the serial device name of your Raspberry Pi and Linux distribution. The following two links are helpful in setting up the serial port on the Raspberry Pi:

[General Setup of the serial port for a Raspberry Pi](http://elinux.org/RPi_Serial_Connection)

[An updated serial port setup instructions based on the Raspberry Pi 3](http://spellfoundry.com/2016/05/29/configuring-gpio-serial-port-raspbian-jessie-including-pi-3/)

One important step is to validate your serial port is working properly. You can validate the serial port is working properly by using the program serialtest.py in this repository. To validate your serial port connect the RS-232 transmit to RS-232 receive and follow the instructions in the software section on [serialtest.py](https://github.com/jgyates/genmon/wiki/1:-Software-Overview#otherappsserialtestpy-optional). Also, you can validate your cable by connecting your cable to your serial port and connecting transmit to receive at the far end of the cable so you will be looping back through your cable, then repeat the serialtest.py test.

# Documentation
* [Genmon Project Wiki](https://github.com/jgyates/genmon/wiki)
