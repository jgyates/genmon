# Information for using DietPi to host GenMon.
This information was created using a NanoPi Neo Air-LTS and NanoPi Neo Plus 2.

## What won't work
* Currently, none of the extensions or functionality that uses digital inputs/outputs on the GPIO will not work as the RPi.GPIO library is Raspberry Pi only, it throws an exception if it detects a non-Raspberry board.
* I2C, SPI, and 1-Wire do not appear to use the RPi.GPIO library, so add-ons using those MIGHT work if the pins are available.  NanoPi stops at Pin 24, so hardware using Raspberry's SPI1 will not work.
* Mappings may be different, different boards have different chip manufacturers and the pinouts differ.  This is true for everything, not just digital IO pins.  Physically, Raspberry's UART0 is NanoPi's UART1.

## Getting started
Login as root, some of this first portion will not work under sudo, and unlike Raspberry Pi, DietPi uses very stripped down default Linux users.

### Renaming the user
It is absolutely not required to rename the user, but if you want to do so, now is the time when the user is not in use. Anything that refers to the DietPi user after this you will need to update as well. \
`usermod -l mynewusername -d /home/mynewusername -m dietpi` \
`groupmod --new-name mynewusername dietpi`

### Start installing
Add user to sudo and dialout (for serial access) groups, these are automatic with RPiOS but not DietPi \
`usermod -a -G sudo,dialout dietpi`
Next we need to enable the appropriate UART, this will depend on the board you have. The UART you need are the ones on physical pins 7 and 9. \
For NanoPi Neo's `sed -Ei 's/^(overlays=.*)/\1 uart1/' /boot/armbianEnv.txt` \
The following can immediately verify the required UART is enabled (the appropriate line should not be "unknown" or irq:0). You need to reboot before trying a loopback test, but you can do that after the root section. \
`cat /proc/tty/driver/serial` \
Next we need to get around some problems with the normal Cryptography install. We'll get rust, C++, fortran, and more all installed.  Also grabbing SSH/SCP and GIT while here. \
`apt install -y git build-essential cargo gfortran libffi-dev libopenblas-dev libssl-dev openssh-client python3-dev python3-pip` \
Next upgrade pip to a newer version than python3-pip installs. Yes you just installed pip, but there's a newer version anyway. \
`pip3 install --upgrade pip` \
Last action as root, install pyopenssl which will compile cryptography. For some reason if this is not done as root it will never be recognized as installed. Sudo is not sufficient.
`pip3 install pyopenssl` - warning, this takes quite awhile (30 to 60 minutes is expected). If you aren't sure, open a second SSH window (account doesn't matter) and run `top` to see the rust and gcc commands.

### GenMon install differences
Log out of root and log in as your regular user (DietPi or whatever you renamed the account). \
Follow the genmon instructions until you get to the serial loopback test. The test accepts an optional parameter for the serial port you need to test and the number will most likely line up with the UART number you used. \
For NanoPi Neo's `~/genmon/OtherApps/serialtest.py /dev/ttyS1` \
Now before starting GenMon the serial port needs to be manually changed in the config file. Open the file with: \
`sudo nano /etc/genmon/genmon.conf` \
Near the top you will see `port = /dev/serial0`, the serial0 needs to change to ttyS and the UART number. \
For NanoPi Neo's `port = /dev/ttyS1` \
Now you should be able to run `~/genmon/startgenmon.sh start` and have GenMon's UI load as normal.
