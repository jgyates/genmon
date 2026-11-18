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
in the configuration directory will not be overwritten.  \
Continue? (y/n)  "

usepython3=true
pipoptions="--prefer-binary"
pythoncommand="python3"
OPTIND=1         # Reset in case getopts has been used previously in the shell.
config_path="/etc/genmon/"
restore_file="genmon_backup.tar.gz"
log_path="/var/log/"
install_opt=false
backup_opt=false
restore_opt=false
log_opt=false
refresh_opt=false
update_opt=false
noprompt_opt=false
cleanpython_opt=false
copyfiles_opt=false
update_os=false
managedpackages=false
configfilescopied=false
useserial=true
operating_system="Unknown"
is_raspbian=true

#-------------------------------------------------------------------------------
check_os(){

  source /etc/os-release
  operating_system=$NAME
  echo "The operating system is: $NAME"
  echo "OS version is: $VERSION_ID"
  if [[ $operating_system == *"Ubuntu"* ]]; then
     is_raspbian=false
  fi

}

#-------------------------------------------------------------------------------
is_pi () {
  ARCH=$(dpkg --print-architecture)
  if [ "$ARCH" = "armhf" ] || [ "$ARCH" = "arm64" ] ; then
    return 0
  else
    return 1
  fi
}
#-------------------------------------------------------------------------------
is_pifive() {
  grep -q "^Revision\s*:\s*[ 123][0-9a-fA-F][0-9a-fA-F]4[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$" /proc/cpuinfo
  return $?
}

#-------------------------------------------------------------------------------
function env_activate() {

  if [ "$managedpackages" = true ] ; then
    source $genmondir/genenv/bin/activate
  fi
}
#-------------------------------------------------------------------------------
function env_deactivate() {
  if [ "$managedpackages" = true ] ; then
    deactivate
  fi
}
#-------------------------------------------------------------------------------
function checkmanagedpackages() {

  #  /usr/lib/python3.11/EXTERNALLY-MANAGED
  pythonmajor=$($pythoncommand -c 'import sys; print(sys.version_info.major)')
  pythonminor=$($pythoncommand -c 'import sys; print(sys.version_info.minor)')
  managedfile="/usr/lib/python$pythonmajor.$pythonminor/EXTERNALLY-MANAGED"

  if [ -f $managedfile ]; then
      managedpackages=true
      echo "Managed system packages found"
      sudo apt-get -yqq install python3-venv
      if [ ! -d $genmondir/genenv ]; then
        # create the virtual environment 
        echo "Setting up virtual python environment for genmon"
        $pythoncommand -m venv $genmondir/genenv
      else
        echo "Python virtual environment found"
      fi
      pythoncommand="$genmondir/genenv/bin/python"
  fi
}

