#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
linetoadd="@reboot sleep 30 && /bin/bash $genmondir/startgenmon.sh start"
tempfile='/tmp/gmtemp'
installnotice="This script will install libraries needed by genmon. \
This script assumes you have already downloaded the genmon project via 'git'. \
This script will optionally copy the config files to the configuration \
directory. This script will not test the serial port. This script requires \
internet access to download the needed libraries. Press any key to continue.  "
updatenotice="This script will update genmon to the latest version from the github \
repository. This script requires internet access. If you have modified any \
files in the genmon directory, they will be overwritten. Configuration files \
in the configuration directory will not be overritten.   \
Continue? (y/n)  "

usepython3=false
pipcommand="pip"
pythoncommand="python"
OPTIND=1         # Reset in case getopts has been used previously in the shell.
config_path="/etc/genmon/"
install_opt=false
backup_opt=false
refresh_opt=false
update_opt=false
noprompt_opt=false
cleanpython_opt=false
copyfiles_opt=false

#-------------------------------------------------------------------------------
function cleanpython() {

  echo "Removing *.pyc files..."
  sudo rm $genmondir/genmonlib/*.pyc
  echo "Done."
}
#-------------------------------------------------------------------------------
function setuppython3() {

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
    linetoadd="$linetoadd -p 3 "
  else
    echo 'Setting up for Python 2.7...'
    pipcommand="pip"
    pythoncommand="python"
fi
}
#-------------------------------------------------------------------------------
# This function copy all config files to the target install directory
function copyconffiles() {
    sudo mkdir "$config_path"
    sudo cp $genmondir/conf/*.conf "$config_path"
}
#-------------------------------------------------------------------------------
# This function will update the pip libraries used
function updatelibraries() {

  echo "Updating libraries...."
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
  sudo $pipcommand install pysnmp -U
  echo "Done."
}

#-------------------------------------------------------------------------------
# This function will setup the serial port
function setupserial() {
  pushd $genmondir
  cd OtherApps
  sudo $pythoncommand serialconfig.py -e
  echo "Finished setting up the serial port."
  popd
}

#-------------------------------------------------------------------------------
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
#-------------------------------------------------------------------------------
# This function will install the required libraries for genmon
function installgenmon() {

    echo "Installing...."
    # possibly use "sudo easy_install3 -U pip"
    sudo apt-get -yqq update
    if [ "$usepython3" = true ] ; then
      sudo apt-get -yqq install python3-pip
    else
      sudo apt-get -yqq install python-pip
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
    sudo apt-get -yqq install build-essential libssl-dev libffi-dev python-dev
    sudo $pipcommand install pyopenssl
    sudo $pipcommand install twilio
    sudo $pipcommand install chump
    sudo $pipcommand install paho-mqtt
    sudo $pipcommand install pysnmp

    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    installrpirtscts

    if [ -z "$2" ] || [ $1 == "prompt" ]; then    # Is parameter #1 zero length?
        read -p "Copy configuration files to $config_path? (y/n)?" choice
        case "$choice" in
          y|Y ) echo "Copying *.conf files to "$config_path""
            copyconffiles
            ;; # yes choice
          n|N ) echo "Not copying *.conf to "$config_path""
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
    echo "Done."
}

#-------------------------------------------------------------------------------
function updatecrontab() {

    sudo crontab -l > $tempfile
    result=$(grep -i "startgenmon.sh" /tmp/gmtemp)
    if [ "$result" == "" ]
        then
            echo "Updating crontab..."
            echo "adding < $linetoadd > to crontab"
            echo "$linetoadd" >> $tempfile
            sudo crontab  $tempfile
    elif [ "$result" != "$linetoadd" ]
        then
            echo "Crontab has an incorrect configuration, updating:"
            echo "$result"
            echo "to"
            echo "$linetoadd"
            sed -i "s~${result/\&\&/\\\&\\\&}~${linetoadd/\&\&/\\\&\\\&}~g" $tempfile
            sudo crontab $tempfile
        else
            echo "Crontab already contains genmon start script:"
            echo "$result"
        fi
}

#-------------------------------------------------------------------------------
# backup genmon
function backupgenmon() {

    echo "Backup genmon..."
    cd $genmondir
    sudo rm -r genmon_backup
    sudo rm genmon_backup.tar.gz
    mkdir genmon_backup
    sudo cp "$config_path"genmon.conf ./genmon_backup
    sudo cp "$config_path"mymail.conf ./genmon_backup
    sudo cp "$config_path"genloader.conf ./genmon_backup
    sudo cp "$config_path"genmqtt.conf ./genmon_backup
    sudo cp "$config_path"genpushover.conf ./genmon_backup
    sudo cp "$config_path"genslack.conf ./genmon_backup
    sudo cp "$config_path"gensms.conf ./genmon_backup
    sudo cp "$config_path"mymodem.conf ./genmon_backup
    sudo cp "$config_path"genemail2sms.conf ./genmon_backup
    sudo cp "$config_path"genexercise.conf ./genmon_backup
    sudo cp "$config_path"gengpioin.conf ./genmon_backup
    sudo cp "$config_path"outage.txt ./genmon_backup
    sudo cp "$config_path"kwlog.txt ./genmon_backup
    sudo cp "$config_path"maintlog.json ./genmon_backup
    tar -zcvf genmon_backup.tar.gz genmon_backup/
    sudo rm -r genmon_backup
    echo "Done."
}
#-------------------------------------------------------------------------------
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
    echo "Done."
}

#-------------------------------------------------------------------------------
function printhelp() {

  echo ""
  echo "Usage: "
  echo ""
  echo "    genmonmaint.sh <options>"
  echo ""
  echo "Options:"
  echo ""
  echo "  -i           Install genmon and required libraries"
  echo "  -b           Backup genmon configuration"
  echo "  -r           Refresh (update) required libraries"
  echo "  -u           Update genmon to the latest version"
  echo "  -C           Remove *.pyc files (clean pre-compiled python files)"
  echo "  -n           Do not prompt for Y/N, assume yes"
  echo "  -c           Specifiy full path to config file directory"
  echo "  -p           Use python 3 instead of python 2.7"
  echo "  -s           Just copy conf files"
  echo "  -h           Display help"
  echo ""
}

#-------------------------------------------------------------------------------
# main entry


while getopts ":hp:birunc:Cs" opt; do
  case ${opt} in
    h )
      printhelp
      exit 0
      ;;
    p )
      setuppython3 $OPTARG
      ;;
    c )
      config_path=$OPTARG
      linetoadd="$linetoadd -c $OPTARG"
      ;;
    C )
      cleanpython_opt=true
      ;;
    s )
      copyfiles_opt=true
      ;;
    b )
      backup_opt=true
      ;;
    i )
      install_opt=true
      ;;
    r )
      refresh_opt=true
      ;;
    u )
      update_opt=true
      ;;
    n )
      noprompt_opt=true
      ;;
    \? )
      echo "Invalid Option: -$OPTARG" 1>&2
      printhelp
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))


if [ "$install_opt" = true ] ; then
  if [ "$noprompt_opt" = true ] ; then
    installgenmon "noprompt"
    updatecrontab
  else
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
  fi
fi

if [ "$cleanpython_opt" = true ] ; then
  cleanpython
fi

if [ "$backup_opt" = true ] ; then
  backupgenmon
fi

if [ "$refresh_opt" = true ] ; then
  updatelibraries
fi

if [ "$update_opt" = true ] ; then

  if [ "$noprompt_opt" = true ] ; then
    updategenmon
  else
    read -p "$updatenotice" choice
    case "$choice" in
      y|Y ) updategenmon
        ;; # yes choice
      * ) echo "Not updating genmon"
        ;; # no choice
    esac
  fi
fi
if [ "$copyfiles_opt" = true ] ; then
  copyconffiles
fi



exit 0
