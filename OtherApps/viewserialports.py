import serial.tools.list_ports

def list_serial_ports():
    """Lists serial port names and details."""
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found.")
    else:
        print("Available serial ports:")
        for port, desc, hwid in sorted(ports):
            print(f"- {port}: {desc} [{hwid}]")
    return ports

if __name__ == '__main__':
    list_serial_ports()