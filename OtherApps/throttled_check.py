import select
import datetime
import sys

#------------------------------------------------------
def ParseThrottleStatus(status):
    StatusStr = ""

    if (status & 0x40000):
        StatusStr += "Throttling has occured. "
    if (status & 0x20000):
        StatusStr += "ARM freqency capping has occured. "
    if (status & 0x10000):
        StatusStr += "Undervoltage has occured. "
    if (status & 0x4):
        StatusStr += "Active throttling. "
    if (status & 0x2):
        StatusStr += "Active ARM frequency capped. "
    if (status & 0x1):
        StatusStr += "Active undervoltage. "

    return StatusStr

if __name__=='__main__':

    print("\nThis program will monitor the Raspberry Pi CPU throttling status. Type Ctrl+C to exit.\n")

    epoll = select.epoll()

    try:
        file = open("/sys/devices/platform/soc/soc:firmware/get_throttled")
    except:
        print("This program requires a Rasperry Pi. The latest firmware version is recommened.\n")
        sys.exit(1)

    epoll.register(file.fileno(), select.EPOLLPRI | select.EPOLLERR)
    status = file.read()

    get_throttled = int(status, 16)
    StatusStr = ParseThrottleStatus(get_throttled)
    print("Initial Status: %s 0x%08x : %s" % (datetime.datetime.now().strftime('%H:%M:%S'), get_throttled, StatusStr))


    while(True):
        epoll.poll()
        file.seek(0)
        status = file.read()
        get_throttled = int(status, 16)

        StatusStr = ParseThrottleStatus(get_throttled)

        print("%s 0x%08x : %s" % (datetime.datetime.now().strftime('%H:%M:%S'), get_throttled, StatusStr))

    epoll.unregister(file.fileno())
    file.close()
