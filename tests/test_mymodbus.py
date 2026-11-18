#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_mymodbus.py
# PURPOSE: Tests for genmonlib/mymodbus.py, the Modbus protocol genmon uses
#          to talk to the controllers (Modbus RTU over a serial port or serial
#          over TCP, and Modbus TCP): the request packets for each function
#          (read, write registers / coils, files) with their CRC or Modbus TCP
#          header, reading the reply packets (partial, wrong address, bad CRC,
#          error replies), and a whole transaction.
#
#          The serial device is a fake: nothing is sent.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_mymodbus
#
# -------------------------------------------------------------------------------

import logging
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

import crcmod.predefined  # noqa: E402

from genmonlib import mymodbus  # noqa: E402
from genmonlib.myconfig import MyConfig  # noqa: E402

CRC = crcmod.predefined.mkCrcFun("modbus")


def with_crc(packet):
    crc = CRC(bytearray(packet))
    return list(packet) + [crc & 0xFF, crc >> 8]


class FakeSlave(object):
    """The serial device: records what is written; Buffer holds the bytes
    received. reply(packet) may answer each request."""

    def __init__(self, *args, **kwargs):
        self.Buffer = []
        self.written = []
        self.Threads = {}
        self.reply = None

    def Write(self, data):
        self.written.append(list(data))
        if self.reply:
            self.Buffer.extend(self.reply(list(data)))

    def Flush(self):
        del self.Buffer[:]

    def DiscardByte(self):
        if len(self.Buffer):
            return self.Buffer.pop(0)

    def Close(self):
        pass

    def GetCommStats(self):
        return []

    def ResetCommStats(self):
        pass


class ModbusTestCase(unittest.TestCase):

    def protocol(self, address="01", modbus_tcp=False, updates=None):
        folder = tempfile.mkdtemp(prefix="mymodbus_")
        self.addCleanup(shutil.rmtree, folder)
        shutil.copy(os.path.join(REPO_DIR, "conf", "genmon.conf"), folder)
        config = MyConfig(filename=os.path.join(folder, "genmon.conf"), section="GenMon")
        for key, value in {"loglocation": folder, "address": address, "use_serial_tcp": "False",
                           "modbus_tcp": str(modbus_tcp)}.items():
            config.WriteValue(key, value)
        for patch in [mock.patch.object(mymodbus, "SerialDevice", FakeSlave),
                      mock.patch.object(mymodbus, "SerialTCPDevice", FakeSlave)]:
            patch.start()
            self.addCleanup(patch.stop)
        if updates is None:
            updates = []
        def update(*args, **kwargs):  # genmon's UpdateRegisterList (True: accepted)
            updates.append(args)
            return True

        protocol = mymodbus.ModbusProtocol(update, config=config)
        protocol.ModbusTCP = modbus_tcp
        self.addCleanup(self.close_logs)
        return protocol

    @staticmethod
    def close_logs():
        for name in ["mymodbus", "mymodbus_console"]:
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                handler.close()
                logger.removeHandler(handler)


