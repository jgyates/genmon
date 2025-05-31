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
in the configuration directory will not be overritten.  \
Continue? (y/n)  "

usepython3=true
pipcommand="pip3"
pipoptions=""
pythoncommand="python3"
OPTIND=1         # Reset in case getopts has been used previously in the shell.
config_path="/etc/genmon/"
log_path="/var/log/"
install_opt=false
backup_opt=false
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
  # This function sources /etc/os-release to determine the OS distribution
  # and version. It sets the 'operating_system' variable with the NAME
  # field from /etc/os-release and sets 'is_raspbian' to false if the
  # OS is Ubuntu, otherwise it defaults to true (implying Raspbian or other Debian derivative).
  source /etc/os-release
  operating_system=$NAME
  echo "The operating system is: $NAME"
  string='My long string'
  if [[ $operating_system == *"Ubuntu"* ]]; then
     is_raspbian=false
  fi

}

#-------------------------------------------------------------------------------
is_pi () {
  # This function checks the system architecture to determine if the script
  # is running on a Raspberry Pi. It returns 0 (true) if the architecture
  # is armhf or arm64, which are common for Raspberry Pi devices.
  ARCH=$(dpkg --print-architecture)
  if [ "$ARCH" = "armhf" ] || [ "$ARCH" = "arm64" ] ; then
    return 0
  else
    return 1
  fi
}
#-------------------------------------------------------------------------------
is_pifive() {
  # This function checks the /proc/cpuinfo file for a specific revision pattern
  # (e.g., "*4***" where * are hex chars) to identify if the hardware is a Raspberry Pi 5.
  # It returns 0 (true) if the pattern matches, indicating a Pi 5.
  grep -q "^Revision\s*:\s*[ 123][0-9a-fA-F][0-9a-fA-F]4[0-9a-fA-F][0-9a-fA-F][0-9a-fA-F]$" /proc/cpuinfo
  return $?
}

#-------------------------------------------------------------------------------
function env_activate() {
  # This function activates the Python virtual environment located in
  # '$genmondir/genenv' if the 'managedpackages' variable is true.
  # 'managedpackages' is set to true if the system is detected to use
  # an externally managed Python environment (e.g., Debian Bookworm onwards).
  if [ "$managedpackages" = true ] ; then
    source $genmondir/genenv/bin/activate
  fi
}
#-------------------------------------------------------------------------------
function env_deactivate() {
  # This function deactivates an active Python virtual environment if
  # 'managedpackages' is true. It's typically called after Python package
  # operations are completed within the virtual environment.
  if [ "$managedpackages" = true ] ; then
    deactivate
  fi
}
#-------------------------------------------------------------------------------
function checkmanagedpackages() {
  # This function checks if the Python environment is "externally managed"
  # which is common in newer OS distributions like Debian Bookworm.
  # It determines the Python major and minor version to locate the
  # EXTERNALLY-MANAGED file (e.g., /usr/lib/python3.11/EXTERNALLY-MANAGED).
  pythonmajor=$($pythoncommand -c 'import sys; print(sys.version_info.major)')
  pythonminor=$($pythoncommand -c 'import sys; print(sys.version_info.minor)')
  managedfile="/usr/lib/python$pythonmajor.$pythonminor/EXTERNALLY-MANAGED"

  # If the EXTERNALLY-MANAGED file is found:
  # 1. Set 'managedpackages' to true.
  # 2. Install 'python3-venv' package if not already installed.
  # 3. Create a Python virtual environment named 'genenv' in the genmon directory.
  # 4. Update 'pythoncommand' to point to the Python interpreter within this virtual environment.
  # This ensures that Python packages for genmon are installed in an isolated environment.
  if [ -f $managedfile ]; then
      managedpackages=true
      echo "Managed system packages found, installing python virtual environment"
      sudo apt-get -yqq install python3-venv
      # create the virtual environment 
      echo "Setting up virtual python environment for genmon"
      $pythoncommand -m venv $genmondir/genenv
      pythoncommand="$genmondir/genenv/bin/python"
  fi
}

