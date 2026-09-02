#!/usr/bin/env python
# ------------------------------------------------------------
#    FILE: modbusscan.py
# PURPOSE: Scan a serial port across common baud rates and all
#          MODBUS RTU slave IDs (1-247) to discover the address
#          and speed of an attached MODBUS device.
#
#  AUTHOR: Jon R. Helms
#    DATE: 01-Sep-2026
# Free software. Use at your own risk.
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import os
import sys
import time
import re
from subprocess import PIPE, Popen

try:
    import serial
    import serial.tools.list_ports
except Exception as e1:
    managedfile = "/usr/lib/python" + str(sys.version_info.major) + "." + str(sys.version_info.minor) + "/EXTERNALLY-MANAGED"
    if os.path.isfile(managedfile):
        print("\n\nYou appear to be running in a managed python environemnt. To run this program see this page: ")
        print("\n\n  https://github.com/jgyates/genmon/wiki/Appendix-S---Working-in-a-Managed-Python-Environment\n")
    else:
        print("\nThe python serial libary is not install. You must run the setup script first.\n")
        print("\n\n   https://github.com/jgyates/genmon/wiki/3.3--Setup-genmon-software")
    sys.exit(1)

BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400]
SLAVE_IDS = range(1, 248)  # 1-247


# ------------ UseLegacySerialName --------------------------------------------
def UseLegacySerialName():
    try:
        model = GetRaspberryPiModel()

        if model == None:
            return True

        PiMajorVersion = re.search(r'\d+', model).group()
        if int(PiMajorVersion) >= 5:
            return False
        return True
    except Exception as e1:
        print("Error in UseLegacySerialEnable: " + GetErrorInfo())
        return False
# ------------ IsPlatformRaspberryPi -------------------------------------------
def IsPlatformRaspberryPi():
    try:
        model = GetRaspberryPiModel()
        if model != None and "raspberry" in model.lower():
            return True
        return False
    except Exception as e1:
        print("Error in IsPlatformRaspberryPi: " + GetErrorInfo())
        return False
# ------------ GetRaspberryPiModel ---------------------------------------------
def GetRaspberryPiModel():
    try:
        process = Popen(["cat", "/proc/device-tree/model"], stdout=PIPE)
        output, _error = process.communicate()
        if sys.version_info[0] >= 3:
            output = output.decode("utf-8")
        return str(output.rstrip("\x00"))
    except Exception as e1:
        return None

# ------------ VersionTuple -----------------------------------------------------
def VersionTuple(value):

    value = removeAlpha(value)
    return tuple(map(int, (value.split("."))))


# ----------  removeAlpha--------------------------------------------------------
# used to remove alpha characters from string so the string contains a
# float value (leaves all special characters)
def removeAlpha(inputStr):
    answer = ""
    for char in inputStr:
        if not char.isalpha() and char != " " and char != "%":
            answer += char

    return answer.strip()


# ------------------- List / Select Serial Port ---------------------------------
def ListSerialPorts():
    ports = serial.tools.list_ports.comports()
    if not ports:
        print("No serial ports found.")
    else:
        print("Available serial ports:")
        for i, (port, desc, hwid) in enumerate(sorted(ports)):
            print(f"  [{i}] {port}: {desc} [{hwid}]")
    return sorted(ports)


def SelectSerialPort():
    ports = ListSerialPorts()

    if not ports:
        return None

    if len(ports) == 1:
        print(f"\nOnly one port found, using {ports[0][0]}")
        return ports[0][0]

    try:
        choice = input(f"\nSelect a port [0-{len(ports) - 1}]: ").strip()
        index = int(choice)
        return ports[index][0]
    except (ValueError, IndexError):
        print("Invalid selection.")
        return None


# ------------------- Open Serial Port for scanning ------------------------------
def OpenScanPort(name, rate):

    if VersionTuple(serial.__version__) < VersionTuple("3.3"):
        NewSerialPort = serial.Serial()
    else:
        NewSerialPort = serial.Serial(exclusive=True)

    NewSerialPort.port = name

    if NewSerialPort.is_open == True:
        print(
            "The serial port is already opened. The serial port is in use, please stop genmon and retry."
        )

    NewSerialPort.baudrate = rate
    NewSerialPort.bytesize = serial.EIGHTBITS  # number of bits per bytes
    NewSerialPort.parity = serial.PARITY_NONE  # set parity check: no parity
    NewSerialPort.stopbits = serial.STOPBITS_ONE  # number of stop bits
    NewSerialPort.timeout = 0.1  # 100ms read timeout, matches slave response window
    NewSerialPort.xonxoff = False  # disable software flow control
    NewSerialPort.rtscts = False  # disable hardware (RTS/CTS) flow control
    NewSerialPort.dsrdtr = False  # disable hardware (DSR/DTR) flow control
    NewSerialPort.writeTimeout = 0.1  # timeout for write

    if NewSerialPort.is_open == False:
        try:
            NewSerialPort.open()
        except Exception as e:
            print("error opening serial port: " + str(e))
            print("\nTry stopping genmon.\n")
            return None
    else:
        print(
            "Serial port already opened. The serial port is in use. Please stop genmon and retry."
        )
        return None

    NewSerialPort.flushInput()
    NewSerialPort.flushOutput()

    return NewSerialPort


