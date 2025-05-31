#!/bin/bash
# bash script to start, stop or restart genmon. the scrip calls genloader.py
# with the needed command line parameters and can use python 2.7 or 3.x to call
# genloader.py
#-------------------------------------------------------------------------------
PARAMS=""
genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )" # Determine the script's own directory
pythoncommand="python3" # Default to python3
pipcommand="pip3"       # Default to pip3
config_path=""          # Path to config files, can be overridden by -c option
usepython3=true         # Flag to indicate if python 3 is being used
found_action=false      # Flag to track if a valid action (start, stop, etc.) was provided
managedpackages=false   # Flag to indicate if the system uses an externally managed python environment


#-------------------------------------------------------------------------------
function env_activate() {
  # This function activates the Python virtual environment located in
  # '$genmondir/genenv' if the 'managedpackages' variable is true.
  # 'managedpackages' is set if the system is detected to use
  # an externally managed Python environment (e.g., Debian Bookworm onwards),
  # prompting the use of a venv for genmon's dependencies.
  if [ "$managedpackages" = true ] ; then
    source $genmondir/genenv/bin/activate
  fi
}
#-------------------------------------------------------------------------------
function env_deactivate() {
  # This function deactivates an active Python virtual environment if
  # 'managedpackages' is true. It's typically called after Python scripts
  # that require the venv have finished executing.
  if [ "$managedpackages" = true ] ; then
    deactivate
  fi
}
#-------------------------------------------------------------------------------
function checkmanagedpackages() {
  # This function checks if the system's Python is "externally managed",
  # a practice in newer OS distributions (like Debian Bookworm) to prevent
  # conflicts between system packages and pip-installed packages.

  # Determine the Python major and minor version to construct the path
  # to the EXTERNALLY-MANAGED marker file.
  pythonmajor=$($pythoncommand -c 'import sys; print(sys.version_info.major)')
  pythonminor=$($pythoncommand -c 'import sys; print(sys.version_info.minor)')
  managedfile="/usr/lib/python$pythonmajor.$pythonminor/EXTERNALLY-MANAGED"

  # If the EXTERNALLY-MANAGED file exists:
  # 1. Set 'managedpackages' to true, indicating a venv should be used.
  # 2. Update 'pythoncommand' to point to the Python interpreter within the
  #    virtual environment ('$genmondir/genenv/bin/python').
  #    Note: genmonmaint.sh is responsible for creating this venv.
  if [ -f $managedfile ]; then
      pythoncommand="$genmondir/genenv/bin/python"
      managedpackages=true
      echo "using binary: $pythoncommand" # Inform user that venv python is being used
  fi
}
#-------------------------------------------------------------------------------
function setuppython3() {
  # This function sets the Python interpreter and pip command based on the
  # provided argument (typically '2' or '3').
  # - $1: The first argument to the function (Python version preference).

  if [ $# -eq 0 ]; then # If no argument is provided
    usepython3=false   # Default to Python 2 behavior (legacy)
  elif [ $1 == "3" ]; then # If argument is '3'
    usepython3=true    # Set flag to use Python 3
  elif [ $1 == "2" ]; then # If argument is '2'
    usepython3=false   # Set flag to use Python 2
  else # For any other argument
    usepython3=false   # Default to Python 2 behavior
  fi

  if [ "$usepython3" = true ] ; then
    echo 'Using Python 3.x...'
    pipcommand="pip3"       # Set pip command for Python 3
    pythoncommand="python3" # Set python command for Python 3
  else
    echo 'Using Python 2.x...'
    pipcommand="pip2"       # Set pip command for Python 2 (or pip for older systems)
    pythoncommand="python2" # Set python command for Python 2 (or python)
fi
}

#-------------------------------------------------------------------------------
function printhelp(){
  echo "usage: "
  echo " "
  echo "./startgenmon.sh <options> start|stop|restart|hardstop"
  echo ""
  echo "valid options:"
  echo "   -h      display help"
  echo "   -c      path of config files"
  echo "   -p      Specifiy 2 or 3 for python version. 2 is default"
  echo ""
}

#-------------------------------------------------------------------------------
# main
# This loop parses command-line options.
# It continues as long as there are arguments ("$#").
while (( "$#" )); do
  case "$1" in
    -p) # Python version option
      # Calls setuppython3 with the next argument ($2) which should be '2' or '3'.
      setuppython3 $2
      shift 2 # Consume both -p and its argument.
      ;;
    -c) # Configuration path option
      # Check if the next argument ($2) is present and not another option (doesn't start with -).
      if [ -n "$2" ] && [ ${2:0:1} != "-" ]; then
        config_path="-c $2" # Store the -c option and its argument for later use with genloader.py.
        shift 2 # Consume both -c and its argument.
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    -h) # Help option
     printhelp # Display help message.
     exit 0    # Exit script.
    ;;
    -*|--*=) # Handle unsupported flags/options.
      echo "Error: Unsupported flag $1" >&2
      exit 1
      ;;
    *) # Collect non-option arguments (like 'start', 'stop').
      # These are assumed to be action commands.
      PARAMS="$PARAMS $1"
      shift # Consume the argument.
      ;;
  esac
done

# Check if the system uses an externally managed Python environment and adjust pythoncommand if needed.
checkmanagedpackages

# This loop processes the action commands (start, stop, restart, hardstop)
# that were collected in the PARAMS variable.
for val in $PARAMS; do
  case "$val" in
    start) # Start genmon
      echo "Starting genmon python scripts"
      env_activate # Activate Python virtual environment if managedpackages is true.
      found_action=true # Mark that a valid action was found.
      # Execute genloader.py with the -s (start) flag and any custom config path.
      sudo $pythoncommand "$genmondir/genloader.py" -s $config_path
      env_deactivate # Deactivate Python virtual environment if it was used.
      ;;
    stop) # Stop genmon
      found_action=true
      env_activate
      echo "Stopping genmon python scripts"
      # Execute genloader.py with the -x (stop) flag.
      sudo $pythoncommand "$genmondir/genloader.py" -x $config_path
      env_deactivate
      ;;
    hardstop) # Hard stop genmon
      found_action=true
      env_activate
      echo "Hard Stopping genmon python scripts"
      # Execute genloader.py with the -z (hardstop, implies stop) flag.
      sudo $pythoncommand "$genmondir/genloader.py" -z $config_path
      env_deactivate
      ;;
    restart) # Restart genmon
      found_action=true
      env_activate
      echo "Restarting genmon python scripts"
      # Execute genloader.py with the -r (restart) flag.
      sudo $pythoncommand "$genmondir/genloader.py" -r $config_path
      env_deactivate
      ;;
    *) # Handle any other non-option arguments if necessary.
      # Currently, this just echoes the additional command.
      echo "Additional command found: " $val
      ;;
  esac
done

# If no valid action command (start, stop, restart, hardstop) was found in PARAMS,
# print an error message.
if [ "$found_action" = false ] ; then
  echo "Invalid command. Valid commands are start, stop, restart or hardstop."
fi

exit 0