#-------------------------------------------------------------------------------
function cleanpython() {
  # This function removes all pre-compiled Python files (*.pyc)
  # from the 'genmonlib' directory. This can be useful to ensure
  # a clean state, especially after Python version changes or code updates.
  echo "Removing *.pyc files..."
  sudo rm $genmondir/genmonlib/*.pyc
  echo "Done."
}
#-------------------------------------------------------------------------------
function checkpython() {
  # This function verifies if the Python command (stored in $pythoncommand,
  # which could be 'python', 'python3', or a path to a venv python) is available
  # in the system's PATH and is executable. Exits if Python is not found.
  if command -v $pythoncommand >/dev/null 2>&1; then
    echo "Python is installed."
  else
    echo "Pyhton is not present on this system. Genmon requires python." >&2 && exit 1
  fi

}
#-------------------------------------------------------------------------------
function setuppython3() {
  # This function sets the Python environment variables (usepython3, pipcommand, pythoncommand)
  # based on the input argument.
  # If no argument or an invalid argument is provided, it defaults to Python 2.
  # If '3' is provided, it sets up for Python 3.
  # It also modifies 'linetoadd' (for crontab) to include the Python version preference.
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
    pipcommand="pip3"
    pythoncommand="python3"
    # Modify the crontab line to specify python3 if chosen
    linetoadd="$linetoadd -p 3 "
  else
    echo 'Setting up for Python 2.7...'
    pipcommand="pip"
    pythoncommand="python"
    # Python 2 is default for crontab line, no change needed to linetoadd for -p 2
fi
}
#-------------------------------------------------------------------------------
# This function copy all config files to the target install directory
function copyconffiles() {
    # Creates the configuration directory specified by '$config_path' (e.g., /etc/genmon/)
    # if it doesn't already exist. Then, it copies all '*.conf' files from the
    # './conf/' directory within the genmon source to the '$config_path' directory.
    sudo mkdir -p "$config_path" # -p creates parent directories if they don't exist
    sudo cp $genmondir/conf/*.conf "$config_path"
}
#-------------------------------------------------------------------------------
# This function reads the configured branch name from genmon.conf
function get_configured_branch_name() {
    local default_branch="master"
    local conf_file="$config_path/genmon.conf"

    if [ ! -f "$conf_file" ]; then
        echo "$default_branch"
        return
    fi

    # Try to find the branch name in the [GenMon] section
    # This grep chain:
    # 1. Looks for lines starting with [GenMon] (GNU grep -A option for context)
    # 2. Within the next 5 lines, finds "update_check_branch"
    # 3. Filters again for "update_check_branch" to ensure it's the correct line
    # This is to make it more robust than a simple grep for "update_check_branch" anywhere in the file.
    local branch_line=$(sudo grep -A5 "^\[GenMon\]" "$conf_file" | grep "update_check_branch")

    if [[ -n "$branch_line" ]]; then
        # Extract the value after '='
        local value=$(echo "$branch_line" | cut -d'=' -f2)
        # Trim leading and trailing whitespace
        value=$(echo "$value" | sed 's/^[ \t]*//;s/[ \t]*$//')

        if [[ -n "$value" ]]; then
            echo "$value"
        else
            echo "$default_branch"
        fi
    else
        echo "$default_branch"
    fi
}
#-------------------------------------------------------------------------------
# This function will update the pip libraries used
function updatelibraries() {
  # This function updates Python packages listed in the 'requirements.txt' file.
  # It uses the 'pipcommand' (pip or pip3) and 'pythoncommand' determined earlier.
  # The '-U' option tells pip to upgrade packages to the latest available version.
  # '$pipoptions' can contain additional options for pip.
  echo "Updating libraries...."
  sudo $pythoncommand -m pip install -r $genmondir/requirements.txt -U $pipoptions
  echo "Done."
}

#-------------------------------------------------------------------------------
# This function will setup the serial port
function setupserial() {
  # This function navigates to the 'OtherApps' directory within the genmon
  # source code and runs the 'serialconfig.py' script.
  # The 'serialconfig.py' script is responsible for configuring the system's
  # serial port settings, often for Raspberry Pi devices, to enable
  # communication with the generator controller. The '-e -b' options are
  # passed to disable the serial console and enable the port, leaving Bluetooth on.
  pushd $genmondir
  cd OtherApps
  # we will leave bluetooth on. Pi4 and earlier devices the serial port 
  # has a conflict unless you use the -b option
  sudo $pythoncommand serialconfig.py -e -b
  echo "Finished setting up the serial port."
  popd
}

