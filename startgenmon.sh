#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pycmd="python"
configpath=""

#-------------------------------------------------------------------------------
function printhelp() {

  echo ""
  echo "Usage: "
  echo ""
  echo "    startgenmon.sh <options> <action>"
  echo ""
  echo "Options:"
  echo ""
  echo "  -c           Specifiy full path to config file directory"
  echo "  -p           Use python 3 instead of python 2.7"
  echo "  -h           Display help"
  echo ""
  echo "Actions:"
  echo ""
  echo " start) stop) hardstop) restart) "
  echo ""
}

#-------------------------------------------------------------------------------
# main entry

while getopts ":c:p:h" opt; do
  case ${opt} in
    h )
      printhelp
      exit 0
      ;;
    p )
      pycmd="python$OPTARG"
      ;;
    c )
      config_path="-c $OPTARG"
      ;;
    \? )
      echo "Invalid Option: -$OPTARG" 1>&2
      printhelp
      exit 1
      ;;
  esac
done
case "$2" in
  start)
    echo "Starting genmon python scripts"
    sudo $pycmd "$genmondir/genloader.py" -s $configpath
    ;;
  stop)
    echo "Stopping genmon python scripts"
    sudo $pycmd "$genmondir/genloader.py" -x $configpath
    ;;
  hardstop)
    echo "Hard Stopping genmon python scripts"
    sudo $pycmd "$genmondir/genloader.py" -z $configpath
    ;;
  restart)
    echo "Restarting genmon python scripts"
    sudo $pycmd "$genmondir/genloader.py" -r $configpath
    ;;
  *)
    #
    echo "Invalid command. Valid commands are start, stop, restart or hardstop."
    ;;
esac

exit 0
