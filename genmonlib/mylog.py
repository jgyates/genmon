#-------------------------------------------------------------------------------
# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
#-------------------------------------------------------------------------------
import logging, logging.handlers

#---------- SetupLogger --------------------------------------------------------
def SetupLogger(logger_name, log_file, level=logging.INFO, stream = False):


    logger = logging.getLogger(logger_name)

    # remove existing logg handlers
    for handler in logger.handlers[:]:      # make a copy of the list
        logger.removeHandler(handler)

    logger.setLevel(level)

    formatter = logging.Formatter('%(asctime)s : %(message)s')

    if log_file != "":

        rotate = logging.handlers.RotatingFileHandler(log_file, mode='a',maxBytes=50000,backupCount=5)
        rotate.setFormatter(formatter)
        logger.addHandler(rotate)

    if stream:      # print to screen also?
        streamHandler = logging.StreamHandler()
        # Dont format stream log messages
        logger.addHandler(streamHandler)


    return logging.getLogger(logger_name)
