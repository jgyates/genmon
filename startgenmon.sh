
case "$1" in
  start)
    echo "Starting genmon python scripts"
    sudo python /home/pi/genmon/genmon.py  &
    sleep 2
    sudo python /home/pi/genmon/genserv.py  &
    #sudo python /home/pi/genmon/gengpio.py  &
    #sudo python /home/pi/genmon/gengpioin.py  &
    #sudo python /home/pi/genmon/genlog.py -f /home/pi/genmon/LogFile.csv
    #sudo python /home/pi/genmon/gensms.py
    ;;
  stop)
    echo "Stopping genmon python scripts"
    sudo pkill -f genmon.py
    sudo pkill -f genserv.py
    #sudo pkill -f gengpio.py
    #sudo pkill -f gengpioin.py
    #sudo pkill -f genlog.py
    #sudo pkill -f gensms.py
    ;;
  *)
    #
    ;;
esac

exit 0

