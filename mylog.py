# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
#------------------------------------------------------------
#
# This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

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
