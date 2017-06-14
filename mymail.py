#!/usr/bin/env python
#------------------------------------------------------------
#    FILE: mymail.py
# PURPOSE: send mail messages and receive commands via email
#
#  AUTHOR: Jason G Yates
#    DATE: 18-Nov-2016
#
# MODIFICATIONS:
#------------------------------------------------------------

import datetime, time, smtplib, threading
import imaplib, email, email.header
import os
from os.path import basename
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate

import atexit, ConfigParser
import mylog

#imaplib.Debug = 4


#------------ MyMail class --------------------------------------------
class MyMail:
    def __init__(self, monitor = False, incoming_folder = None, processed_folder = None, incoming_callback = None, localinit = False):

        self.Monitor = monitor                          # true if we receive IMAP email
        self.IncomingFolder = incoming_folder           # folder to look for incoming email
        self.ProcessedFolder = processed_folder         # folder to move mail to once processed
        self.IncomingCallback = incoming_callback       # called back with mail subject as a parameter
        self.Mailbox = 0
        self.EmailSendQueue = []                        # queue for email to send
        self.DisableEmail = False

        # log errors in this module to a file
        if localinit == True:
            logfile = "mymail.log"
            configfile = "mymail.conf"
        else:
            logfile = "/var/log/mymail.log"
            configfile = "/etc/mymail.conf"

        self.log = mylog.SetupLogger("mymail", logfile)

        atexit.register(self.Cleanup)
        try:
            config = ConfigParser.RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read(configfile)

            self.EmailPassword = config.get('MyMail', 'email_pw')
            self.EmailAccount = config.get('MyMail', 'email_account')
            self.EmailRecipient = config.get('MyMail', 'email_recipient')
            self.SMTPServer = config.get('MyMail', 'smtp_server')
            self.IMAPServer = config.get('MyMail', 'imap_server')
            self.SMTPPort = config.getint('MyMail', 'smtp_port')
            if config.has_option('MyMail', 'disableemail'):
                self.DisableEmail = config.getboolean('MyMail', 'disableemail')
        except Exception as e1:
            self.FatalError("ERROR: Unable to read config file" + str(e1))


        atexit.register(self.Cleanup)

        if not self.DisableEmail:
            if self.SMTPServer != "":
                self.threadSendEmail = threading.Thread(target=self.SendMailThread, name = "SendMailThread")
                self.threadSendEmail.daemon = True
                self.threadSendEmail.start()       # start server thread

            if monitor:     # if True then we will have an IMAP monitor thread
                if incoming_callback and incoming_folder and processed_folder and self.IMAPServer != "":
                    self.threadEmail = threading.Thread(target=self.EmailCommandThread, name = "EmailCommandThread")
                    self.threadEmail.daemon = True
                    self.threadEmail.start()       # start server thread
                else:
                    self.FatalError("ERROR: incoming_callback, incoming_folder and processed_folder are required if receive IMAP is used")

    #---------- MyMail.GetSendEmailThreadObject -------------------------
    def GetSendEmailThreadObject(self):

        if not self.DisableEmail:
            return self.threadSendEmail
        else:
            return 0

    #---------- MyMail.GetEmailMonitorThreadObject -------------------------
    def GetEmailMonitorThreadObject(self):

        if not self.DisableEmail:
            if self.Monitor:
                return self.threadEmail
            else:
                return 0
        else:
            return 0

    #---------- MyMail.EmailCommandThread -----------------------------------
    def Cleanup(self):

        if self.Monitor:
            if self.Mailbox:
                self.Mailbox.close()
                self.Mailbox.logout()

    #---------- MyMail.EmailCommandThread -----------------------------------
    def EmailCommandThread(self):

        while True:
            # start email command thread
            try:
                self.Mailbox = imaplib.IMAP4_SSL(self.IMAPServer)
            except Exception:
                self.LogError( "No Internet Connection! ")
                time.sleep(120)
                continue   # exit thread
            try:
                data = self.Mailbox.login(self.EmailAccount, self.EmailPassword)
            except Exception:
                self.LogError( "LOGIN FAILED!!! ")
                time.sleep(60)
                continue   # exit thread
            while True:
                try:
                    rv, data = self.Mailbox.select(self.IncomingFolder)
                    if rv != 'OK':
                        self.LogError( "Error selecting mail folder! (select)")
                        time.sleep(15)
                        continue
                    rv, data = self.Mailbox.search(None, "ALL")
                    if rv != 'OK':
                        self.LogError( "No messages found! (search)")
                        time.sleep(15)
                        continue
                    for num in data[0].split():
                        rv, data = self.Mailbox.fetch(num, '(RFC822)')
                        if rv != 'OK':
                            self.LogError( "ERROR getting message (fetch)")
                            printToScreen( num)
                            time.sleep(15)
                            continue
                        msg = email.message_from_string(data[0][1])
                        decode = email.header.decode_header(msg['Subject'])[0]
                        subject = unicode(decode[0])
                        #print( 'Message %s: %s' % (num, subject))

                        self.IncomingCallback(subject)

                        # move the message to processed folder
                        result = self.Mailbox.store(num, '+X-GM-LABELS', self.ProcessedFolder)  #add the label
                        #result = M.store(num, '-X-GM-LABELS', "Gate")  # oddly this will not remove the label
                        self.Mailbox.store(num, '+FLAGS', '\\Deleted')     # this is needed to remove the original label
                    time.sleep(15)
                except Exception as e1:
                    self.LogError("Resetting email thread" + str(e1))
                    time.sleep(60)
                    break
            time.sleep(15)
            ## end of outer loop

    #------------ MyMail.sendEmailDirectMIME --------------------------------------------
    # send email, bypass queue
    def sendEmailDirectMIME(self, subjectstr, msgstr, recipient = None, files=None, deletefile = False):

        if recipient == None:
            recipient = self.EmailRecipient

        # update date
        dtstamp=datetime.datetime.now().strftime('%a %d-%b-%Y')
        # update time
        tmstamp=datetime.datetime.now().strftime('%I:%M:%S %p')

        msg = MIMEMultipart()
        msg['From'] = self.EmailAccount
        msg['To'] = recipient
        msg['Date'] = formatdate(localtime=True)
        msg['Subject'] = subjectstr

        body = '\n' + 'Time: ' + tmstamp + '\n' + 'Date: ' + dtstamp + '\n' + msgstr
        msg.attach(MIMEText(body, 'plain', 'us-ascii'))

        # if the files are not found then we skip them but still send the email
        try:
            for f in files or []:

                with open(f, "rb") as fil:
                    part = MIMEApplication(
                        fil.read(),
                        Name=basename(f)
                    )
                    part['Content-Disposition'] = 'attachment; filename="%s"' % basename(f)
                    msg.attach(part)

                if deletefile:
                    os.remove(f)

        except Exception as e1:
            self.LogError("Error attaching file in sendEmailDirectMIME: " + str(e1))

        session = smtplib.SMTP(self.SMTPServer, self.SMTPPort)
        session.ehlo()
        session.starttls()

        session.ehlo
        # this allows support for simple TLS
        if self.EmailPassword != "":
            session.login(self.EmailAccount, self.EmailPassword)
        session.sendmail(self.EmailAccount, recipient, msg.as_string())
        session.quit()
       # end sendEmail()

    #------------MyMail::SendMailThread-----------------------
    def SendMailThread(self):

        # once sendMail is called email messages are queued and then sent from this thread
        while True:
            time.sleep(2)

            while self.EmailSendQueue != []:
                EmailItems = self.EmailSendQueue.pop()
                try:
                    self.sendEmailDirectMIME(EmailItems[0], EmailItems[1], EmailItems[2], EmailItems[3], EmailItems[4])
                except Exception as e1:
                    # put the time back at the end of the queue
                    self.LogError("Error in SendMailThread, retrying: " + str(e1))
                    self.EmailSendQueue.insert(len(self.EmailSendQueue),EmailItems)
                    # sleep for 2 min and try again
                    time.sleep(120)


    #------------MyMail::sendEmail-----------------------
    def sendEmail(self, subjectstr, msgstr, recipient = None, files = None, deletefile = False):

        if not self.DisableEmail:
            self.EmailSendQueue.insert(0,[subjectstr,msgstr,recipient, files, deletefile])

    #---------------------SecurityMonitor::FatalError------------------------
    def LogError(self, Message):
        self.log.error(Message)

    #---------------------SecurityMonitor::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)
