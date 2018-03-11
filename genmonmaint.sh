#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
linetoadd="@reboot sleep 30 && $genmondir/startgenmon.sh start"
tempfile='/tmp/gmtemp'
notice="This script will install libraries needed by genmon. \
This script assumes you have already downloaded the genmon project via 'git'. \
This script will NOT copy config files to the /etc directory or test the serial port. \
This script requires internet access to download the needed libraries. \
Press any key to continue."

function installgenmon() {

    sudo apt-get update
    sudo apt-get install python-pip
    sudo pip install crcmod
    #python -m crcmod.test
    sudo pip install pytz
    sudo pip install configparser
    sudo apt-get install python-serial
    sudo pip install Flask
    sudo chmod 775 "$genmondir/startgenmon.sh"

}

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

case "$1" in
  update)
    echo "Updating genmon..."
    git fetch origin
    git reset --hard origin/master
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    ;;
  install)
    read -n 1 -s -r -p "$notice"

    # install libraries
    installgenmon
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
  installnp)        # install with no prompt
    installgenmon
    updatecrontab
    ;;
  *)
    echo "No valid command given. Specify 'update' or 'install' on command line"
    #
    ;;
esac

exit 0

