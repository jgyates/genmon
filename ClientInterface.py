#!/usr/bin/env python
"""
Provides a command-line interface (CLI) for interacting with the genmon.py server.

This script allows users to connect to a running genmon.py server instance,
send commands to it (e.g., to query generator status, settings, or logs),
and view the responses received from the server. It utilizes the `ClientInterface`
class from the `genmonlib.myclient` module to handle the underlying socket
communication and command processing logic.

Usage:
    python ClientInterface.py [options]

Options:
    -h, --help          Show help message.
    -a, --address <ip>  IP address of the genmon.py server (defaults to localhost).
    -p, --port <port>   Port number of the genmon.py server (defaults to server default).

Example:
    python ClientInterface.py -a 192.168.1.100 -p 8888
    > status
    [Server response for 'status' command]
    > exit
"""
# -------------------------------------------------------------------------------
#    FILE: ClientInterface.py
# PURPOSE:
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Dec-2016
# MODIFICATIONS:
# -------------------------------------------------------------------------------
import getopt
import signal
import sys

try:
    # Attempt to import necessary modules from the genmonlib library.
    from genmonlib.myclient import ClientInterface
    from genmonlib.mylog import SetupLogger
    from genmonlib.program_defaults import ProgramDefaults
except Exception as e1:
    # Provide a helpful message if imports fail, often due to incorrect setup.
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print(f"Error: {str(e1)}")
    sys.exit(2)

# Global variable to hold the client interface instance, accessible by signal_handler.
MyClientInterface = None

# ----------  Signal Handler ----------------------------------------------------
def signal_handler(sig, frame):
    """
    Handles termination signals (SIGINT, SIGTERM) for graceful shutdown.

    This function is registered as a handler for interrupt signals. When such a
    signal is received (e.g., Ctrl+C), it attempts to close the network
    connection maintained by `MyClientInterface` before exiting the script.

    Args:
        sig (int): The signal number that was caught.
        frame (frame): The current stack frame when the signal was received.
    """
    print("\nSignal received, shutting down client...")
    if MyClientInterface is not None:
        MyClientInterface.Close() # Attempt to close the client connection.
    sys.exit(0) # Exit gracefully.


# ------------------- Command-line interface for monitor ------------------------
if __name__ == "__main__":  # Script entry point.
    # Default server address and port, can be overridden by command-line arguments.
    address = ProgramDefaults.LocalHost
    port = ProgramDefaults.ServerPort

    # Setup a logger for console output (e.g., help messages, errors during startup).
    # This logger streams directly to the console without writing to a file.
    console = SetupLogger("client_console", log_file="", stream=True)

    HelpStr = "\npython ClientInterface.py -a <IP Address or none for localhost> -p <port or none for default port>\n"

    # Parse command-line arguments using getopt.
    try:
        # 'hp:a:' defines short options: -h (help), -p (port, requires arg), -a (address, requires arg).
        # ["help", "port=", "address="] defines corresponding long options.
        opts, args = getopt.getopt(sys.argv[1:], "hp:a:", ["help", "port=", "address="])
    except getopt.GetoptError as err:
        # If getopt encounters an invalid argument or option.
        console.error(f"Invalid command line argument: {err}")
        console.error(HelpStr)
        sys.exit(2)

    # Process the parsed options and arguments.
    try:
        for opt, arg in opts:
            if opt == "-h" or opt == "--help":
                # Display help string and exit if -h or --help is used.
                console.info(HelpStr) # Use info for help text
                sys.exit()
            elif opt in ("-a", "--address"):
                # Set server address if -a or --address is provided.
                address = arg
            elif opt in ("-p", "--port"):
                # Set server port if -p or --port is provided, converting to integer.
                port = int(arg)
    except ValueError:
        console.error(f"Error: Port number must be an integer. Received: '{arg}'")
        sys.exit(2)
    except Exception as e1:
        # Catch any other errors during option processing.
        console.error(f"Error parsing command-line options: {str(e1)}")
        sys.exit(2)

    # Setup a logger for general client operations, writing to "client.log".
    # This logger can be passed to the ClientInterface for its internal logging.
    log = SetupLogger("client", "client.log")

    # Register signal handlers for SIGINT (Ctrl+C) and SIGTERM.
    # This allows for graceful shutdown (e.g., closing the socket) upon interruption.
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Instantiate the ClientInterface with the determined address, port, and logger.
    # The global MyClientInterface variable is assigned here.
    try:
        MyClientInterface = ClientInterface(host=address, port=port, log=log)
    except Exception as e: # Catch potential errors during ClientInterface instantiation (e.g. initial connection failure)
        console.error(f"Failed to initialize client connection: {e}")
        if log: # Log to file if logger is available
            log.error(f"Failed to initialize client connection: {e}", exc_info=True)
        sys.exit(1)


    # Main command loop: continuously prompt user for commands until "exit".
    try:
        console.info(f"Connected to genmon server at {address}:{port}. Type 'exit' to quit.")
        while True:
            # Prompt user for input.
            # Use raw_input() for Python 2.x, input() for Python 3.x.
            if sys.version_info[0] < 3:
                line = raw_input("> ")
            else:
                line = input("> ")

            # Check if the user wants to exit.
            if line.strip().lower() == "exit":
                break # Exit the command loop.

            # If the input line is not empty, process it as a command.
            if len(line.strip()):
                # Send the command to the server via ClientInterface and get the response.
                data = MyClientInterface.ProcessMonitorCommand(line)
                # Print the server's response to the console.
                print(data)

    except EOFError:
        # Handle EOF (e.g., if input is redirected and finishes, or Ctrl+D).
        print("\nEOF received, exiting.")
    except KeyboardInterrupt:
        # This is redundant if SIGINT handler works as expected, but good for robustness.
        print("\nKeyboard interrupt received, exiting.")
    except Exception as e1:
        # Catch any other runtime errors during the command loop.
        console.error(f"Runtime error: {str(e1)}")
        if log: # Log detailed error to file
            log.error(f"Runtime error in command loop: {str(e1)}", exc_info=True)
    finally:
        # Ensure the client connection is closed when the loop exits (normally or via error).
        if MyClientInterface is not None:
            console.info("Closing connection...")
            MyClientInterface.Close()
        console.info("Client shut down.")
