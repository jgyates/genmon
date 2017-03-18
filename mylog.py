# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
#------------------------------------------------------------
import logging, logging.handlers

#---------- SetupLogger -------------------------
def SetupLogger(logger_name, log_file, level=logging.INFO, stream = False):

    l = logging.getLogger(logger_name)
    l.setLevel(level)

    formatter = logging.Formatter('%(asctime)s : %(message)s')

    if log_file != "":

        rotate = logging.handlers.RotatingFileHandler(log_file, mode='a',maxBytes=4000,backupCount=5)
        rotate.setFormatter(formatter)
        l.addHandler(rotate)

    if stream:      # print to screen also?
        streamHandler = logging.StreamHandler()
        streamHandler.setFormatter(formatter)
        l.addHandler(streamHandler)


    return logging.getLogger(logger_name)