#-------------------------------------------------------------------------------
function cleanpython() {

  echo "Removing *.pyc files..."
  sudo rm $genmondir/genmonlib/*.pyc
  echo "Done."
}
#-------------------------------------------------------------------------------
function checkpython() {

  if command -v $pythoncommand >/dev/null 2>&1; then
    echo "Python is installed."
  else
    echo "Python is not present on this system. Genmon requires python." >&2 && exit 1
  fi

}
#-------------------------------------------------------------------------------
function setuppython3() {

  if [ $# -eq 0 ]; then
    usepython3=false
  elif [ $1 == "3" ]; then
    usepython3=true
  elif [ $1 == "2" ]; then
    usepython3=false
  else
    usepython3=false
  fi

  if [ "$usepython3" = true ] ; then
    echo 'Setting up for Python 3.x...'
    pythoncommand="python3"
    linetoadd="$linetoadd -p 3 "
  else
    echo 'Setting up for Python 2.7...'
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
  sudo $pythoncommand -m pip install --upgrade -r $genmondir/requirements.txt -U $pipoptions
  installgpio
  echo "Done."
}

#-------------------------------------------------------------------------------
# Install the GPIO library. rpi-lgpio provides the RPi.GPIO API on top of lgpio
# and works on all Pi models (required on the Pi 5). Fall back to the original
# RPi.GPIO if lgpio can not be installed (e.g. older OS without liblgpio-dev).
function installgpio() {

  echo "Installing GPIO library...."
  # needed to build lgpio from source if no binary wheel exists; may not exist on older OS
  sudo apt-get -yqq install liblgpio-dev || echo "liblgpio-dev not available on this OS"

  # RPi.GPIO and rpi-lgpio install the same module files, so they can not coexist
  if sudo $pythoncommand -m pip show RPi.GPIO >/dev/null 2>&1; then
    echo "Removing RPi.GPIO (replacing with rpi-lgpio)"
    if ! sudo $pythoncommand -m pip uninstall -y RPi.GPIO >/dev/null 2>&1; then
      # pip can not remove RPi.GPIO installed by the OS package manager (e.g.
      # python3-rpi.gpio on Bullseye and older, where no managed python
      # environment is used). RPi.GPIO works on these systems, so keep it.
      # The Pi 5 requires Bookworm (managed environment), so it never gets here.
      echo "RPi.GPIO was installed by the OS and can not be removed by pip, keeping it"
      return 0
    fi
    sudo $pythoncommand -m pip uninstall -y rpi-lgpio >/dev/null 2>&1
  fi

  if sudo $pythoncommand -m pip install --upgrade rpi-lgpio $pipoptions && \
     sudo $pythoncommand -c "import lgpio, RPi.GPIO" >/dev/null 2>&1; then
    echo "Installed rpi-lgpio"
    return 0
  fi

  if is_pifive; then
    echo "ERROR: rpi-lgpio could not be installed. GPIO add-ons will not work on a Raspberry Pi 5."
    return 1
  fi

  echo "rpi-lgpio not available on this system, falling back to RPi.GPIO"
  sudo $pythoncommand -m pip uninstall -y rpi-lgpio >/dev/null 2>&1
  sudo $pythoncommand -m pip install --upgrade RPi.GPIO $pipoptions
}

#-------------------------------------------------------------------------------
# This function will setup the serial port
function setupserial() {
  pushd $genmondir || return 1
  cd OtherApps || return 1
  # we will leave bluetooth on. Pi4 and earlier devices the serial port 
  # has a conflict unless you use the -b option
  sudo $pythoncommand serialconfig.py -e -b
  echo "Finished setting up the serial port."
  popd || return 1
}

#-------------------------------------------------------------------------------
# This function will install rpirtscts program needed for the LTE modem
function installrpirtscts() {
    echo "Installing rpirtscts..."
    pushd $genmondir || return 1
    cd ~ || return 1
    git clone https://github.com/mholling/rpirtscts.git
    cd rpirtscts || return 1
    make
    sudo cp ./rpirtscts /usr/local/bin/rpirtscts
    echo "Finished installing rpirtscts."
    popd || return 1
}
#-------------------------------------------------------------------------------
# This function will install the required libraries for genmon
function installgenmon() {

    echo "Installing genmon package requirements...."
    # possibly use "sudo easy_install3 -U pip"
    sudo apt-get -yqq update
    if [ "$usepython3" = true ] ; then
      sudo apt-get -yqq install python3-pip
    else
      sudo apt-get -yqq install python-pip
    fi
    if [ "$usepython3" = true ] ; then
      sudo apt-get -yqq install build-essential libssl-dev libffi-dev python3-dev cargo swig
    else
      sudo apt-get -yqq install build-essential libssl-dev libffi-dev python-dev cargo swig
    fi
    sudo apt-get -yqq install cmake
    # upgrade setuptools for the environment
    sudo $pythoncommand  -m pip install --upgrade setuptools

    sudo $pythoncommand -m pip install -r $genmondir/requirements.txt $pipoptions
    installgpio

    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    installrpirtscts

    if [ -z "$2" ] && [ $1 != "noprompt" ]; then    # Is parameter #1 zero length?
        read -p "Copy configuration files to $config_path? (y/n)?" choice
        case "$choice" in
          y|Y ) echo "Copying *.conf files to $config_path"
            copyconffiles
            configfilescopied=true
            ;; # yes choice
          n|N ) echo "Not copying *.conf to $config_path"
            ;; # no choice
          *)
            echo "Invalid choice, not copying conf files"
            ;;  # default choice
        esac
    else
        copyconffiles
        configfilescopied=true
    fi

    if [ "$configfilescopied" = true ] && [ -z "$2" ] && [ $1 != "noprompt" ]; then    # Is parameter #1 zero length?
      read -p "What type of connection from genmon to the controller? S=Onboard Serial, T=Network, Serial over TCP/IP Bridge, U=USB Serial (s/t/u)?" choice
      case "$choice" in
        s|S ) echo "Setting up serial onboard port..."
          if is_pifive || [ "$is_raspbian" = false ]; then
            # on a raspberry pi 5 or Ubuntu use /dev/ttyAMA0 instead of /dev/serial0
            echo "Using port /dev/ttyAMA0"
            sudo sudo sed -i 's/\/dev\/serial0/\/dev\/ttyAMA0/gI' /etc/genmon/genmon.conf
          fi
          ;; # serial, nothing to do if pi 4 or lower
        t|T ) echo "Network connection used for serial over TCP/IP. Not setting up onboard serial port"
          sudo sed -i 's/use_serial_tcp = False/use_serial_tcp = True/gI' /etc/genmon/genmon.conf
          useserial=false
          ;; # TCP/IP bridge
        u|U ) echo "USB serial. Not setting up onboard serial port, using USB serial /dev/ttyUSB0"
          sudo sudo sed -i 's/\/dev\/serial0/\/dev\/ttyUSB0/gI' /etc/genmon/genmon.conf
          useserial=false
          ;; # USB Connection
        *)
          echo "Invalid choice, defaulting to onboard serial"
          ;;  # default choice
      esac
    fi

    if [ "$useserial" = true ]; then
      if [ -z "$2" ] && [ $1 != "noprompt" ]; then    # Is parameter #1 zero length?
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
    fi
    echo "Done."
}

#-------------------------------------------------------------------------------
function updatecrontab() {

    # shellcheck disable=SC2024  # root's crontab, saved to a temp file
    sudo crontab -l > $tempfile
    result=$(grep -i "startgenmon.sh" $tempfile)
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
# archive log files
function archivelogs() {

    echo "Archive log files from $log_path ..."
    cd $genmondir || return 1
    sudo rm -r genmon_logs
    sudo rm genmon_logs.tar.gz
    mkdir genmon_logs
    sudo cp "$log_path"genmon.log ./genmon_logs
    sudo cp "$log_path"genserv.log ./genmon_logs
    sudo cp "$log_path"mymail.log ./genmon_logs
    sudo cp "$log_path"myserial.log ./genmon_logs
    sudo cp "$log_path"mymodbus.log ./genmon_logs
    sudo cp "$log_path"gengpio.log ./genmon_logs
    sudo cp "$log_path"gengpioin.log ./genmon_logs
    sudo cp "$log_path"gensms.log ./genmon_logs
    sudo cp "$log_path"gensms_modem.log ./genmon_logs
    sudo cp "$log_path"genmqtt.log ./genmon_logs
    sudo cp "$log_path"genmqttin.log ./genmon_logs
    sudo cp "$log_path"genpushover.log ./genmon_logs
    sudo cp "$log_path"gensyslog.log ./genmon_logs
    sudo cp "$log_path"genloader.log ./genmon_logs
    sudo cp "$log_path"myserialtcp.log ./genmon_logs
    sudo cp "$log_path"genlog.log ./genmon_logs
    sudo cp "$log_path"genslack.log ./genmon_logs
    sudo cp "$log_path"gencallmebot.log ./genmon_logs
    sudo cp "$log_path"genexercise.log ./genmon_logs
    sudo cp "$log_path"genemail2sms.log ./genmon_logs
    sudo cp "$log_path"gencentriconnect.log ./genmon_logs
    sudo cp "$log_path"genhomeassistant.log ./genmon_logs
    sudo cp "$log_path"gentankutil.log ./genmon_logs
    sudo cp "$log_path"genalexa.log ./genmon_logs
    sudo cp "$log_path"gensnmp.log ./genmon_logs
    sudo cp "$log_path"gentemp.log ./genmon_logs
    sudo cp "$log_path"gentankdiy.log ./genmon_logs
    sudo cp "$log_path"gengpioledblink.log ./genmon_logs
    sudo cp "$log_path"gencthat.log ./genmon_logs
    sudo cp "$log_path"genmopeka.log ./genmon_logs
    sudo cp "$log_path"gencustomgpio.log ./genmon_logs
    sudo cp "$log_path"gensms_voip.log ./genmon_logs
    sudo cp "$log_path"genneevo.log ./genmon_logs
    sudo cp "$log_path"genhalink.log ./genmon_logs
    sudo cp "$log_path"genhubitat.log ./genmon_logs

    tar -zcvf genmon_logs.tar.gz genmon_logs/
    sudo rm -r genmon_logs
    echo "Done."
}
#-------------------------------------------------------------------------------
# restore genmon
function restoregenmon() {

    echo "Restore genmon..."
    echo "Restore source: $restore_file"
    echo "Restore destination: $config_path"
    cd $genmondir || return 1

    current_time=$(date '+%Y-%m-%d:%H:%M:%S')
    
    RESTORE_HISTORY="$config_path"restore.txt
    if [ ! -f "$RESTORE_HISTORY" ]; then
      echo "$RESTORE_HISTORY does not exist. Creating.."
      sudo touch $RESTORE_HISTORY
    fi
    sudo sh -c "printf '%s\n' $config_path >> $RESTORE_HISTORY"
    sudo sh -c "printf '%s\n' $restore_file >> $RESTORE_HISTORY"
    sudo sh -c "printf '%s\n' $current_time >> $RESTORE_HISTORY"

    base_filename="${restore_file##*/}"

    echo "$base_filename"


    # echo copy restore archive to a temp folder
    if [[ -d temp_restore ]]; then
      echo removing temp_restore
      sudo rm -r temp_restore
    fi

    mkdir temp_restore 
    sudo mv $restore_file ./temp_restore
    cd temp_restore || return 1
    sudo tar -xzf $base_filename
    sudo cp -r ./genmon_backup/* $config_path
    cd ..
    sudo rm -r temp_restore
}
#-------------------------------------------------------------------------------
# backup genmon
function backupgenmon() {

    echo "Backup genmon..."
    cd $genmondir || return 1
    sudo rm -r genmon_backup
    sudo rm genmon_backup.tar.gz
    mkdir genmon_backup

    sudo cp -r "$config_path"*  ./genmon_backup
    # PIDs of running programs, not settings
    sudo rm -f ./genmon_backup/genloader.pids
    sudo tar -zcvf genmon_backup.tar.gz genmon_backup/
    sudo rm -r genmon_backup
    echo "Done."
}
#-------------------------------------------------------------------------------
function githubhash(){
  cd $genmondir || return 1
  git rev-parse --short HEAD
}
#-------------------------------------------------------------------------------
# update genmon from the github repository
# this function assumes you have downloaded the project from github
function updategenmon() {

    echo "Updating genmon..."
    cd $genmondir || return 1
    current_time=$(date '+%Y-%m-%d:%H:%M:%S')
    
    UPDATE_HISTORY="$config_path"update.txt
    if [ ! -f "$UPDATE_HISTORY" ]; then
      echo "$UPDATE_HISTORY does not exist. Creating.."
      sudo touch $UPDATE_HISTORY
    fi

    git config --global --add safe.directory '*'
    git fetch origin
    git reset --hard origin/master
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    sudo chown -R "$(stat -c "%U" "$genmondir")" "$genmondir"
    sudo chgrp -R "$(stat -c "%G" "$genmondir")" "$genmondir"

    sudo sh -c "printf '%s\n' $current_time >> $UPDATE_HISTORY"
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
  echo "  -t           Specify full path of the backup to restore"
  echo "  -r           Refresh (update) required libraries"
  echo "  -u           Update genmon to the latest version"
  echo "  -v           Display github hash for current source tree"
  echo "  -C           Remove *.pyc files (clean pre-compiled python files)"
  echo "  -n           Do not prompt for Y/N, assume yes"
  echo "  -c           Specify full path to config file directory"
  echo "  -p           Specify 2 or 3 for python version. 2 is default"
  echo "  -s           Just copy conf files"
  echo "  -l           Specify the full path of the log directory to archive"
  echo "  -f           Update OS software and apt repository flags if needed"
  echo "  -h           Display help"
  echo ""
}

#-------------------------------------------------------------------------------
# main entry

while getopts ":hfp:bt:iruvnc:Csl:" opt; do
  #echo $OPTARG
  case ${opt} in
    h )
      printhelp
      exit 0
      ;;
    f )
      update_os=true
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
    l )
      log_path=$OPTARG
      log_opt=true
      ;;
    s )
      copyfiles_opt=true
      ;;
    b )
      backup_opt=true
      ;;
    t )
      restore_opt=true
      restore_file=$OPTARG
      ;;
    i )
      install_opt=true
      ;;
    r )
      refresh_opt=true
      ;;
    v ) 
      githubhash
      exit 0
      ;;
    u )
      update_opt=true
      ;;
    n )
      noprompt_opt=true
      ;;
    \? )
      echo ""
      echo "Invalid Option: -$OPTARG" 1>&2
      printhelp
      exit 1
      ;;
  esac
done
shift $((OPTIND -1))

echo ""
if [ "$update_os" = true ] ; then
   sudo apt-get --allow-releaseinfo-change update && sudo apt-get upgrade
fi

check_os
checkpython
checkmanagedpackages

if [ "$install_opt" = true ] ; then
  if [ "$noprompt_opt" = true ] ; then
    env_activate
    installgenmon "noprompt"
    env_deactivate
    updatecrontab
  else
    read -n 1 -s -r -p "$installnotice"
    echo ""
    # install libraries
    env_activate
    installgenmon  "prompt"
    env_deactivate
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
  env_activate
  cleanpython
  env_deactivate
fi

if [ "$backup_opt" = true ] ; then
  backupgenmon
fi

if [ "$restore_opt" = true ] ; then
  restoregenmon
fi
if [ "$log_opt" = true ] ; then
  archivelogs
fi

if [ "$refresh_opt" = true ] ; then
  env_activate
  updatelibraries
  env_deactivate
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
