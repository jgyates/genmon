#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
pycmd="python"
configpath=""
if [ -z "$2" ]; then
  configpath=""
else
  configpath="-c $2"
  echo "Using config in $2"
fi
case "$1" in
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
