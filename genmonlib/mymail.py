#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mymail.py
# PURPOSE: send mail messages and receive commands via email
#
#  AUTHOR: Jason G Yates
#    DATE: 18-Nov-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import atexit
import datetime
import email
import email.header
import imaplib
import os
import smtplib
import sys
import time
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import COMMASPACE, formatdate
from os.path import basename
from shutil import copyfile

import idna

from genmonlib.myconfig import MyConfig
from genmonlib.mylog import SetupLogger
from genmonlib.mysupport import MySupport
from genmonlib.mythread import MyThread
from genmonlib.program_defaults import ProgramDefaults


# ------------ MyMail class -----------------------------------------------------
class MyMail(MySupport):
    def __init__(
        self,
        monitor=False,
        incoming_folder=None,
        processed_folder=None,
        incoming_callback=None,
        localinit=False,
        loglocation=ProgramDefaults.LogPath,
        ConfigFilePath="/etc/",
        log=None,
        start=True,
    ):

        self.Monitor = monitor  # true if we receive IMAP email
        self.IncomingFolder = incoming_folder  # folder to look for incoming email
        self.ProcessedFolder = processed_folder  # folder to move mail to once processed
        self.IncomingCallback = (
            incoming_callback  # called back with mail subject as a parameter
        )
        if ConfigFilePath == None or ConfigFilePath == "":
            self.ConfigFilePath = "/etc/"
        else:
            self.ConfigFilePath = ConfigFilePath
        self.Mailbox = 0
        self.EmailSendQueue = []  # queue for email to send
        self.DisableEmail = False
        self.DisableIMAP = False
        self.DisableSNMP = False
        self.DisableSmtpAuth = False
        self.SSLEnabled = False
        self.TLSDisable = False
        self.UseBCC = False
        self.UseHTML = False
        self.ExtendWait = 0
        self.Threads = {}  # Dict of mythread objects
        self.debug = False
        self.ModulePath = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        # log errors in this module to a file
        if localinit == True:
            self.logfile = "mymail.log"
            self.configfile = "mymail.conf"
        else:
            self.logfile = os.path.join(loglocation, "mymail.log")
            self.configfile = os.path.join(self.ConfigFilePath, "mymail.conf")

        if log == None:
            self.log = SetupLogger("mymail", self.logfile)
        else:
            self.log = log
        self.console = None

        # if mymail.conf is present attempt to copy it from the
        # main source directory
        if not os.path.isfile(self.configfile):
            if os.path.isfile(os.path.join(self.ModulePath, "mymail.conf")):
                copyfile(os.path.join(self.ModulePath, "mymail.conf"), self.configfile)
            else:
                self.LogError("Missing config file : " + self.configfile)
                self.FatalError("Missing config file : " + self.configfile)

        self.config = MyConfig(filename=self.configfile, section="MyMail", log=self.log)

        self.GetConfig()

        if self.DisableEmail:
            self.DisableIMAP = True
            self.DisableSNMP = True
            self.Monitor = False

        if not len(self.SMTPServer):
            self.DisableSNMP = True

        if not len(self.IMAPServer):
            self.DisableIMAP = True
            self.Monitor = False

        atexit.register(self.Close)

        if not self.DisableEmail:
            if not self.DisableSMTP and self.SMTPServer != "":
                self.Threads["SendMailThread"] = MyThread(
                    self.SendMailThread, Name="SendMailThread", start=start
                )
            else:
                self.LogError("SMTP disabled")

            if (
                not self.DisableIMAP and self.Monitor and self.IMAPServer != ""
            ):  # if True then we will have an IMAP monitor thread
                if incoming_callback and incoming_folder and processed_folder:
                    self.Threads["EmailCommandThread"] = MyThread(
                        self.EmailCommandThread, Name="EmailCommandThread", start=start
                    )
                    self.LogError("IMAP enabled")
                else:
                    self.FatalError(
                        "ERROR: incoming_callback, incoming_folder and processed_folder are required if receive IMAP is used"
                    )

    # ---------- MyMail.TestSendSettings ----------------------------------------
    @staticmethod
    def TestSendSettings(
        smtp_server=None,
        smtp_port=587,
        email_account=None,
        sender_account=None,
        sender_name=None,
        recipient=None,
        password=None,
        use_ssl=False,
        tls_disable=False,
        smtpauth_disable=False,
        use_html = False
    ):

        try:
            if smtp_server == None or not len(smtp_server):
                return "Error: Invalid SMTP server"

            if not isinstance(smtpauth_disable, bool) and (
                email_account == None or not len(email_account)
            ):
                return "Error: Invalid email account"

            if sender_account == None or not len(sender_account):
                sender_account = email_account

            if recipient == None or not len(recipient):
                return "Error: Invalid email recipient"

            if password == None or not len(password):
                password = ""

            if smtp_port == None or not isinstance(smtp_port, int):
                return "Error: Invalid SMTP port"

            if use_ssl == None or not isinstance(use_ssl, bool):
                return "Error: Invalid Use SSL value"

            if tls_disable == None or not isinstance(tls_disable, bool):
                return "Error: Invalid TLS Disable value"

            # update date
            dtstamp = datetime.datetime.now().strftime("%a %d-%b-%Y")
            # update time
            tmstamp = datetime.datetime.now().strftime("%I:%M:%S %p")

            try:
                import email.policy
                parent = MIMEMultipart('mixed',policy=email.policy.SMTP)
            except:
                parent = MIMEMultipart('mixed')

            if use_html:
                subtype = 'alternative'
            else:
                subtype = 'mixed'
            if sys.version_info[0] < 3:  # PYTHON 2
                msg = MIMEMultipart(subtype)
            else:  # PYTHON 3
                try:
                    import email.policy

                    msg = MIMEMultipart(subtype,policy=email.policy.SMTP)
                except:
                    msg = MIMEMultipart(subtype)

            parent.attach(msg)
            if sender_name == None or not len(sender_name):
                parent["From"] = "<" + sender_account + ">"
            else:
                parent["From"] = sender_name + " <" + sender_account + ">"
        except Exception as e1:
            return "Error Initializing email: " + str(e1)
        try:
            recipientList = recipient.strip().split(",")
            recipientList = map(lambda x: x.strip(), recipientList)
            recipienttemp = ">,<"
            recipienttemp = recipienttemp.join(recipientList)
            recipient = "<" + recipienttemp + ">"
        except Exception as e1:
            pass
        try:
            parent["To"] = recipient
            parent["Date"] = formatdate(localtime=True)
            parent["Subject"] = "Genmon Test Email"

            msgstr = "\r\n" + "Test email from genmon\r\n"
            body = ("\r\n" + "Time: " + tmstamp + "\r\n"
                    + "Date: " + dtstamp + "\r\n"
                    + msgstr
            )
            if use_html:
                html_message = MyMail.ConvertTextToHTML(body)

            if sys.version_info[0] < 3:  # PYTHON 2
                msg.attach(MIMEText(body, "plain"))
                if use_html:
                    msg.attach(MIMEText(html_message, "html"))
            else:  # PYTHON 3
                try:
                    msg.attach(
                        MIMEText(
                            body, "plain", _charset="utf-8", policy=email.policy.SMTP
                        )
                    )
                    if use_html:
                        msg.attach(
                            MIMEText(
                                html_message, "html", _charset="utf-8", policy=email.policy.SMTP
                            )
                        )
                except:
                    msg.attach(MIMEText(body, "plain"))
        except Exception as e1:
            return "Error formatting email: " + str(e1)

        try:
            if use_ssl:
                session = smtplib.SMTP_SSL(smtp_server, smtp_port)
                session.ehlo()
            else:
                session = smtplib.SMTP(smtp_server, smtp_port)
                if not tls_disable:
                    session.starttls()
                session.ehlo
                # this allows support for simple TLS
        except Exception as e1:
            # self.LogErrorLine("Error Test SMTP : SSL:<" + str(use_ssl)  + ">: " + str(e1))
            return "Error Initializing SMTP library: " + str(e1)

        try:
            if password != "" and not smtpauth_disable:
                session.login(MyMail.FilterAddress(email_account), str(password))

            if sys.version_info[0] < 3:  # PYTHON 2
                message = parent.as_string()
            else:  # PYTHON 3
                message = parent.as_bytes()

            if "," in recipient:
                multiple_recipients = recipient.split(",")
                session.sendmail(
                    MyMail.FilterAddress(sender_account), multiple_recipients, message
                )
            else:
                session.sendmail(
                    MyMail.FilterAddress(sender_account), recipient, message
                )
        except Exception as e1:
            # self.LogErrorLine("Error SMTP sendmail: " + str(e1))
            errorstring = str(e1)
            try:
                session.quit()
            except:
                pass
            return "Error sending email: " + str(errorstring)

        session.quit()
        return "Success"

    # ------------ MyMail.FilterAddress -----------------------------------------
    @staticmethod
    def FilterAddress(address):

        if isinstance(address, list):
            returnList = []
            for oneAddress in address:
                oneAddress = oneAddress.strip()
                addressSplit = oneAddress.split("@")
                if len(addressSplit) > 1:
                    returnList.append(
                        addressSplit[0]
                        + "@"
                        + idna.encode(addressSplit[1]).decode("ascii")
                    )
                else:
                    returnList.append(oneAddress)
            return returnList
        else:
            address = address.strip()
            addressSplit = address.split("@")
            if len(addressSplit) > 1:
                address = (
                    str(addressSplit[0])
                    + "@"
                    + str(idna.encode(addressSplit[1]).decode("ascii"))
                )
            return address

    # ---------- MyMail.ConvertTextToHTML --------------------------------------
    @staticmethod
    def ConvertTextToHTML(text):
        try:
            return "<pre>" + text + "</pre>"
        except:
            return text

    # ---------- MyMail.GetConfig -----------------------------------------------
    def GetConfig(self, reload=False):

        try:

            if self.config.HasOption("disableemail"):
                self.DisableEmail = self.config.ReadValue(
                    "disableemail", return_type=bool
                )
            else:
                self.DisableEmail = False

            if self.config.HasOption("disablesmtp"):
                self.DisableSMTP = self.config.ReadValue(
                    "disablesmtp", return_type=bool
                )
            else:
                self.DisableSMTP = False

            if self.config.HasOption("smtpauth_disable"):
                self.DisableSmtpAuth = self.config.ReadValue(
                    "smtpauth_disable", return_type=bool
                )
            else:
                self.DisableSmtpAuth = False

            if self.config.HasOption("disableimap"):
                self.DisableIMAP = self.config.ReadValue(
                    "disableimap", return_type=bool
                )
            else:
                self.DisableIMAP = False

            if self.config.HasOption("usebcc"):
                self.UseBCC = self.config.ReadValue("usebcc", return_type=bool)
            
            if self.config.HasOption("use_html"):
                self.UseHTML = self.config.ReadValue("use_html", return_type=bool)

            if self.config.HasOption("extend_wait"):
                self.ExtendWait = self.config.ReadValue(
                    "extend_wait", return_type=int, default=0, NoLog=True
                )

            self.debug = self.config.ReadValue("debug", return_type=bool, default=False)

            self.EmailPassword = self.config.ReadValue("email_pw", default="")
            self.EmailPassword = self.EmailPassword.strip()
            self.EmailAccount = self.config.ReadValue("email_account")
            if self.config.HasOption("sender_account"):
                self.SenderAccount = self.config.ReadValue("sender_account")
                self.SenderAccount = self.SenderAccount.strip()
                if not len(self.SenderAccount):
                    self.SenderAccount = self.EmailAccount
            else:
                self.SenderAccount = self.EmailAccount

            self.SenderName = self.config.ReadValue("sender_name", default=None)

            # SMTP Recipients
            self.EmailRecipient = self.config.ReadValue("email_recipient")
            self.EmailRecipientByType = {}
            for type in ["outage", "error", "warn", "info"]:
                tempList = []
                for email in self.EmailRecipient.split(","):
                    if self.config.HasOption(email):
                        if type in self.config.ReadValue(email).split(","):
                            tempList.append(email)
                    else:
                        tempList.append(email)

                self.EmailRecipientByType[type] = ",".join(tempList)
            # SMTP Server
            if self.config.HasOption("smtp_server"):
                self.SMTPServer = self.config.ReadValue("smtp_server")
                self.SMTPServer = self.SMTPServer.strip()
            else:
                self.SMTPServer = ""
            # IMAP Server
            if self.config.HasOption("imap_server"):
                self.IMAPServer = self.config.ReadValue("imap_server")
                self.IMAPServer = self.IMAPServer.strip()
            else:
                self.IMAPServer = ""
            self.SMTPPort = self.config.ReadValue(
                "smtp_port", return_type=int, default=587
            )

            if self.config.HasOption("ssl_enabled"):
                self.SSLEnabled = self.config.ReadValue("ssl_enabled", return_type=bool)

            self.TLSDisable = self.config.ReadValue(
                "tls_disable", return_type=bool, default=False
            )

        except Exception as e1:
            self.LogErrorLine("ERROR: Unable to read config file : " + str(e1))
            sys.exit(1)

        return True

    # ---------- MyMail.Close ---------------------------------------------------
    def Close(self):
        try:
            if not self.DisableEmail:
                if self.SMTPServer != "" and not self.DisableSMTP:
                    try:
                        self.Threads["SendMailThread"].Stop()
                    except:
                        pass

            if not self.DisableEmail:
                if self.Monitor and self.IMAPServer != "" and not self.DisableIMAP:
                    if (
                        self.IncomingCallback != None
                        and self.IncomingFolder != None
                        and self.ProcessedFolder != None
                    ):
                        try:
                            self.Threads["EmailCommandThread"].Stop()
                        except:
                            pass

            if self.Monitor:
                if self.Mailbox:
                    try:
                        self.Mailbox.close()
                        self.Mailbox.logout()
                    except:
                        pass
        except Exception as e1:
            self.LogErrorLine("Error Closing Mail: " + str(e1))

    # ---------- MyMail.EmailCommandThread --------------------------------------
    def EmailCommandThread(self):

        while True:
            # start email command thread
            try:
                self.Mailbox = imaplib.IMAP4_SSL(self.IMAPServer)
                if self.debug:
                    self.Mailbox.Debug = 4
            except Exception:
                self.LogError("No Internet Connection! ")
                if self.WaitForExit("EmailCommandThread", 120):
                    return  # exit thread
                continue
            try:
                if not self.DisableSmtpAuth:
                    data = self.Mailbox.login(self.EmailAccount, self.EmailPassword)
            except Exception as e1:
                self.LogError("LOGIN FAILED!!! " + str(e1))
                if self.WaitForExit("EmailCommandThread", 60):
                    return  # exit thread
                continue
            while True:
                try:
                    rv, data = self.Mailbox.select(self.IncomingFolder)
                    if rv != "OK":
                        self.LogError("Error selecting mail folder! (select)")
                        if self.WaitForExit("EmailCommandThread", 15):
                            return
                        continue
                    rv, data = self.Mailbox.search(None, "ALL")
                    if rv != "OK":
                        self.LogError("No messages found! (search)")
                        if self.WaitForExit("EmailCommandThread", 15):
                            return
                        continue
                    for num in data[0].split():
                        rv, data = self.Mailbox.fetch(num, "(RFC822)")
                        if rv != "OK":
                            self.LogError("ERROR getting message (fetch): " + str(num))
                            if self.WaitForExit("EmailCommandThread", 15):
                                return
                            continue
                        if sys.version_info[0] < 3:  # PYTHON 2
                            msg = email.message_from_string(data[0][1])
                        else:  # PYTHON 3
                            msg = email.message_from_bytes(data[0][1])
                        decode_val = email.header.decode_header(msg["Subject"])[0]
                        if sys.version_info[0] < 3:  # PYTHON 2
                            subject = unicode(decode_val[0])
                            subject = subject.decode("utf-8")
                        else:  # PYTHON 3
                            subject = decode_val[0]
                        self.IncomingCallback(subject)

                        # move the message to processed folder
                        self.Mailbox.copy(num, self.ProcessedFolder)
                        self.Mailbox.store(
                            num, "+FLAGS", "\\Deleted"
                        )  # this is needed to remove the original label
                        self.Mailbox.expunge()
                    if self.WaitForExit("EmailCommandThread", 15):
                        return
                except Exception as e1:
                    self.LogErrorLine("Resetting email thread : " + str(e1))
                    if self.WaitForExit("EmailCommandThread", 60):  # 60 sec
                        return
                    break

            if self.WaitForExit("EmailCommandThread", 15):  # 15 sec
                return

            ## end of outer loop

    # ------------ MyMail.GetRecipientByType ------------------------------------
    def GetRecipientByType(self, msgtype, recipient):
        try:
            if recipient == None:
                recipient = self.EmailRecipientByType[msgtype]
                if "@" in recipient:
                    return recipient
                else:
                    return None
            else:
                return recipient
        except Exception as e1:
            self.LogErrorLine("Error in GetRecipientByType : " + str(e1))
            return None

    # ------------ MyMail.sendEmailDirectMIME -----------------------------------
    # send email, bypass queue
    def sendEmailDirectMIME(
        self, msgtype, subjectstr, msgstr, recipient=None, files=None, deletefile=False
    ):

        try:
            recipient = self.GetRecipientByType(msgtype, recipient)
            if recipient == None:
                # returning true here means that there is not category for this message
                self.LogDebug("Message abandoned, no recipient")
                return True

            # update date
            dtstamp = datetime.datetime.now().strftime("%a %d-%b-%Y")
            # update time
            tmstamp = datetime.datetime.now().strftime("%I:%M:%S %p")
            try:
                import email.policy
                parent = MIMEMultipart('mixed',policy=email.policy.SMTP)
            except:
                parent = MIMEMultipart('mixed')

            if self.UseHTML:
                subtype = 'alternative'
            else:
                subtype = 'mixed'
            if sys.version_info[0] < 3:  # PYTHON 2
                msg = MIMEMultipart(subtype)
            else:
                try:
                    import email.policy
                    msg = MIMEMultipart(subtype, policy=email.policy.SMTP)
                except:
                    msg = MIMEMultipart(subtype)
            if self.SenderName == None or not len(self.SenderName):
                parent["From"] = "<" + self.SenderAccount + ">"
            else:
                parent["From"] = self.SenderName + " <" + self.SenderAccount + ">"
                self.LogDebug(parent["From"])

            parent.attach(msg)
        except Exception as e1:
            self.LogErrorLine("Error in email init: " + str(e1))
            return False

        try:
            recipientList = recipient.strip().split(",")
            recipientList = map(lambda x: x.strip(), recipientList)
            recipienttemp = ">,<"
            recipienttemp = recipienttemp.join(recipientList)
            recipient = "<" + recipienttemp + ">"
        except Exception as e1:
            self.LogErrorLine("Error parsing recipient format: " + str(e1))

        try:
            if self.UseBCC:
                parent["Bcc"] = recipient
            else:
                parent["To"] = recipient

            parent["Date"] = formatdate(localtime=True)
            parent["Subject"] = subjectstr

            body = ("\r\n" + "Time: " + tmstamp + "\r\n" + 
                    "Date: " + dtstamp + "\r\n"
                    + msgstr
            )
            if self.UseHTML:
                html_message = MyMail.ConvertTextToHTML(body)

            if sys.version_info[0] < 3:  # PYTHON 2
                msg.attach(MIMEText(body, "plain"))
                if self.UseHTML:
                    msg.attach(MIMEText(html_message, "html"))
            else:  # PYTHON 3
                try:
                    msg.attach(
                        MIMEText(
                            body, "plain", _charset="utf-8", policy=email.policy.SMTP
                        )
                    )
                    if self.UseHTML:
                        msg.attach(
                            MIMEText(
                                html_message, "html", _charset="utf-8", policy=email.policy.SMTP
                            )
                        )
                except:
                    msg.attach(MIMEText(body, "plain"))
        except Exception as e1:
            self.LogErrorLine("Error in email init 2: " + str(e1))
            return False

        # if the files are not found then we skip them but still send the email
        try:
            from email import encoders
            from email.mime.base import MIMEBase
            for f in files or []:

                with open(f, "rb") as fil:
                    part = MIMEApplication(fil.read(), Name=basename(f))
                    part.add_header('Content-Disposition',
                            'attachment',
                            filename=basename(f))
                    parent.attach(part)
                    self.LogDebug("attachment: "  + basename(f))

                if deletefile:
                    os.remove(f)

        except Exception as e1:
            self.LogErrorLine("Error attaching file in sendEmailDirectMIME: " + str(e1))

        # self.LogError("Logging in: SMTP Server <"+self.SMTPServer+">:Port <"+str(self.SMTPPort) + ">")

        try:
            if self.SSLEnabled:
                session = smtplib.SMTP_SSL(self.SMTPServer, self.SMTPPort)
                session.ehlo()
            else:
                session = smtplib.SMTP(self.SMTPServer, self.SMTPPort)
                if not self.TLSDisable:
                    session.starttls()
                session.ehlo
            try:
                if self.debug:
                    pass
                    # session.set_debuglevel(1)     # for some reason login fails when this enabled
            except Exception as e1:
                self.LogErrorLine("Error setting debug level: " + str(e1))
                # this allows support for simple TLS
        except Exception as e1:
            self.LogErrorLine(
                "Error SMTP Init : SSL:<" + str(self.SSLEnabled) + ">: " + str(e1)
            )
            return False

        try:
            if self.EmailPassword != "" and not self.DisableSmtpAuth:
                session.login(
                    MyMail.FilterAddress(self.EmailAccount), str(self.EmailPassword)
                )

            if sys.version_info[0] < 3:  # PYTHON 2
                message = parent.as_string()
            else:  # PYTHON 3
                message = parent.as_bytes()

            if "," in recipient:
                multiple_recipients = recipient.split(",")
                session.sendmail(
                    MyMail.FilterAddress(self.SenderAccount),
                    multiple_recipients,
                    message,
                )
            else:
                session.sendmail(
                    MyMail.FilterAddress(self.SenderAccount), recipient, message
                )
        except Exception as e1:
            self.LogErrorLine("Error SMTP sendmail: " + str(e1))
            try:
                session.quit()
            except:
                pass
            return False

        session.quit()

        return True

    # end sendEmailDirectMIME()

    # ------------MyMail::SendMailThread-----------------------------------------
    def SendMailThread(self):

        # once sendMail is called email messages are queued and then sent from this thread
        time.sleep(0.1)
        while True:

            while self.EmailSendQueue != []:
                MailError = False
                EmailItems = self.EmailSendQueue.pop()
                try:
                    if not (
                        self.sendEmailDirectMIME(
                            EmailItems[0],
                            EmailItems[1],
                            EmailItems[2],
                            EmailItems[3],
                            EmailItems[4],
                            EmailItems[5],
                        )
                    ):
                        self.LogError(
                            "Error in SendMailThread, sendEmailDirectMIME failed, retrying"
                        )
                        MailError = True
                except Exception as e1:
                    # put the time back at the end of the queue
                    self.LogErrorLine(
                        "Error in SendMailThread, retrying (2): " + str(e1)
                    )
                    MailError = True

                if MailError:
                    # NOTE: emails are retried if they fail. This allows emails to eventually
                    # be sent if there is an internet outage however the downside is that
                    # if the recipient is bad then it will keep trying and the mail queue will
                    # be stuck

                    self.EmailSendQueue.insert(len(self.EmailSendQueue), EmailItems)
                    # sleep for 2 min and try again
                    if self.WaitForExit("SendMailThread", 120 + self.ExtendWait):
                        return

            if self.WaitForExit("SendMailThread", 2):
                return

    # ------------MyMail::sendEmail----------------------------------------------
    # msg type must be one of "outage", "error", "warn", "info"
    def sendEmail(
        self,
        subjectstr,
        msgstr,
        recipient=None,
        files=None,
        deletefile=False,
        msgtype="error",
    ):

        if not self.DisableEmail:  # if all email disabled, do not queue
            if (
                self.SMTPServer != "" and not self.DisableSMTP
            ):  # if only sending is disabled, do not queue
                self.EmailSendQueue.insert(
                    0, [msgtype, subjectstr, msgstr, recipient, files, deletefile]
                )