#-------------------------------------------------------------------------------
# This function will install rpirtscts program needed for the LTE modem
function installrpirtscts() {
    # This function clones the 'rpirtscts' utility from GitHub,
    # builds it using 'make', and installs the compiled binary to
    # '/usr/local/bin/rpirtscts'. This utility is used for managing
    # RTS/CTS flow control for serial communication, often needed for
    # LTE modems on Raspberry Pi.
    echo "Installing rpirtscts..."
    pushd $genmondir # Save current directory
    cd ~ # Change to home directory for cloning
    git clone https://github.com/mholling/rpirtscts.git
    cd rpirtscts
    make
    sudo cp ./rpirtscts /usr/local/bin/rpirtscts
    echo "Finished installing rpirtscts."
    popd # Return to original directory
}
#-------------------------------------------------------------------------------
# This function will install the required libraries for genmon
function installgenmon() {

    echo "Installing genmon package requirements...."
    # Update package lists
    sudo apt-get -yqq update
    # Install pip for the selected Python version
    if [ "$usepython3" = true ] ; then
      sudo apt-get -yqq install python3-pip
    else
      sudo apt-get -yqq install python-pip
    fi
    # Install build tools and development headers required for some Python packages
    if [ "$usepython3" = true ] ; then
      sudo apt-get -yqq install build-essential libssl-dev libffi-dev python3-dev cargo
    else
      sudo apt-get -yqq install build-essential libssl-dev libffi-dev python-dev cargo
    fi
    # Install cmake, another build tool dependency
    sudo apt-get -yqq install cmake
    # Install Python packages from requirements.txt using pip
    sudo $pythoncommand -m pip install -r $genmondir/requirements.txt $pipoptions

    # Set execute permissions for main scripts
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    # Install rpirtscts utility
    installrpirtscts

    # Prompt user to copy configuration files unless '-n' (noprompt) was specified
    if [ -z "$2" ] && [ $1 != "noprompt" ]; then
        read -p "Copy configuration files to $config_path? (y/n)?" choice
        case "$choice" in
          y|Y ) echo "Copying *.conf files to "$config_path""
            copyconffiles # Call function to copy config files
            configfilescopied=true # Set flag indicating files were copied
            ;;
          n|N ) echo "Not copying *.conf to "$config_path""
            ;;
          *)
            echo "Invalid choice, not copying conf files"
            ;;
        esac
    else # If noprompt or called with specific internal arguments
        copyconffiles
        configfilescopied=true
    fi

    # If config files were copied, prompt for serial port setup method
    if [ "$configfilescopied" = true ] && [ -z "$2" ] && [ $1 != "noprompt" ]; then
      read -p "What type of connection from genmon to the controller? S=Onboard Serial, T=Network, Serial over TCP/IP Bridge, U=USB Serial (s/t/u)?" choice
      case "$choice" in
        s|S ) echo "Setting up serial onboard port..."
          # For Raspberry Pi 5 or non-Raspbian OS (like Ubuntu), use /dev/ttyAMA0
          if is_pifive || [ "$is_raspbian" = false ]; then
            echo "Using port /dev/ttyAMA0"
            # Modify genmon.conf to use /dev/ttyAMA0
            sudo sudo sed -i 's/\/dev\/serial0/\/dev\/ttyAMA0/gI' "$config_path"genmon.conf
          fi
          # For other Pi models, /dev/serial0 is often the default and might not need changing in genmon.conf
          ;;
        t|T ) echo "Network connection used for serial over TCP/IP. Not setting up onboard serial port"
          # Modify genmon.conf to enable serial over TCP/IP
          sudo sed -i 's/use_serial_tcp = False/use_serial_tcp = True/gI' "$config_path"genmon.conf
          useserial=false # Indicate that onboard serial setup is not needed
          ;;
        u|U ) echo "USB serial. Not setting up onboard serial port, using USB serial /dev/ttyUSB0"
          # Modify genmon.conf to use /dev/ttyUSB0
          sudo sudo sed -i 's/\/dev\/serial0/\/dev\/ttyUSB0/gI' "$config_path"genmon.conf
          useserial=false # Indicate that onboard serial setup is not needed
          ;;
        *)
          echo "Invalid choice, defaulting to onboard serial"
          # Default behavior might assume /dev/serial0 or require manual setup later
          ;;
      esac
    fi

    # If using onboard serial, prompt for automatic serial port setup
    if [ "$useserial" = true ]; then
      if [ -z "$2" ] && [ $1 != "noprompt" ]; then
        read -p "Setup the raspberry pi onboard serial port? (y/n)?" choice
        case "$choice" in
          y|Y ) echo "Setting up serial port..."
            setupserial # Call function to configure serial port
            ;;
          n|N ) echo "Not setting up serial port"
            ;;
          *)
            echo "Invalid choice, not setting up serial port"
            ;;
        esac
      else # If noprompt or called with specific internal arguments
          setupserial
      fi
    fi
    echo "Done."
}