# -------------------------------------------------------------------------------
class RequestPacketTests(ModbusTestCase):

    def test_read_holding_registers(self):
        # the textbook example: slave 1, registers 0000-0009
        m = self.protocol()
        self.assertEqual(m.CreateMasterPacket("0000", length=10),
                         [0x01, 0x03, 0x00, 0x00, 0x00, 0x0A, 0xC5, 0xCD])
        self.assertTrue(m.CheckCRC(m.CreateMasterPacket("0000", length=10)))

    def test_read_coils_and_inputs(self):
        m = self.protocol(address="9d")
        self.assertEqual(m.CreateMasterPacket("0010", length=8, command=m.MBUS_CMD_READ_COILS),
                         with_crc([0x9D, 0x01, 0x00, 0x10, 0x00, 0x08]))
        self.assertEqual(m.CreateMasterPacket("0200", length=2, command=m.MBUS_CMD_READ_INPUT_REGS),
                         with_crc([0x9D, 0x04, 0x02, 0x00, 0x00, 0x02]))

    def test_write_registers(self):
        m = self.protocol()
        self.assertEqual(m.CreateMasterPacket("002c", length=2, command=m.MBUS_CMD_WRITE_REGS,
                                              data=[0x0D, 0x1E, 0x00, 0x01]),
                         with_crc([0x01, 0x10, 0x00, 0x2C, 0x00, 0x02, 0x04, 0x0D, 0x1E, 0x00, 0x01]))

    def test_write_single_register_and_coil(self):
        m = self.protocol()
        self.assertEqual(m.CreateMasterPacket("0003", length=1, command=m.MBUS_CMD_WRITE_REG, data=[0x00, 0x0F]),
                         with_crc([0x01, 0x06, 0x00, 0x03, 0x00, 0x0F]))
        # a coil is on (FF00) for any value but 0
        self.assertEqual(m.CreateMasterPacket("0005", length=1, command=m.MBUS_CMD_WRITE_COIL, data=[0x00, 0x01]),
                         with_crc([0x01, 0x05, 0x00, 0x05, 0xFF, 0x00]))
        self.assertEqual(m.CreateMasterPacket("0005", length=1, command=m.MBUS_CMD_WRITE_COIL, data=[0x00, 0x00]),
                         with_crc([0x01, 0x05, 0x00, 0x05, 0x00, 0x00]))

    def test_write_coils(self):
        # coil n is bit n % 8 of byte n // 8 (only the first coil of each byte
        # was set)
        m = self.protocol()
        self.assertEqual(m.CreateMasterPacket("0013", length=3, command=m.MBUS_CMD_WRITE_COILS,
                                              data=[0, 1, 0, 0, 0, 1]),  # on, off, on
                         with_crc([0x01, 0x0F, 0x00, 0x13, 0x00, 0x03, 0x01, 0b00000101]))
        nine = [0, 1] * 9  # 9 coils on: 2 bytes
        self.assertEqual(m.CreateMasterPacket("0000", length=9, command=m.MBUS_CMD_WRITE_COILS, data=nine),
                         with_crc([0x01, 0x0F, 0x00, 0x00, 0x00, 0x09, 0x02, 0xFF, 0x01]))
        self.assertEqual(m.CreateMasterPacket("0000", length=1, command=m.MBUS_CMD_WRITE_COILS, data=[0, 1]),
                         with_crc([0x01, 0x0F, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01]))

    def test_files(self):
        m = self.protocol(address="9d")
        self.assertEqual(m.CreateMasterPacket("0040", length=2, command=m.MBUS_CMD_READ_FILE, file_num=1),
                         with_crc([0x9D, 0x14, 0x07, 0x06, 0x00, 0x01, 0x00, 0x40, 0x00, 0x02]))
        packet = m.CreateMasterPacket("0040", length=1, command=m.MBUS_CMD_WRITE_FILE, data=[0x12, 0x34])
        self.assertEqual(packet[:2], [0x9D, 0x15])
        self.assertEqual(packet[3:-2], [0x06, 0x00, 0x01, 0x00, 0x40, 0x00, 0x01, 0x12, 0x34])
        self.assertTrue(m.CheckCRC(packet))

    def test_invalid_requests(self):
        m = self.protocol()
        for args, kwargs in [(("10000",), {}),                                         # register too big
                             (("0001",), {"command": m.MBUS_CMD_WRITE_REGS, "data": []}),
                             (("0001",), {"length": 2, "command": m.MBUS_CMD_WRITE_REGS, "data": [0, 1]}),
                             (("0001",), {"length": 2, "command": m.MBUS_CMD_WRITE_REG, "data": [0, 1, 0, 2]}),
                             (("0001",), {"command": 0x2B}),                              # unknown function
                             (("0001",), {"command": m.MBUS_CMD_READ_FILE, "file_num": 0x10000})]:
            with self.subTest(args=args, kwargs=kwargs):
                before = m.ComValidationError
                self.assertEqual(m.CreateMasterPacket(*args, **kwargs), [])
                self.assertEqual(m.ComValidationError, before + 1)

    def test_modbus_tcp(self):
        # Modbus TCP: a header (transaction id, protocol 0, length) and no CRC
        m = self.protocol(modbus_tcp=True)
        packet = m.CreateMasterPacket("0000", length=10)
        self.assertEqual(packet[2:], [0x00, 0x00, 0x00, 0x06, 0x01, 0x03, 0x00, 0x00, 0x00, 0x0A])
        second = m.CreateMasterPacket("0000", length=10)
        self.assertNotEqual(packet[:2], second[:2])  # a new transaction id


