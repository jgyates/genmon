#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mymsgqueue.py
# PURPOSE: message queue with retry support
#
#  AUTHOR: Jason G Yates
#    DATE: 16-Feb-2022
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import datetime
import threading
import time

from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread


# ------------ MyMsgQueue class -------------------------------------------------
class MyMsgQueue(MySupport):
    # ------------ MyMsgQueue::init----------------------------------------------
    def __init__(self, config=None, log=None, debug=False,callback=None, minimum_wait_between_messages = 0):
        super(MyMsgQueue, self).__init__()
        self.log = log
        self.config = config
        self.callback = callback
        self.MessageQueue = []

        self.QueueLock = threading.RLock()

        self.max_retry_time = 600  # 10 min
        self.default_wait = 120  # 2 min
        self.minimum_wait_between_messages = minimum_wait_between_messages
        self.last_message_sent_time = None

        self.debug = debug

        if self.config != None:
            try:
                self.max_retry_time = self.config.ReadValue(
                    "max_retry_time", return_type=int, default=600
                )
                self.default_wait = self.config.ReadValue(
                    "default_wait", return_type=int, default=120
                )
                self.minimum_wait_between_messages = self.config.ReadValue(
                    "minimum_wait_between_messages", return_type=int, default=minimum_wait_between_messages
                )
                self.debug = self.config.ReadValue(
                    "debug", return_type=bool, default=False
                )
                self.LogDebug("Min Wait Between Messages: " + str(self.minimum_wait_between_messages))
            except Exception as e1:
                self.LogErrorLine(
                    "Error in MyMsgQueue:init, error reading config: " + str(e1)
                )
        if not self.callback == None:
            self.Threads["QueueWorker"] = MyThread(
                self.QueueWorker, Name="QueueWorker", start=False
            )
            self.Threads["QueueWorker"].Start()

    # ------------ MyMsgQueue::QueueWorker---------------------------------------
    def QueueWorker(self):

        # once SendMessage is called messages are queued and then sent from this thread
        time.sleep(0.1)
        while True:

            while self.MessageQueue != []:
                messageError = False
                try:
                    message_time = datetime.datetime.now()
                    if self.last_message_sent_time != None and ((message_time - self.last_message_sent_time).total_seconds() < self.minimum_wait_between_messages):
                        if self.WaitForExit("QueueWorker", self.minimum_wait_between_messages):
                            return
                        continue
                    with self.QueueLock:
                        MessageItems = self.MessageQueue.pop()
                    if len(MessageItems[1]):
                        ret_val = self.callback(MessageItems[0], **MessageItems[1])
                    else:
                        ret_val = self.callback(MessageItems[0])
                    if not (ret_val):
                        self.LogError("Error sending message in QueueWorker, callback failed, retrying")
                        messageError = True
                except Exception as e1:
                    self.LogErrorLine("Error in QueueWorker, retrying (2): " + str(e1))
                    messageError = True

                try:
                    if messageError:
                        # check max retry timeout
                        retry_duration = datetime.datetime.now() - MessageItems[2]
                        if retry_duration.total_seconds() <= self.max_retry_time:
                            with self.QueueLock:
                                # put the message back at the end of the queue
                                self.MessageQueue.insert(
                                    len(self.MessageQueue), MessageItems
                                )
                            # sleep for 2 min and try again
                            if self.WaitForExit("QueueWorker", self.default_wait):
                                return
                        else:
                            self.LogDebug("Message retry expired: " + MessageItems[0])
                    else:
                        # message was sent
                        self.LogDebug("Message Sent")
                        self.last_message_sent_time = message_time
                except Exception as e1:
                    self.LogErrorLine(
                        "Error in QueueWorker requeue, retrying (3): " + str(e1)
                    )

            if self.WaitForExit("QueueWorker", 2):
                return

    # ------------ MyMsgQueue::SendMessage---------------------------------------
    def SendMessage(self, message, **kwargs):
        try:
            if self.callback != None:
                with self.QueueLock:
                    MessageItems = []
                    MessageItems.append(message)
                    MessageItems.append(kwargs)
                    MessageItems.append(datetime.datetime.now())
                    self.MessageQueue.insert(0, MessageItems)
        except Exception as e1:
            self.LogErrorLine("Error in MyMsgQueue:SendMessage: " + str(e1))

    # ------------ MyMsgQueue::Close---------------------------------------------
    def Close(self):

        try:
            if not self.callback == None:
                self.KillThread("QueueWorker")
        except Exception as e1:
            self.LogErrorLine("Error in MyMsgQueue:Close: " + str(e1))
