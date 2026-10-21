#!/usr/bin/env python3
# ------------------------------------------------------------
#    FILE: test_web_stall.py
# PURPOSE: Checks whether one stalled client can stop genserv from answering anyone else.
#
#          genserv's HTTPS server did the TLS handshake of each new connection in the thread that
#          accepts connections, with no timeout. A client that connected and never finished the
#          handshake (a phone or tablet that dropped off the network mid-connect, a port scanner)
#          blocked every other request until that client went away, which could be never. The
#          HTTP -> HTTPS redirect server had the same problem, being single threaded with no timeout.
#
#          For each server this opens a connection that stalls (sending nothing, or half a TLS
#          ClientHello), makes a normal request while it is held open, then closes the stalled
#          connection and makes one more request.
#
#   USAGE: python3 test_web_stall.py [-a address] [-p https_port] [-r redirect_port] [-t seconds] [-w seconds]
#          Defaults: 127.0.0.1, 443, 8000 (skipped if nothing listens there), 5 second request timeout,
#          5 second pause between scenarios (time to reload the web UI in a browser and see the result).
#          Exit code 0 if nothing was blocked, 1 if a stalled client blocked a server.
#
# EXAMPLE: python3 test_web_stall.py -a genmon -p 443 -t 15
#
#          To see it in a browser: open the GenMon web interface, then start the test (from the Pi or
#          any computer that can reach it). While a scenario holds its stalled connection (up to the
#          -t timeout), the web interface shows its "not responding" message and refreshing the page
#          fails. The pause between scenarios lets the page load again, so each scenario can be seen
#          failing in turn. With the fix, the page keeps working throughout.
#
#  AUTHOR: skipfire
#    DATE: 21-Oct-2026
# ------------------------------------------------------------
import getopt
import socket
import ssl
import sys
import time

try:
    import http.client as httplib
except ImportError:  # Python 2
    import httplib

# The start of a TLS 1.x ClientHello record; the rest is never sent.
PARTIAL_CLIENT_HELLO = bytes(bytearray.fromhex("16030100c8010000c40303"))

USAGE = "usage: test_web_stall.py [-a address] [-p https_port] [-r redirect_port] [-t seconds] [-w seconds]"


def request(address, port, use_tls, timeout):
    """One normal GET /; any HTTP response counts as answered. Returns (answered, seconds, detail)."""
    start = time.time()
    try:
        if use_tls:
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            conn = httplib.HTTPSConnection(
                address, port, timeout=timeout, context=context
            )
        else:
            conn = httplib.HTTPConnection(address, port, timeout=timeout)
        conn.request("GET", "/")
        status = conn.getresponse().status
        conn.close()
        return True, time.time() - start, "HTTP %d" % status
    except Exception as e1:
        return False, time.time() - start, "%s: %s" % (type(e1).__name__, e1)


def listening(address, port):
    try:
        socket.create_connection((address, port), timeout=2).close()
        return True
    except Exception:
        return False


def scenario(address, port, use_tls, timeout, name, payload):
    """Returns True if the server kept answering while a client stalled."""
    print("\n%s on port %d: %s" % ("HTTPS" if use_tls else "HTTP", port, name))
    answered, seconds, detail = request(address, port, use_tls, timeout)
    print(
        "  before:            %-8s %5.2fs  %s"
        % ("answered" if answered else "FAILED", seconds, detail)
    )
    if not answered:
        print("  The server doesn't answer even without a stalled client; skipping.")
        return True

    stalled = socket.create_connection((address, port), timeout=timeout)
    if payload:
        stalled.sendall(payload)
    time.sleep(1)  # let the server pick up the stalled connection first
    answered, seconds, detail = request(address, port, use_tls, timeout)
    print(
        "  while stalled:     %-8s %5.2fs  %s"
        % ("answered" if answered else "BLOCKED", seconds, detail)
    )
    stalled.close()

    recovered, seconds, detail = request(address, port, use_tls, timeout)
    print(
        "  after it closed:   %-8s %5.2fs  %s"
        % ("answered" if recovered else "FAILED", seconds, detail)
    )
    return answered


def main(argv):
    address, https_port, redirect_port, timeout, pause = (
        "127.0.0.1",
        443,
        8000,
        5.0,
        5.0,
    )
    try:
        opts, _ = getopt.getopt(argv, "ha:p:r:t:w:")
    except getopt.GetoptError:
        print(USAGE)
        return 2
    for opt, arg in opts:
        if opt == "-h":
            print(USAGE)
            return 0
        if opt == "-a":
            address = arg
        elif opt == "-p":
            https_port = int(arg)
        elif opt == "-r":
            redirect_port = int(arg)
        elif opt == "-t":
            timeout = float(arg)
        elif opt == "-w":
            pause = float(arg)

    scenarios = [
        (https_port, True, "client connects and sends nothing", None),
        (https_port, True, "client sends half a TLS ClientHello", PARTIAL_CLIENT_HELLO),
    ]
    if redirect_port and listening(address, redirect_port):
        scenarios.append(
            (redirect_port, False, "client connects and sends nothing", None)
        )
    else:
        print(
            "\nNothing listening on port %d; redirect server not tested."
            % redirect_port
        )

    results = []
    for i, (port, use_tls, name, payload) in enumerate(scenarios):
        if i > 0 and pause > 0:
            print("\nPausing %g seconds before the next scenario..." % pause)
            time.sleep(pause)
        print("\nScenario %d of %d" % (i + 1, len(scenarios)))
        results.append(scenario(address, port, use_tls, timeout, name, payload))

    if all(results):
        print("\nPASS: no stalled client blocked the web server.")
        return 0
    print(
        "\nFAIL: a single stalled client stopped the web server from answering anyone else."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