# ------------------- MODBUS CRC16 -----------------------------------------------
def CalculateCrc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc >>= 1
                crc ^= 0xA001
            else:
                crc >>= 1
    return crc


# ------------------- Build MODBUS RTU request -----------------------------------
def BuildModbusRequest(slave_id, function_code, start_address, quantity):
    request = bytearray(8)
    request[0] = slave_id
    request[1] = function_code
    request[2] = (start_address >> 8) & 0xFF
    request[3] = start_address & 0xFF
    request[4] = (quantity >> 8) & 0xFF
    request[5] = quantity & 0xFF

    crc = CalculateCrc16(request[:6])
    request[6] = crc & 0xFF
    request[7] = (crc >> 8) & 0xFF

    return bytes(request)


# ------------------- Test a single slave ID at the current baud rate ------------
def TestModbusAddress(port, slave_id):
    try:
        port.reset_input_buffer()
        port.reset_output_buffer()

        # MODBUS RTU: Read Holding Registers (Function 0x03)
        # Reading 1 register starting at address 0
        request = BuildModbusRequest(slave_id, 0x03, 0x0000, 0x0001)
        port.write(request)

        time.sleep(0.05)

        if port.in_waiting > 0:
            response = port.read(port.in_waiting)

            # Validate response - at minimum should be 5 bytes (slave ID + function + byte count + CRC)
            if len(response) >= 5 and response[0] == slave_id:
                return response.hex(sep="-").upper()
    except serial.SerialTimeoutException:
        pass  # Expected for non-responding addresses
    except Exception:
        pass  # Ignore other errors during scanning

    return None


# ------------------- Scan the bus for baud rate + slave ID ----------------------
def ScanModbusBus(port_name, baud_rates=BAUD_RATES, slave_ids=SLAVE_IDS):
    results = []
    total_steps = len(baud_rates) * len(slave_ids)
    step = 0
    start_time = time.time()

    print(f"Starting MODBUS bus scan on {port_name}")
    print(f"Testing {len(baud_rates)} baud rates x {len(slave_ids)} slave IDs = {total_steps} combinations")

    for baud_rate in baud_rates:
        print(f"\n--- Testing Baud Rate: {baud_rate} ---")

        port = None
        try:
            port = OpenScanPort(port_name, baud_rate)
            if port is None:
                print(f"ERROR at baud rate {baud_rate}: unable to open port")
                continue

            time.sleep(0.05)  # Allow port to stabilize

            for slave_id in slave_ids:
                step += 1
                if step % 50 == 0:
                    print(f"Progress: {step} of {total_steps} ({step * 100 // total_steps}%)")

                response = TestModbusAddress(port, slave_id)
                if response is not None:
                    print(f"✓ FOUND: Baud Rate {baud_rate}, Slave ID {slave_id} - Response: {response}")
                    results.append({"baud_rate": baud_rate, "slave_id": slave_id, "response": response})
                    time.sleep(0.1)  # Extra delay after success

        except Exception as e1:
            print(f"ERROR at baud rate {baud_rate}: {str(e1)} " + GetErrorInfo())
        finally:
            if port is not None:
                port.close()

        time.sleep(0.2)  # Delay between baud rate changes

    duration = time.time() - start_time
    print("\n=== Scan Complete ===")
    print(f"Duration: {duration:.1f} seconds")
    print(f"Found {len(results)} responding configuration(s):")

    if results:
        for result in results:
            print(f"  ✓ Baud Rate: {result['baud_rate']}, Slave ID: {result['slave_id']}")
    else:
        print("  No responding devices found.")

    return results


# ------------------GetErrorInfo-------------------------------------------------
def GetErrorInfo():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# ------------------- Command-line interface for monitor ------------------------
if __name__ == "__main__":  # usage modbusscan.py [port]

    if UseLegacySerialName():
        defaultDevice = "/dev/serial0"
    else:
        defaultDevice = "/dev/ttyAMA0"

    if len(sys.argv) >= 2:
        device = sys.argv[1]
    else:
        device = SelectSerialPort()
        if device is None:
            device = defaultDevice

    print(
        "\nNote: Genmon must NOT be running for this test to work properly. If Genmon is running this test will not function properly,"
    )
    print(f"\nScanning MODBUS bus on serial port {device}...\n")

    try:
        ScanModbusBus(device)
    except KeyboardInterrupt:
        print("\nScan interrupted by user.")
    except Exception as e1:
        print("error communicating...: " + str(e1) + " " + GetErrorInfo())

    sys.exit(0)
