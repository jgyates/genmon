#!/bin/bash
# bash script to start, stop or restart genmon. the scrip calls genloader.py
# with the needed command line parameters and can use python 2.7 or 3.x to call
# genloader.py
#-------------------------------------------------------------------------------
PARAMS=""
genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pythoncommand="python3"
pipcommand="pip3"
config_path=""
usepython3=true
found_action=false
managedpackages=false


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
      pythoncommand="$genmondir/genenv/bin/python"
      managedpackages=true
      echo "using binary: $pythoncommand"
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
    echo 'Using Python 3.x...'
    pipcommand="pip3"
    pythoncommand="python3"
  else
    echo 'Using Python 2.x...'
    pipcommand="pip2"
    pythoncommand="python2"
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
while (( "$#" )); do
  case "$1" in
    -p)
      setuppython3 $2
      shift 2
      ;;
    -c)
      if [ -n "$2" ] && [ ${2:0:1} != "-" ]; then
        config_path="-c $2"
        shift 2
      else
        echo "Error: Argument for $1 is missing" >&2
        exit 1
      fi
      ;;
    -h)
     printhelp
     exit 0
    ;;
    -*|--*=) # unsupported flags
      echo "Error: Unsupported flag $1" >&2
      exit 1
      ;;
    *) # preserve positional arguments
      PARAMS="$PARAMS $1"
      shift
      ;;
  esac
done
checkmanagedpackages
for val in $PARAMS; do
  case "$val" in
    start)
      echo "Starting genmon python scripts"
      env_activate
      found_action=true
      sudo $pythoncommand "$genmondir/genloader.py" -s $config_path
      env_deactivate
      ;;
    stop)
      found_action=true
      env_activate
      echo "Stopping genmon python scripts"
      sudo $pythoncommand "$genmondir/genloader.py" -x $config_path
      env_deactivate
      ;;
    hardstop)
      found_action=true
      env_activate
      echo "Hard Stopping genmon python scripts"
      sudo $pythoncommand "$genmondir/genloader.py" -z $config_path
      env_deactivate
      ;;
    restart)
      found_action=true
      env_activate
      echo "Restarting genmon python scripts"
      sudo $pythoncommand "$genmondir/genloader.py" -r $config_path
      env_deactivate
      ;;
    *)
      #
      echo "Additional command found: " $val
      ;;
  esac
done

if [ "$found_action" = false ] ; then
  echo "Invalid command. Valid commands are start, stop, restart or hardstop."
fi

exit 0
