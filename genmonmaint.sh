#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
linetoadd="@reboot sleep 30 && /bin/bash $genmondir/startgenmon.sh start"
tempfile='/tmp/gmtemp'
installnotice="This script will install libraries needed by genmon. \
This script assumes you have already downloaded the genmon project via 'git'. \
This script will optionally copy the config files to the /etc directory. This script \
will not test the serial port. This script requires internet access to download \
the needed libraries. Press any key to continue.  "
updatenotice="This script will update genmon to the latest version from the github repository. \
This script requires internet access. If you have modified any files in the genmon directory, \
they will be overwritten. Configuration files in the /etc directory will not be overritten.   \
Continue? (y/n)  "

#-------------------------------------------------------------------
# This function copy all config files to the ./etc directory
function copyconffiles() {
    sudo cp $genmondir/conf/*.conf /etc
}
#-------------------------------------------------------------------
# This function will update the pip libraries used
function updatelibraries() {
  local pipcmd=

  if [ $# -eq 0 ]; then
    pipcmd="pip"
  elif [ $1 == "3" ]; then
    echo "Installing for Python 3.x"
    pipcmd="pip3"
  else
    pipcmd="pip"
  fi
  sudo $pipcmd install crcmod -U
  sudo $pipcmd install configparser -U
  sudo $pipcmd install pyserial -U
  sudo $pipcmd install Flask -U
  sudo $pipcmd install pyowm==2.9.0 -U
  sudo $pipcmd install pytz -U
  sudo $pipcmd install pyopenssl  -U
  sudo $pipcmd install twilio -U
  sudo $pipcmd install chump -U
  sudo $pipcmd install paho-mqtt -U
}

#-------------------------------------------------------------------
# This function will setup the serial port
function setupserial() {
  pushd $genmondir
  cd OtherApps
  sudo python serialconfig.py -e
  echo "Finished setting up the serial port."
  popd
}

#-------------------------------------------------------------------
# This function will install rpirtscts program needed for the LTE modem
function installrpirtscts() {
    echo "Installing rpirtscts..."
    pushd $genmondir
    cd ~
    git clone git://github.com/mholling/rpirtscts.git
    cd rpirtscts
    make
    sudo cp ./rpirtscts /usr/local/bin/rpirtscts
    echo "Finished installing rpirtscts."
    popd
}
#-------------------------------------------------------------------
# This function will install the required libraries for genmon
function installgenmon() {

    local pipcmd=

    if [ -z "$2" ]; then
      pipcmd="pip"
    elif [ $2 == "3" ]; then
      echo "Installing for Python 3.x"
      pipcmd="pip3"
    else
      pipcmd="pip"
    fi
    sudo apt-get update
    sudo apt-get install python-pip
    sudo $pipcmd install crcmod
    sudo $pipcmd install configparser
    sudo $pipcmd install pyserial
    sudo $pipcmd install Flask
    sudo $pipcmd install pyowm==2.9.0
    sudo $pipcmd install pytz
    sudo apt-get install build-essential libssl-dev libffi-dev python-dev
    sudo $pipcmd install pyopenssl
    sudo $pipcmd install twilio
    sudo $pipcmd install chump
    sudo $pipcmd install paho-mqtt
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    installrpirtscts

    if [ -z "$2" ] || [ $1 == "prompt" ]; then    # Is parameter #1 zero length?
        read -p "Copy configuration files to /etc? (y/n)?" choice
        case "$choice" in
          y|Y ) echo "Copying *.conf files to /etc"
            copyconffiles
            ;; # yes choice
          n|N ) echo "Not copying *.conf to /etc"
            ;; # no choice
          *)
            echo "Invalid choice, not copying conf files"
            ;;  # default choice
        esac
    else
        copyconffiles
    fi
    if [ -z "$2" ] || [ $1 == "prompt" ]; then    # Is parameter #1 zero length?
      read -p "Setup the raspberry pi onboard serial port? (y/n)?" choice
      case "$choice" in
        y|Y ) echo "Setting up serial port..."
          setupserial
          ;; # yes choice
        n|N ) echo "Not setting up serial port"
          ;; # no choice
        *)
          echo "Invalid choice, not setting up serial port"
          ;;  # default choice
      esac
    else
        setupserial
    fi
}

#-------------------------------------------------------------------
function updatecrontab() {

    sudo crontab -l > $tempfile
    result=$(grep -i "startgenmon.sh" /tmp/gmtemp)
    if [ "$result" == "" ]
        then
            echo "Updating crontab..."
            echo "adding < $linetoadd > to crontab"
            echo "$linetoadd" >> $tempfile
            sudo crontab  $tempfile
        else
            echo "Crontab already contains genmon start script:"
            echo "$result"
        fi
}

#-------------------------------------------------------------------
# backup genmon
function backupgenmon() {

    echo "Backup genmon..."
    cd $genmondir
    sudo rm -r genmon_backup
    sudo rm genmon_backup.tar.gz
    mkdir genmon_backup
    mkdir ./genmon_backup/conf
    sudo cp /etc/genmon.conf ./genmon_backup/conf
    sudo cp /etc/mymail.conf ./genmon_backup/conf
    sudo cp /etc/genloader.conf ./genmon_backup/conf
    sudo cp /etc/genmqtt.conf ./genmon_backup/conf
    sudo cp /etc/genpushover.conf ./genmon_backup/conf
    sudo cp /etc/genslack.conf ./genmon_backup/conf
    sudo cp /etc/gensms.conf ./genmon_backup/conf
    sudo cp /etc/mymodem.conf ./genmon_backup/conf
    sudo cp outage.txt ./genmon_backup
    sudo cp kwlog.txt ./genmon_backup
    tar -zcvf genmon_backup.tar.gz genmon_backup/
    sudo rm -r genmon_backup
}
#-------------------------------------------------------------------
# update genmon from the github repository
# this function assumes you have downloaded the project from github
function updategenmon() {

    echo "Updating genmon..."
    cd $genmondir
    git fetch origin
    git reset --hard origin/master
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    sudo chown -R `stat -c "%U" $genmondir` $genmondir
    sudo chgrp -R `stat -c "%G" $genmondir` $genmondir
}

#-------------------------------------------------------------------
# main entry
case "$1" in
  update)

    read -p "$updatenotice" choice
    case "$choice" in
      y|Y ) updategenmon
        ;; # yes choice
      * ) echo "Not updating genmon"
        ;; # no choice
    esac
    ;;
  install)
    read -n 1 -s -r -p "$installnotice"
    echo ""
    # install libraries
    installgenmon  "prompt" $2
    # update crontab
    read -p "Start genmon on boot? (y/n)?" choice
    case "$choice" in
      y|Y ) echo "Updating crontab...."
        updatecrontab
        ;; # yes choice
      n|N ) echo "Not updating crontab."
        ;; # no choice
      *)
        echo "Invalid choice, not updating crontab.."
        ;;  # default choice
    esac

    ;;  # install
  backup)
    backupgenmon
    ;;
  updatenp)
    updategenmon
    ;;
  updatelibs)
    updatelibraries $2
    ;;
  installnp)        # install with no prompt
    installgenmon "noprompt" $2
    updatecrontab
    ;;
  *)
    echo "No valid command given. Specify 'backup','update', 'install' or 'updatelibs' on command line"
    #
    ;;
esac

exit 0
