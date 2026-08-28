#!/usr/bin/env python3

import os
import sys

GENMON = "/home/pi/genmon"
sys.path.insert(0, GENMON)

from genmonlib.myclient import ClientInterface

client = ClientInterface(loglocation="/tmp/")
response = client.ProcessMonitorCommand("generator: setremote=start")
client.Close()

print(response)