#-------------------------------------------------------------------------------
function updatecrontab() {
    # This function adds or updates a crontab entry to start genmon on boot.
    # It first reads the existing crontab into a temporary file.
    sudo crontab -l > $tempfile
    # It then checks if a line containing 'startgenmon.sh' already exists.
    result=$(grep -i "startgenmon.sh" /tmp/gmtemp) # Case-insensitive search

    if [ "$result" == "" ]; then
        # If 'startgenmon.sh' is not found, add the 'linetoadd' to crontab.
        echo "Updating crontab..."
        echo "adding < $linetoadd > to crontab"
        echo "$linetoadd" >> $tempfile # Append the new line to the temp file
        sudo crontab $tempfile       # Load the modified temp file into crontab
    elif [ "$result" != "$linetoadd" ]; then
        # If 'startgenmon.sh' is found but the line is different from 'linetoadd',
        # it means the existing entry is incorrect or outdated.
        echo "Crontab has an incorrect configuration, updating:"
        echo "Old entry: $result"
        echo "New entry: $linetoadd"
        # Use sed to replace the old line with the new line.
        # Special characters in 'result' and 'linetoadd' (like '&&') need to be escaped for sed.
        # Here, '&&' is replaced with '\\&\\&' to be treated literally by sed's regex.
        # The '~' is used as a delimiter for sed's s command to avoid conflict with '/' in paths.
        sudo sed -i "s~${result//\&\&/\\\&\\\&}~${linetoadd//\&\&/\\\&\\\&}~g" $tempfile
        sudo crontab $tempfile # Load the corrected crontab.
    else
        # If the line already exists and is correct, do nothing.
        echo "Crontab already contains genmon start script:"
        echo "$result"
    fi
    # It's good practice to remove the temporary file, though not explicitly done here.
}

#-------------------------------------------------------------------------------
# archive log files
function archivelogs() {
    # This function creates a compressed tar archive of various genmon-related log files.
    # It first removes any existing 'genmon_logs' directory and 'genmon_logs.tar.gz' archive.
    # Then, it creates a new 'genmon_logs' directory, copies specified log files
    # from '$log_path' (e.g., /var/log/genmon/) into it, creates a .tar.gz archive
    # from this directory, and finally removes the temporary 'genmon_logs' directory.
    # Key log files included: genmon.log, genserv.log, mymail.log, myserial.log, etc.
    echo "Archive log files from $log_path ..."
    cd $genmondir
    sudo rm -r genmon_logs 2>/dev/null # Suppress error if dir doesn't exist
    sudo rm genmon_logs.tar.gz 2>/dev/null # Suppress error if file doesn't exist
    mkdir genmon_logs

    # Copy various log files into the temporary directory
    sudo cp "$log_path"genmon.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genserv.log ./genmon_logs 2>/dev/null
    # ... (other cp commands for different log files, suppressing errors if files don't exist) ...
    sudo cp "$log_path"mymail.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"myserial.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"mymodbus.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gengpio.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gengpioin.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gensyslog.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"myserialtcp.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genlog.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genloader.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genmqtt.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genpushover.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genslack.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gensms.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gensms_modem.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genemail2sms.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genexercise.log ./genmon_logs 2>/dev/null
    # Note: gengpioin.log is listed twice in original, keeping one.
    sudo cp "$log_path"genalexa.log ./genmon_logs 2>/dev/null
    # Note: genemail2sms.log and genexercise.log are listed twice, keeping one of each.
    sudo cp "$log_path"gensnmp.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gentankutil.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gentankdiy.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gentemp.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gengpioledblink.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gencthat.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"genmopeka.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gencustomgpio.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gencallmebot.log ./genmon_logs 2>/dev/null
    sudo cp "$log_path"gensms_voip.log ./genmon_logs 2>/dev/null

    # Create a compressed tar archive of the genmon_logs directory
    tar -zcvf genmon_logs.tar.gz genmon_logs/
    # Remove the temporary directory
    sudo rm -r genmon_logs
    echo "Done."
}

