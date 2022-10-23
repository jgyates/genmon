# Information for using Pi's other than Raspberry
* WARNING - currently, none of the extensions or functionality that uses digital inputs/outputs on the GPIO will work as the RPi.GPIO library is Raspberry Pi only, it throws an exception if it detects a non-Raspberry board.
* I2C, SPI, and 1-Wire do not appear to use the RPi.GPIO library, so add-ons using those MIGHT work if the pins are available, but some boards have a subset of the 40-pin connector.
* Pin mappings and function indexes (GPIO-07 vs GPIO-04, UART0 vs UART2, I2C-0 vs I2C-1) may be different even if the pins are physically in the same location.
* Raspberry Pi OS adds the default user to a ton of groups that provide all GPIO related access, these permissions are not typically granted on any other OS.

## Renaming Users
Most non-Rasperry Pi's use usernames other than pi. You can use the default, or if you want to change it you can use the following lines. If you do, you may have to adjust other commands in provided scripts. If you want to change the username, it is highly recommended to do it before doing any other changes as if the account is in use it cannot be renamed.
* `usermod -l mynewusername -d /home/mynewusername -m myoldusername`
* `groupmod --new-name mynewusername myoldusername`

## NanoPi Neo Air-LTS and Neo Plus 2 (might work or be similar for other NanoPi's)
### Before installing GenMon
#### Setup the serial port
* login as root
* execute `sed -Ei 's/^(overlays=.*)/\1 uart1/' /boot/armbianEnv.txt` to enable UART1
* execute `cat /proc/tty/driver/serial` to verify that it is enabled, a reboot may be required and this can be run later

#### Get cryptography working
Cryptography doesn't install correctly or get recognized if this is done during the genmon install or as the regular user with or without sudo.  Install compilers and then install SSH and GIT while at it.
* execute `apt install -y git build-essential cargo gfortran libffi-dev libopenblas-dev libssl-dev openssh-client python3-dev python3-pip`
* upgrade pip to a newer version `pip3 install --upgrade pip`
* install pyopenssl which will compile cryptography, this can take up to 60 minutes. `pip3 install pyopenssl`

#### Add user to sudo and serial groups
`usermod -a -G sudo,dialout dietpi`

### GenMon install differences
* Select NO when genmon asks to configure the serial port.
* When it comes time for the serial test, execute with the correct serial port. `~/genmon/OtherApps/serialtest.py /dev/ttyS1`
* After the install finishes, update `sudo nano /etc/genmon/genmon.conf` and set the port line to `port = /dev/ttyS1`

## Rock Pi 4C Plus (might work or be similar for other Rock Pi's)
### Before installing GenMon
#### Setup the serial port
* edit `/boot/hw_intfc.conf`
  * update `intfc:uart2=off` to `intfc:uart2=on`
  * comment the line `intfc:dtoverlay=console-on-ttyS2`
* edit `/boot/extlinux/extlinux.conf`
  * remove `console=ttyFIQ0,1500000n8` and `console=ttyS2,1500000n8` from the line that looks like:
    * `append earlyprintk console=ttyFIQ0,1500000n8 rw init=/sbin/init rootfstype=ext4 rootwait  root=UUID=783271c5-9845-49fd-819f-a09107a2ec9d console=ttyS2,1500000n8`
#### Add user to serial groups
`sudo usermod -a -G tty,dialout rock`

### GenMon install differences
* Select NO when genmon asks to configure the serial port.
* When it comes time for the serial test, execute with the correct serial port. `~/genmon/OtherApps/serialtest.py /dev/ttyS2`
* After the install finishes, update `sudo nano /etc/genmon/genmon.conf` and set the port line to `port = /dev/ttyS2`
