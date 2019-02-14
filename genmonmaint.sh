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

usepython3=false
pipcommand="pip"
pythoncommand="python"

#-------------------------------------------------------------------
function clean() {

  sudo rm $genmondir/genmonlib/*.pyc
}
#-------------------------------------------------------------------
function setup() {

  if [ $# -eq 0 ]; then
    usepython3=false
  elif [ $1 == "3" ]; then
    usepython3=true
  else
    usepython3=false
  fi

  if [ "$usepython3" = true ] ; then
    echo 'Setting up for Python 3.x...'
    pipcommand="pip3"
    pythoncommand="python3"
  else
    echo 'Setting up for Python 2.7...'
    pipcommand="pip"
    pythoncommand="python"
fi
}
#-------------------------------------------------------------------
# This function copy all config files to the ./etc directory
function copyconffiles() {
    sudo cp $genmondir/conf/*.conf /etc
}
#-------------------------------------------------------------------
# This function will update the pip libraries used
function updatelibraries() {

  sudo $pipcommand install crcmod -U
  sudo $pipcommand install configparser -U
  sudo $pipcommand install pyserial -U
  sudo $pipcommand install Flask -U
  if [ "$usepython3" = true ] ; then
    sudo $pipcommand install pyowm -U
  else
    sudo $pipcommand install pyowm==2.9.0 -U
  fi
  sudo $pipcommand install pytz -U
  sudo $pipcommand install pyopenssl  -U
  sudo $pipcommand install twilio -U
  sudo $pipcommand install chump -U
  sudo $pipcommand install paho-mqtt -U
}

#-------------------------------------------------------------------
# This function will setup the serial port
function setupserial() {
  pushd $genmondir
  cd OtherApps
  sudo $pythoncommand serialconfig.py -e
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

    # possibly use "sudo easy_install3 -U pip"
    sudo apt-get update
    if [ "$usepython3" = true ] ; then
      sudo apt-get install python3-pip
    else
      sudo apt-get install python-pip
    fi
    sudo $pipcommand install crcmod
    sudo $pipcommand install configparser
    sudo $pipcommand install pyserial
    sudo $pipcommand install Flask
    if [ "$usepython3" = true ] ; then
      sudo $pipcommand install pyowm
    else
      sudo $pipcommand install pyowm==2.9.0
    fi
    sudo $pipcommand install pytz
    sudo apt-get install build-essential libssl-dev libffi-dev python-dev
    sudo $pipcommand install pyopenssl
    sudo $pipcommand install twilio
    sudo $pipcommand install chump
    sudo $pipcommand install paho-mqtt
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
    sudo cp maintlog.json ./genmon_backup
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

# setup must be run first
setup $2
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
    installgenmon  "prompt"
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
    updatelibraries
    ;;
  installnp)        # install with no prompt
    installgenmon "noprompt"
    updatecrontab
    ;;
  clean)
    clean
    ;;
  *)
    echo "No valid command given. Specify 'backup', 'clean', 'update', 'install' or 'updatelibs' on command line"
    #
    ;;
esac

exit 0
