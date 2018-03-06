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

import atexit, configparser
import mylog, mythread

#imaplib.Debug = 4


#------------ MyMail class --------------------------------------------
class MyMail:
    def __init__(self, monitor = False, incoming_folder = None, processed_folder = None, incoming_callback = None, localinit = False, loglocation = "/var/log/"):

        self.Monitor = monitor                          # true if we receive IMAP email
        self.IncomingFolder = incoming_folder           # folder to look for incoming email
        self.ProcessedFolder = processed_folder         # folder to move mail to once processed
        self.IncomingCallback = incoming_callback       # called back with mail subject as a parameter
        self.Mailbox = 0
        self.EmailSendQueue = []                        # queue for email to send
        self.DisableEmail = False
        self.SSLEnabled = False


        # log errors in this module to a file
        if localinit == True:
            self.logfile = "mymail.log"
            self.configfile = "mymail.conf"
        else:
            self.logfile = loglocation + "mymail.log"
            self.configfile = "/etc/mymail.conf"

        self.log = mylog.SetupLogger("mymail", self.logfile)

        self.GetConfig()

        atexit.register(self.Cleanup)

        if not self.DisableEmail:
            if self.SMTPServer != "":
                self.threadSendEmail = mythread.MyThread(self.SendMailThread, Name = "SendMailThread")
            else:
                self.LogError("SMTP disabled")

            if self.Monitor and self.IMAPServer != "":     # if True then we will have an IMAP monitor thread
                if incoming_callback and incoming_folder and processed_folder:
                    self.threadReceiveEmail = mythread.MyThread(self.EmailCommandThread, Name = "EmailCommandThread")
                else:
                    self.FatalError("ERROR: incoming_callback, incoming_folder and processed_folder are required if receive IMAP is used")
            else:
                self.LogError("IMAP disabled")

    #---------- MyMail.GetConfig ----------------------
    def GetConfig(self, reload = False):

        try:
            config = configparser.RawConfigParser()
            # config parser reads from current directory, when running form a cron tab this is
            # not defined so we specify the full path
            config.read(self.configfile)

            self.EmailPassword = config.get('MyMail', 'email_pw')
            self.EmailAccount = config.get('MyMail', 'email_account')
            if config.has_option('MyMail', 'sender_account'):
                self.SenderAccount = config.get('MyMail', 'sender_account')
            else:
                self.SenderAccount = self.EmailAccount
            # SMTP Recepients
            self.EmailRecipient = config.get('MyMail', 'email_recipient')
            self.EmailRecipientByType = {}
            for type in ["outage", "error", "warn", "info"]:
                tempList = []
                for email in self.EmailRecipient.split(','):
                    if config.has_option('MyMail', email):
                       if type in config.get('MyMail', email).split(','):
                          tempList.append(email)
                    else:
                       tempList.append(email)
                # print "Inverted List: " + type + " -> " + ",".join(tempList)
                self.EmailRecipientByType[type] = ",".join(tempList)
            # SMTP Server
            if config.has_option('MyMail', 'smtp_server'):
                self.SMTPServer = config.get('MyMail', 'smtp_server')
                self.SMTPServer = self.SMTPServer.strip()
            else:
                self.SMTPServer = ""
            # IMAP Server
            if config.has_option('MyMail', 'imap_server'):
                self.IMAPServer = config.get('MyMail', 'imap_server')
                self.IMAPServer = self.IMAPServer.strip()
            else:
                self.IMAPServer = ""
            self.SMTPPort = config.getint('MyMail', 'smtp_port')
            if config.has_option('MyMail', 'disableemail'):
                self.DisableEmail = config.getboolean('MyMail', 'disableemail')
            if config.has_option('MyMail', 'ssl_enabled'):
                self.SSLEnabled = config.getboolean('MyMail', 'ssl_enabled')
        except Exception as e1:
            if reload:
                self.FatalError("ERROR: Unable to read config file " + str(e1))
                return False
            else:
                self.FatalError("ERROR: Unable to read config file " + str(e1))

        return True

    #---------- MyMail.GetSendEmailThreadObject -------------------------
    def GetSendEmailThreadObject(self):

        if not self.DisableEmail:
            if self.SMTPServer != "":
                return self.threadSendEmail
        return 0

    #---------- MyMail.GetEmailMonitorThreadObject -------------------------
    def GetEmailMonitorThreadObject(self):

        if not self.DisableEmail:
            if self.Monitor and self.IMAPServer != "":
                if self.IncomingCallback != None and self.IncomingFolder != None and self.ProcessedFolder != None:
                    return self.threadReceiveEmail
        return 0

    #---------- MyMail.EmailCommandThread -----------------------------------
    def Cleanup(self):

        self.threadSendEmail.Stop()
        self.threadReceiveEmail.Stop()

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

            if self.threadReceiveEmail.StopSignaled():
                return
            time.sleep(15)
            ## end of outer loop

    #------------ MyMail.sendEmailDirectMIME --------------------------------------------
    # send email, bypass queue
    def sendEmailDirectMIME(self, msgtype, subjectstr, msgstr, recipient = None, files=None, deletefile = False):

        if recipient == None:
            # recipient = self.EmailRecipient
            recipient = self.EmailRecipientByType[msgtype]


        # update date
        dtstamp=datetime.datetime.now().strftime('%a %d-%b-%Y')
        # update time
        tmstamp=datetime.datetime.now().strftime('%I:%M:%S %p')

        msg = MIMEMultipart()
        msg['From'] = self.SenderAccount
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

        self.LogError("Logging in: SMTP Server <"+self.SMTPServer+">:Port <"+str(self.SMTPPort) + ">")

        try:
            if self.SSLEnabled:
                 session = smtplib.SMTP_SSL(self.SMTPServer, self.SMTPPort)
                 session.ehlo()
            else:
                 session = smtplib.SMTP(self.SMTPServer, self.SMTPPort)
                 session.starttls()
                 session.ehlo
                 # this allows support for simple TLS
        except Exception as e1:
            self.LogError("Error SMTP Init : SSL:<" + str(self.SSLEnabled)  + ">: " + str(e1))
            return False

        try:
            if self.EmailPassword != "":
                session.login(str(self.EmailAccount), str(self.EmailPassword))

            if "," in recipient:
                multiple_recipients = recipient.split(",")
                session.sendmail(self.SenderAccount, multiple_recipients, msg.as_string())
            else:
                session.sendmail(self.SenderAccount, recipient, msg.as_string())
        except Exception as e1:
            self.LogError("Error SMTP sendmail: " + str(e1))
            session.quit()
            return False

        session.quit()

        return True
       # end sendEmailDirectMIME()

    #------------MyMail::SendMailThread-----------------------
    def SendMailThread(self):

        # once sendMail is called email messages are queued and then sent from this thread

        while True:

            time.sleep(2)
            if self.threadSendEmail.StopSignaled():
                return

            while self.EmailSendQueue != []:
                MailError = False
                EmailItems = self.EmailSendQueue.pop()
                try:
                    if not (self.sendEmailDirectMIME(EmailItems[0], EmailItems[1], EmailItems[2], EmailItems[3], EmailItems[4], EmailItems[5])):
                        self.LogError("Error in SendMailThread, sendEmailDirectMIME failed, retrying")
                        MailError = True
                except Exception as e1:
                    # put the time back at the end of the queue
                    self.LogError("Error in SendMailThread, retrying (2): " + str(e1))
                    MailError = True

                if MailError:
                    self.EmailSendQueue.insert(len(self.EmailSendQueue),EmailItems)
                    # sleep for 2 min and try again
                    time.sleep(120)


    #------------MyMail::sendEmail-----------------------
    # msg type must be one of "outage", "error", "warn", "info"
    def sendEmail(self, subjectstr, msgstr, recipient = None, files = None, deletefile = False, msgtype = "error"):

        if not self.DisableEmail:       # if all email disabled, do not queue
            if self.SMTPServer != "":    # if only sending is disabled, do not queue
                self.EmailSendQueue.insert(0,[msgtype,subjectstr,msgstr,recipient, files, deletefile])

    #---------------------SecurityMonitor::FatalError------------------------
    def LogError(self, Message):
        self.log.error(Message)

    #---------------------SecurityMonitor::FatalError------------------------
    def FatalError(self, Message):

        self.log.error(Message)
        raise Exception(Message)
