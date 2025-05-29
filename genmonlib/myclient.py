#!/usr/bin/env python
"""
This module defines the `ClientInterface` class, which provides a client-side
implementation for socket-based communication with the `genmon.py` server.
It handles connection management, command sending, response receiving, and
ensures thread-safe operations for client applications interacting with the
generator monitoring server.
"""
# -------------------------------------------------------------------------------
#    FILE: myclient.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 5-Apr-2017
# MODIFICATIONS:
# -------------------------------------------------------------------------------
import os
import socket
import sys
import threading
import time

from genmonlib.mycommon import MyCommon
from genmonlib.mylog import SetupLogger
from genmonlib.program_defaults import ProgramDefaults


class ClientInterface(MyCommon):
    """
    Manages a socket-based connection to the genmon.py server.

    This class is responsible for establishing and maintaining a connection
    to the server, sending commands, and receiving responses. It incorporates
    retry logic for connections and thread safety for command processing using
    an RLock.

    Attributes:
        host (str): The hostname or IP address of the server.
        port (int): The port number the server is listening on.
        Socket (socket.socket): The client socket object used for communication.
        AccessLock (threading.RLock): An RLock to ensure that command sending
            and response receiving sequences are atomic and thread-safe. This
            prevents multiple threads from interleaving their communications with
            the server, ensuring each command correctly pairs with its response.
        EndOfMessage (str): A specific string marker ("EndOfMessage") used to
            determine the end of a complete message from the server, as messages
            might be received in multiple chunks.
        rxdatasize (int): The maximum number of bytes to receive in a single
            socket `recv` operation. Currently set to 2098152.
        max_retries (int): The maximum number of times to attempt to connect to
            the server before giving up.
        log (logging.Logger): Logger instance for this class.
        console (logging.Logger): Logger instance for console output.
    """
    def __init__(
        self,
        host=ProgramDefaults.LocalHost,
        port=ProgramDefaults.ServerPort,
        log=None,
        loglocation=ProgramDefaults.LogPath,
    ):
        """
        Initializes the ClientInterface instance.

        Sets up logging, initializes connection parameters, and attempts to
        establish an initial connection to the server by calling `self.Connect()`.

        Args:
            host (str, optional): The hostname or IP address of the server.
                                  Defaults to `ProgramDefaults.LocalHost`.
            port (int, optional): The port number for the server connection.
                                  Defaults to `ProgramDefaults.ServerPort`.
            log (logging.Logger, optional): An external logger instance. If None,
                                            a new logger named "client" will be
                                            created, logging to "myclient.log"
                                            in `loglocation`.
            loglocation (str, optional): The directory path for log files if
                                         a new logger is created.
                                         Defaults to `ProgramDefaults.LogPath`.
        """
        super(ClientInterface, self).__init__()
        if log is not None:
            self.log = log
        else:
            # Setup a dedicated logger for client operations if one isn't provided.
            self.log = SetupLogger("client", os.path.join(loglocation, "myclient.log"))

        # Setup a logger for console output, typically for startup messages or critical errors.
        self.console = SetupLogger("client_console", log_file="", stream=True)

        # RLock is used to allow the same thread to acquire the lock multiple times,
        # which is useful here as Receive can be called by Connect (already under lock in ProcessMonitorCommand).
        self.AccessLock = threading.RLock()
        self.EndOfMessage = "EndOfMessage"  # Marker for end of server messages
        self.rxdatasize = 2098152  # Max bytes for socket.recv()
        self.host = host
        self.port = port
        self.max_retries = 10 # Max connection attempts
        self.Socket = None # Initialize socket attribute

        # Attempt to connect immediately upon instantiation.
        self.Connect()

    # ----------  ClientInterface::Connect --------------------------------------
    def Connect(self):
        """
        Establishes a connection to the server.

        This method attempts to create a socket and connect to the configured
        `host` and `port`. It includes a retry mechanism, attempting up to
        `self.max_retries` times with a 1-second delay between attempts.
        If connection fails after all retries, it logs an error and exits.
        Upon successful connection, it attempts to receive an initial startup
        message from the server.
        """
        retries = 0
        while True:
            try:
                # Create an INET (IPv4), STREAMing (TCP) socket.
                self.Socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.Socket.settimeout(10) # Set a timeout for socket operations (e.g., 10 seconds)

                # Attempt to connect to the server.
                self.Socket.connect((self.host, self.port))

                # After connecting, server might send an initial status message (e.g. "OK").
                # This call to Receive expects that initial message, which might not
                # have the standard EndOfMessage marker.
                startup_message_status, startup_message_content = self.Receive(
                    expect_no_end_of_message_marker=True
                )
                self.console.info(f"Server startup message: {startup_message_content}") # Log the startup message.
                return # Connection successful.
            except Exception as e1:
                retries += 1
                # If max retries reached, log error and exit.
                if retries >= self.max_retries:
                    self.LogErrorLine(f"Error: Connect to {self.host}:{self.port} failed after {self.max_retries} retries: {str(e1)}")
                    self.console.error("Genmon server not responding or not loaded.")
                    # Depending on application design, exiting here might be too drastic.
                    # Consider raising an exception instead.
                    sys.exit(1)
                else:
                    # Wait for 1 second before retrying.
                    self.LogErrorLine(f"Connection attempt {retries}/{self.max_retries} failed: {str(e1)}. Retrying in 1s...")
                    time.sleep(1)
                    continue # Retry connection

    # ----------  ClientInterface::SendCommand ----------------------------------
    def SendCommand(self, cmd):
        """
        Sends a command string to the connected server.

        The command string is encoded as UTF-8 before sending. If the send
        operation fails (e.g., due to a broken connection), it logs the error,
        closes the current socket, and attempts to reconnect.

        Args:
            cmd (str): The command string to send to the server.
        """
        try:
            if self.Socket:
                self.Socket.sendall(cmd.encode("utf-8"))
            else:
                self.LogErrorLine("Error: SendCommand called but socket is not connected.")
                self.Connect() # Attempt to reconnect
                if self.Socket: # If reconnection was successful, try sending again
                    self.Socket.sendall(cmd.encode("utf-8"))
                else:
                    self.LogErrorLine("Error: Failed to send command after attempting reconnect.")
                    return # Or raise an exception
        except Exception as e1:
            self.LogErrorLine(f"Error: TX (sending command '{cmd}'): {str(e1)}")
            # If send fails, assume connection is broken. Close and try to reconnect.
            self.Close()
            self.Connect()
            # Optionally, try sending the command again after reconnecting.
            # However, this could lead to complex state if the original command
            # was partially sent or if the server state changed. For now, just reconnect.

    # ----------  ClientInterface::Receive --------------------------------------
    def Receive(self, expect_no_end_of_message_marker=False):
        """
        Receives data from the server until an EndOfMessage marker is found
        or specific conditions are met.

        This method handles receiving data in chunks and concatenates them
        until the `self.EndOfMessage` string is detected in the stream,
        unless `expect_no_end_of_message_marker` is True.
        It also checks for special startup messages that might not conform to
        the standard message ending protocol.

        Args:
            expect_no_end_of_message_marker (bool, optional):
                If True, the method assumes the received message might not end
                with the `EndOfMessage` marker. This is typically used for
                the initial server handshake/startup message. Defaults to False.

        Returns:
            tuple (bool, str):
                - `receive_successful` (bool): True if a complete message (ending with
                  `EndOfMessage` or if `expect_no_end_of_message_marker` is True and data is received)
                  was successfully received. False if an error occurred, the connection
                  was lost, or a startup message interrupted a multi-part message.
                - `data_str` (str): The received data string. If `receive_successful` is False
                  due to an error, this might be "Retry" or an empty string.
        """
        # This lock ensures that receive operations for a single command's response
        # are not interleaved with other command/response cycles from other threads.
        with self.AccessLock:
            receive_successful = True
            data_str = ""
            try:
                if not self.Socket:
                    self.LogErrorLine("Error: Receive called but socket is not connected.")
                    self.Connect() # Attempt to reconnect
                    if not self.Socket:
                        return False, "Retry_NoSocket" # Indicate failure to get socket

                # Initial receive attempt
                raw_bytes_received = self.Socket.recv(self.rxdatasize)
                data_str = raw_bytes_received.decode("utf-8")

                if len(data_str):
                    # If we are expecting a message without the EOM marker (e.g., initial handshake)
                    # or if it's a startup message, we might consider it complete as is.
                    is_startup_msg = self.CheckForStarupMessage(data_str)
                    if is_startup_msg or expect_no_end_of_message_marker:
                        # If it's a startup message or noeom is true, we assume the first chunk is the whole message.
                        receive_successful = True
                    else:
                        # Accumulate data until EndOfMessage marker is found
                        while self.EndOfMessage not in data_str:
                            additional_raw_bytes = self.Socket.recv(self.rxdatasize)
                            additional_data_str = additional_raw_bytes.decode("utf-8")

                            if len(additional_data_str):
                                # Critical: If a startup message is received while expecting more parts
                                # of a regular message, it implies an issue or a server reset.
                                if self.CheckForStarupMessage(additional_data_str):
                                    self.LogErrorLine("Warning: Startup message received unexpectedly during multi-part message.")
                                    data_str = additional_data_str # Prioritize the new startup message
                                    receive_successful = True # Treat as a new, complete (startup) message
                                    break # Exit accumulation loop
                                data_str += additional_data_str
                            else:
                                # Socket closed by peer or other issue if recv returns empty with no error
                                self.LogErrorLine("Error: RX: Received empty data, connection likely closed by peer.")
                                self.Close()
                                self.Connect() # Attempt to re-establish
                                return False, "Retry_EmptyData" # Indicate retry

                        # If loop exited because EndOfMessage was found
                        if self.EndOfMessage in data_str:
                            data_str = data_str[:-len(self.EndOfMessage)] # Remove the marker
                            receive_successful = True
                        # If loop exited for other reasons (e.g. startup message interruption),
                        # receive_successful is already set accordingly.

                else: # Initial recv returned empty string
                    self.LogErrorLine("Error: RX: Initial receive returned empty data. Connection may be lost.")
                    self.Close() # Close the problematic socket
                    self.Connect() # Attempt to re-establish
                    return False, "Retry_InitialEmpty" # Indicate retry is needed

            except socket.timeout:
                self.LogErrorLine("Error: RX: Socket timeout during receive.")
                # Depending on policy, may try to reconnect or signal failure
                receive_successful = False
                data_str = "Retry_Timeout"
            except Exception as e1:
                self.LogErrorLine(f"Error: RX: General exception: {str(e1)}")
                self.Close() # Assume connection is compromised
                self.Connect() # Attempt to re-establish
                receive_successful = False
                data_str = "Retry_Exception" # General retry signal

            return receive_successful, data_str

    # ----------  ClientInterface::CheckForStarupMessage ------------------------
    def CheckForStarupMessage(self, data_string):
        """
        Checks if the provided data string matches known server startup messages.

        Startup messages (e.g., "OK", "CRITICAL:", "WARNING:") might be sent by
        the server immediately upon connection or during certain state changes,
        and they might not adhere to the standard `EndOfMessage` marker protocol.

        Args:
            data_string (str): The data string to check.

        Returns:
            bool: True if the `data_string` starts with one of the predefined
                  startup message prefixes, False otherwise.
        """
        # Check for initial status responses from the server.
        # These messages might not end with the standard EndOfMessage marker.
        if (
            data_string.startswith("OK")
            or data_string.startswith("CRITICAL:")
            or data_string.startswith("WARNING:")
        ):
            return True
        else:
            return False

    # ----------  ClientInterface::Close ----------------------------------------
    def Close(self):
        """
        Closes the client socket connection.
        """
        if self.Socket:
            try:
                self.Socket.close()
            except Exception as e:
                self.LogErrorLine(f"Error closing socket: {e}")
            finally:
                self.Socket = None # Ensure socket is marked as closed

    # ----------  ClientInterface::ProcessMonitorCommand ------------------------
    def ProcessMonitorCommand(self, cmd):
        """
        Sends a command to the server and waits for a complete response.

        This is the primary method clients should use to interact with the server.
        It handles sending the command and receiving the response, ensuring the
        entire operation is thread-safe using `self.AccessLock`. If the initial
        receive attempt indicates the message was incomplete or an error occurred
        (e.g., connection dropped), it will retry sending the command and receiving
        the response until a successful status is reported by `Receive()`.

        Args:
            cmd (str): The command string to send to the server.

        Returns:
            str: The server's response data as a string. Returns an empty string
                 if a persistent error occurs despite retries.
        """
        response_data = ""
        try:
            # The AccessLock ensures that the sequence of sending a command and
            # receiving its specific response is atomic. This prevents issues
            # in multi-threaded client applications where one thread might send
            # a command and another thread's Receive call might incorrectly consume
            # that command's response.
            with self.AccessLock:
                command_successfully_processed = False
                retry_count = 0
                max_processing_retries = 3 # Max attempts for this command processing loop

                # Loop to ensure command is sent and a valid response is received.
                # This retries if Receive() indicates a problem (e.g. by returning False).
                while not command_successfully_processed and retry_count < max_processing_retries:
                    self.SendCommand(cmd) # Send (or resend) the command
                    command_successfully_processed, response_data = self.Receive()
                    if not command_successfully_processed:
                        self.LogDebug(f"Retrying command '{cmd}' due to receive issue. Attempt {retry_count + 1}/{max_processing_retries}")
                        retry_count += 1
                        time.sleep(0.5) # Short delay before retrying command processing
                
                if not command_successfully_processed:
                    self.LogErrorLine(f"Failed to process command '{cmd}' after {max_processing_retries} retries. Last response: {response_data}")
                    # Return empty or raise an exception if preferred
                    return f"Error: Failed to get response for command '{cmd}'"

        except Exception as e1:
            self.LogErrorLine(f"Error in ProcessMonitorCommand (command: '{cmd}'): {str(e1)}")
            # Consider re-raising or returning an error indicator
            response_data = f"Error: Exception during command '{cmd}' processing"
        return response_data