#-------------------------------------------------------------------------------
# backup genmon
function backupgenmon() {
    # This function creates a compressed tar archive of genmon configuration files and key data files.
    # It first removes any existing 'genmon_backup' directory and 'genmon_backup.tar.gz' archive.
    # Then, it creates a new 'genmon_backup' directory, copies specified .conf files from
    # '$config_path' (e.g., /etc/genmon/) and other data files (like outage.txt, kwlog.txt)
    # into it, creates a .tar.gz archive, and finally removes the temporary 'genmon_backup' directory.
    # Key files included: genmon.conf, mymail.conf, genloader.conf, various module configs,
    # outage.txt, kwlog.txt, fuellog.txt, maintlog.json, update.txt.
    echo "Backup genmon..."
    cd $genmondir
    sudo rm -r genmon_backup 2>/dev/null # Suppress error if dir doesn't exist
    sudo rm genmon_backup.tar.gz 2>/dev/null # Suppress error if file doesn't exist
    mkdir genmon_backup

    # Copy configuration files
    sudo cp "$config_path"genmon.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"mymail.conf ./genmon_backup 2>/dev/null
    # ... (other *.conf file copy commands, suppressing errors) ...
    sudo cp "$config_path"genloader.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genmqtt.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genpushover.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genslack.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gensms.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"mymodem.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genemail2sms.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genexercise.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gengpio.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gengpioin.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genalexa.conf ./genmon_backup 2>/dev/null
    # Note: genemail2sms.conf and genexercise.conf are listed twice, keeping one of each.
    sudo cp "$config_path"gensnmp.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gentankutil.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gentemp.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gentankdiy.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gengpioledblink.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gencthat.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"genmopeka.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gencustomgpio.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gencallmebot.conf ./genmon_backup 2>/dev/null
    sudo cp "$config_path"gensms_voip.conf ./genmon_backup 2>/dev/null

    # Copy data files
    sudo cp "$config_path"outage.txt ./genmon_backup 2>/dev/null
    sudo cp "$config_path"kwlog.txt ./genmon_backup 2>/dev/null
    sudo cp "$config_path"fuellog.txt ./genmon_backup 2>/dev/null
    sudo cp "$config_path"maintlog.json ./genmon_backup 2>/dev/null
    sudo cp "$config_path"update.txt ./genmon_backup 2>/dev/null

    # Create a compressed tar archive of the genmon_backup directory
    tar -zcvf genmon_backup.tar.gz genmon_backup/
    # Remove the temporary directory
    sudo rm -r genmon_backup
    echo "Done."
}
#-------------------------------------------------------------------------------
# update genmon from the github repository
# this function assumes you have downloaded the project from github
function updategenmon() {
    # This function updates the genmon software to the latest version from
    # the 'origin/master' branch of its Git repository.
    echo "Updating genmon..."
    cd $genmondir # Change to the genmon source directory

    local configured_branch=$(get_configured_branch_name)
    echo "Updating genmon from branch: $configured_branch"

    current_time=$(date '+%Y-%m-%d:%H:%M:%S') # Get current timestamp
    
    # Define path for update history file
    UPDATE_HISTORY="$config_path"update.txt
    # Create update history file if it doesn't exist
    if [ ! -f "$UPDATE_HISTORY" ]; then
      echo "$UPDATE_HISTORY does not exist. Creating.."
      sudo touch $UPDATE_HISTORY
    fi

    # Ensure the current directory is recognized as a safe Git repository
    git config --global --add safe.directory '*'
    # Fetch the latest changes from the remote 'origin' for the configured branch
    git fetch origin $configured_branch
    # Force reset the local branch to match the fetched branch from origin, discarding local changes
    git reset --hard origin/$configured_branch
    # Set execute permissions for main scripts
    sudo chmod 775 "$genmondir/startgenmon.sh"
    sudo chmod 775 "$genmondir/genmonmaint.sh"
    # Set ownership and group for the genmon directory recursively to match the parent directory's user/group
    sudo chown -R `stat -c "%U" $genmondir` $genmondir
    sudo chgrp -R `stat -c "%G" $genmondir` $genmondir

    # Append the current timestamp to the update history file
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
  echo "  -r           Refresh (update) required libraries"
  echo "  -u           Update genmon to the latest version"
  echo "  -C           Remove *.pyc files (clean pre-compiled python files)"
  echo "  -n           Do not prompt for Y/N, assume yes"
  echo "  -c           Specifiy full path to config file directory"
  echo "  -p           Specifiy 2 or 3 for python version. 2 is default"
  echo "  -s           Just copy conf files"
  echo "  -l           Specifiy the full path of the log directory to archive"
  echo "  -f           Update OS software and apt repository flags if needed"
  echo "  -h           Display help"
  echo ""
}