# -------------------------------------------------------------------------------
class ReplyPacketTests(ModbusTestCase):

    def receive(self, m, data):
        m.Slave.Buffer = list(data)
        return m.GetPacketFromSlave()

    def test_read_reply(self):
        m = self.protocol()
        reply = with_crc([0x01, 0x03, 0x04, 0x00, 0x01, 0x00, 0x02])
        self.assertEqual(self.receive(m, reply), (True, reply))
        self.assertEqual(m.Slave.Buffer, [])

    def test_partial_reply(self):
        # not all there yet: wait for more
        m = self.protocol()
        reply = with_crc([0x01, 0x03, 0x04, 0x00, 0x01, 0x00, 0x02])
        self.assertEqual(self.receive(m, reply[:5]), (True, []))
        self.assertEqual(self.receive(m, []), (True, []))

    def test_bad_crc(self):
        m = self.protocol()
        reply = with_crc([0x01, 0x03, 0x04, 0x00, 0x01, 0x00, 0x02])
        reply[-1] ^= 0xFF
        ok, packet = self.receive(m, reply)
        self.assertFalse(ok)
        self.assertEqual(m.CrcError, 1)

    def test_wrong_address(self):
        # a reply from another address: an error, the received bytes dropped
        m = self.protocol()
        reply = with_crc([0x01, 0x03, 0x02, 0x00, 0x07])
        self.assertEqual(self.receive(m, [0x55] + reply), (False, []))
        self.assertEqual(m.Slave.Buffer, [])

    def test_error_reply(self):
        # the function code with 0x80: an exception code
        m = self.protocol()
        before = m.ComValidationError + m.ExcepFunction + m.ExcepAddress
        ok, packet = self.receive(m, with_crc([0x01, 0x83, 0x02]))
        self.assertEqual(m.ExcepAddress, 1)
        self.assertEqual(m.GetExceptionString(0x02), "Illegal Address: 02")
        self.assertGreater(m.ComValidationError + m.ExcepFunction + m.ExcepAddress, before)

    def test_write_replies(self):
        m = self.protocol()
        multiple = with_crc([0x01, 0x10, 0x00, 0x2C, 0x00, 0x02])
        self.assertEqual(self.receive(m, multiple), (True, multiple))
        single = with_crc([0x01, 0x06, 0x00, 0x03, 0x00, 0x0F])
        self.assertEqual(self.receive(m, single), (True, single))

    def test_modbus_tcp_reply(self):
        m = self.protocol(modbus_tcp=True)
        m.CreateMasterPacket("0000", length=1)
        tid = m.CurrentTransactionID  # the reply has the id of the request
        reply = [tid >> 8, tid & 0xFF, 0x00, 0x00, 0x00, 0x05, 0x01, 0x03, 0x02, 0x12, 0x34]
        self.assertEqual(self.receive(m, reply), (True, reply[6:]))  # without the header
        # another protocol id: dropped
        bad = [tid >> 8, tid & 0xFF, 0x00, 0x01, 0x00, 0x05, 0x01, 0x03, 0x02, 0x12, 0x34]
        self.assertEqual(self.receive(m, bad)[1], [])


# -------------------------------------------------------------------------------
class TransactionTests(ModbusTestCase):

    def test_read_registers(self):
        # a whole read: request, reply, the register values passed to genmon
        updates = []
        m = self.protocol(address="9d", updates=updates)
        m.Slave.reply = lambda request: with_crc([0x9D, 0x03, 0x04, 0x00, 0x01, 0x00, 0x02])
        self.assertEqual(m.ProcessTransaction("0010", 2), "00010002")
        self.assertEqual(m.Slave.written, [with_crc([0x9D, 0x03, 0x00, 0x10, 0x00, 0x02])])
        self.assertEqual(updates[-1][:2], ("0010", "00010002"))

    def test_write_registers(self):
        m = self.protocol(address="9d")
        m.Slave.reply = lambda request: with_crc(request[:6])
        m.ProcessWriteTransaction("002c", 1, [0x0D, 0x1E])
        self.assertEqual(m.Slave.written, [with_crc([0x9D, 0x10, 0x00, 0x2C, 0x00, 0x01, 0x02, 0x0D, 0x1E])])

    def test_timeout(self):
        # no reply: an empty value and a timeout counted
        m = self.protocol()
        m.ModBusPacketTimoutMS = 50
        with mock.patch.object(mymodbus.time, "sleep"):
            self.assertEqual(m.ProcessTransaction("0010", 2), "")
        self.assertEqual(m.ComTimoutError, 1)


if __name__ == "__main__":
    unittest.main()
