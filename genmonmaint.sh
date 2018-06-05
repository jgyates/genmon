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
    sudo cp "$genmondir/genmon.conf" /etc
    sudo cp "$genmondir/mymail.conf" /etc
}
#-------------------------------------------------------------------
# This function will install the required libraries for genmon
function installgenmon() {

    sudo apt-get update
    sudo apt-get install python-pip
    sudo pip install crcmod
    sudo pip install configparser
    sudo apt-get install python-serial
    sudo pip install Flask
    sudo pip install pyowm
    sudo pip install pytz
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"

    if [ -z "$1" ]    # Is parameter #1 zero length?
        then
            read -p "Copy genmon.conf and mymail.conf to ./etc? (y/n)?" choice
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
  updatenp)
    updategenmon
    ;;
  installnp)        # install with no prompt
    installgenmon 1
    updatecrontab
    ;;
  *)
    echo "No valid command given. Specify 'update' or 'install' on command line"
    #
    ;;
esac

exit 0
