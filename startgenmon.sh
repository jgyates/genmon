#!/bin/bash

genmondir="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

case "$1" in
  start)
    echo "Starting genmon python scripts"
    sudo python "$genmondir/genmon.py"  &
    sleep 3
    sudo python "$genmondir/genserv.py"  &
    # sleep 5
    #sudo python "$genmondir/gengpio.py"  &
    #sudo python "$genmondir/gengpioin.py"  &
    #sudo python "$genmondir/genlog.py" -f "$genmondir/LogFile.csv" &
    #sudo python "$genmondir/gensms.py" &
    #sudo python "$genmondir/genpushover.py" &
    #sudo python "$genmondir/gensyslog.py" &
    ;;
  stop)
    echo "Stopping genmon python scripts"
    sudo pkill -u root -f genmon.py
    sudo pkill -u root -f genserv.py
    #sudo pkill -u root -f gengpio.py
    #sudo pkill -u root -f gengpioin.py
    #sudo pkill -u root -f genlog.py
    #sudo pkill -u root -f gensms.py
    #sudo pkill -u root -f genpushover.py
    #sudo pkill -u root -f gensyslog.py
    ;;
  restart)
    echo "Stopping genmon python scripts"
    sudo pkill -u root -f genmon.py
    sudo pkill -u root -f genserv.py
    #sudo pkill -u root -f gengpio.py
    #sudo pkill -u root -f gengpioin.py
    #sudo pkill -u root -f genlog.py
    #sudo pkill -u root -f gensms.py
    #sudo pkill -u root -f genpushover.py
    #sudo pkill -u root -f gensyslog.py
    sleep 1
    echo "Starting genmon python scripts"
    sudo python "$genmondir/genmon.py"  &
    sleep 3
    sudo python "$genmondir/genserv.py"  &
    #sleep 5
    #sudo python "$genmondir/gengpio.py"  &
    #sudo python "$genmondir/gengpioin.py"  &
    #sudo python "$genmondir/genlog.py" -f "$genmondir/LogFile.csv" &
    #sudo python "$genmondir/gensms.py" &
    #sudo python "$genmondir/genpushover.py" &
    #sudo python "$genmondir/gensyslog.py" &
    ;;
  *)
    #
    echo "Invalid command."
    ;;
esac

exit 0
