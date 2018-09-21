#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

case "$1" in
  start)
    echo "Starting genmon python scripts"
    sudo python "$genmondir/genloader.py" -s
    ;;
  stop)
    echo "Stopping genmon python scripts"
    sudo python "$genmondir/genloader.py" -x
    ;;
  hardstop)
    echo "Hard Stopping genmon python scripts"
    sudo python "$genmondir/genloader.py" -z
    ;;
  restart)
    echo "Restarting genmon python scripts"
    sudo python "$genmondir/genloader.py" -r
    ;;
  *)
    #
    echo "Invalid command. Valid commands are start, stop, restart or hardstop."
    ;;
esac

exit 0
