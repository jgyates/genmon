"""
This module provides a standardized function (`SetupLogger`) for configuring
loggers used throughout the genmon application. It simplifies the process of
creating and setting up loggers with consistent formatting, file rotation,
and optional stream (console) output.
"""
# -------------------------------------------------------------------------------
# PURPOSE: setup logging
#
#  AUTHOR: Jason G Yates
#    DATE: 03-Dec-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------
import logging
import logging.handlers


# ---------- SetupLogger --------------------------------------------------------
def SetupLogger(logger_name, log_file, level=logging.INFO, stream=False):
    """
    Creates or retrieves and configures a logger instance.

    This function sets up a logger with specified handlers for file logging
    (with rotation) and optional stream (console) logging. It ensures that
    any pre-existing handlers on the logger are removed before new ones
    are attached, preventing duplicate log entries or configurations.

    Args:
        logger_name (str): The name of the logger. This is typically a
                           module-specific name like '__name__'.
        log_file (str): The path to the log file. If an empty string "" is
                        provided, file logging will be disabled.
        level (int, optional): The logging level for the logger
                               (e.g., logging.INFO, logging.DEBUG).
                               Defaults to logging.INFO.
        stream (bool, optional): If True, messages will also be logged to the
                                 console (sys.stderr by default).
                                 Defaults to False.

    Returns:
        logging.Logger: A configured logger instance.

    Key Behaviors:
        - Handler Removal: Iterates over a copy of the logger's handlers
          (logger.handlers[:]) and removes each one. This is crucial to
          prevent adding duplicate handlers if the logger instance already
          exists and has been configured before.
        - File Logging: If `log_file` is not an empty string, a
          `logging.handlers.RotatingFileHandler` is configured. This handler
          rotates log files when they reach `maxBytes` (50000 bytes by default)
          and keeps a specified number of `backupCount` (5 by default).
          Log messages to the file are formatted as "%(asctime)s : %(message)s".
        - Stream Logging: If `stream` is True, a `logging.StreamHandler` is
          added to output log messages to the console. These messages are
          formatted simply as "%(message)s".
    """
    logger = logging.getLogger(logger_name)

    # Remove any existing handlers from the logger.
    # This is important to prevent duplicate logging if this function is called
    # multiple times for the same logger instance (e.g., during a re-configuration).
    # Iterating over a slice (logger.handlers[:]) creates a copy of the list,
    # allowing safe removal of handlers from the original list during iteration.
    for handler in logger.handlers[:]:  # make a copy of the list
        logger.removeHandler(handler)

    logger.setLevel(level) # Set the logger's threshold level.

    # Configure file logging if a log file path is provided.
    if log_file != "":
        # Define the format for messages logged to the file.
        formatter = logging.Formatter("%(asctime)s : %(message)s")
        # Configure the rotating file handler.
        # mode="a": Append to the log file.
        # maxBytes=50000: Rotate the log when it reaches 50KB.
        # backupCount=5: Keep the last 5 rotated log files.
        rotate_handler = logging.handlers.RotatingFileHandler(
            log_file, mode="a", maxBytes=50000, backupCount=5
        )
        rotate_handler.setFormatter(formatter)
        logger.addHandler(rotate_handler)

    # Configure stream (console) logging if enabled.
    if stream:  # print to screen also?
        # Define a simpler format for console messages.
        stream_log_format = "%(message)s"
        stream_handler = logging.StreamHandler()
        stream_formatter = logging.Formatter(stream_log_format)
        stream_handler.setFormatter(stream_formatter)
        # Add the stream handler to the logger.
        logger.addHandler(stream_handler)

    # Return the same logger instance obtained by getLogger.
    # This is standard practice as getLogger retrieves the same logger object
    # if called with the same name.
    return logging.getLogger(logger_name)