#-------------------------------------------------------------------------------
# main entry

# Process command-line options using getopts
while getopts ":hfp:birunc:Csl:" opt; do
  case ${opt} in
    h ) # Display help
      printhelp
      exit 0
      ;;
    f ) # Flag to update OS software
      update_os=true
      ;;
    p ) # Specify Python version (2 or 3)
      setuppython3 $OPTARG
      ;;
    c ) # Specify custom configuration path
      config_path=$OPTARG
      # Append config path to crontab line if specified
      linetoadd="$linetoadd -c $OPTARG"
      ;;
    C ) # Flag to clean .pyc files
      cleanpython_opt=true
      ;;
    l ) # Specify custom log path for archiving
      log_path=$OPTARG
      log_opt=true
      ;;
    s ) # Flag to only copy configuration files
      copyfiles_opt=true
      ;;
    b ) # Flag to backup genmon configuration
      backup_opt=true
      ;;
    i ) # Flag to install genmon
      install_opt=true
      ;;
    r ) # Flag to refresh/update Python libraries
      refresh_opt=true
      ;;
    u ) # Flag to update genmon software
      update_opt=true
      ;;
    n ) # Flag for non-interactive mode (no prompts)
      noprompt_opt=true
      ;;
    \? ) # Handle invalid options
      echo "Invalid Option: -$OPTARG" 1>&2
      printhelp
      exit 1
      ;;
  esac
done
shift $((OPTIND -1)) # Remove processed options from positional parameters

# Perform OS update if -f flag was used
if [ "$update_os" = true ] ; then
   sudo apt-get --allow-releaseinfo-change update && sudo apt-get upgrade -yqq
fi

# Perform initial system checks
check_os                 # Determine OS type
checkpython              # Verify Python installation
checkmanagedpackages     # Check for externally managed Python and set up venv if needed

# Perform installation if -i flag was used
if [ "$install_opt" = true ] ; then
  if [ "$noprompt_opt" = true ] ; then
    # Activate virtual environment if used
    env_activate
    installgenmon "noprompt" # Install without prompts
    # Deactivate virtual environment
    env_deactivate
    updatecrontab # Update crontab to start genmon on boot
  else
    read -n 1 -s -r -p "$installnotice" # Display install notice and wait for key press
    echo ""
    # Install libraries
    env_activate
    installgenmon "prompt" # Install with prompts
    env_deactivate
    # Update crontab
    read -p "Start genmon on boot? (y/n)?" choice
    case "$choice" in
      y|Y ) echo "Updating crontab...."
        updatecrontab
        ;;
      n|N ) echo "Not updating crontab."
        ;;
      *)
        echo "Invalid choice, not updating crontab.."
        ;;
    esac
  fi
fi

# Clean .pyc files if -C flag was used
if [ "$cleanpython_opt" = true ] ; then
  env_activate # Activate venv if needed
  cleanpython
  env_deactivate # Deactivate venv
fi

# Perform backup if -b flag was used
if [ "$backup_opt" = true ] ; then
  backupgenmon
fi

# Archive logs if -l flag was used (log_opt is set if -l is used)
if [ "$log_opt" = true ] ; then
  archivelogs
fi

# Refresh Python libraries if -r flag was used
if [ "$refresh_opt" = true ] ; then
  env_activate # Activate venv
  updatelibraries
  env_deactivate # Deactivate venv
fi

# Update genmon software if -u flag was used
if [ "$update_opt" = true ] ; then
  if [ "$noprompt_opt" = true ] ; then
    updategenmon # Update without prompt
  else
    read -p "$updatenotice" choice # Display update notice and prompt
    case "$choice" in
      y|Y ) updategenmon
        ;;
      * ) echo "Not updating genmon"
        ;;
    esac
  fi
fi

# Copy configuration files if -s flag was used
if [ "$copyfiles_opt" = true ] ; then
  copyconffiles
fi

exit 0
