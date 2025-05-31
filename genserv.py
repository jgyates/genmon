#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: genserv.py
# PURPOSE: Flask app for generator monitor web app
#
#  AUTHOR: Jason G Yates
#    DATE: 20-Dec-2016
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

from __future__ import print_function

import collections
import datetime
import getopt
import json
import os
import os.path
import signal
import subprocess
import sys
import threading
import time

try:
    from flask import (
        Flask,
        jsonify,
        make_response,
        redirect,
        render_template,
        request,
        send_file,
        session,
        url_for,
    )
except Exception as e1:
    print(
        "\n\nThis program requires the Flask library. Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    import pyotp
except Exception as e1:
    print(
        "\n\nThis program requires the pyotp library. Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

try:
    from genmonlib.myclient import ClientInterface
    from genmonlib.myconfig import MyConfig
    from genmonlib.mylog import SetupLogger
    from genmonlib.mymail import MyMail
    from genmonlib.mysupport import MySupport
    from genmonlib.program_defaults import ProgramDefaults
    from genmonlib.presentation import UIPresenter

except Exception as e1:
    print(
        "\n\nThis program requires the modules located in the genmonlib directory in the original github repository.\n"
    )
    print(
        "Please see the project documentation at https://github.com/jgyates/genmon.\n"
    )
    print("Error: " + str(e1))
    sys.exit(2)

if sys.version_info[0] < 3:
    from urlparse import parse_qs, parse_qsl, urlparse
else:
    from urllib.parse import urlparse
    from urllib.parse import parse_qs
    from urllib.parse import parse_qsl

import datetime
import re

# -------------------------------------------------------------------------------
app = Flask(__name__, static_url_path="")

# this allows the flask support to be extended on a per site basis but sill allow for
# updates via the main github repository. If genservex.py exists, load it
if os.path.isfile(
    os.path.join(os.path.dirname(os.path.realpath(__file__)), "genservext.py")
):
    import genservext

app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 300

# --- Global configuration variables, loaded by LoadConfig() ---
HTTPAuthUser = None
HTTPAuthPass = None
HTTPAuthUser_RO = None
HTTPAuthPass_RO = None
LdapServer = None
LdapBase = None
DomainNetbios = None
LdapAdminGroup = None
LdapReadOnlyGroup = None

mail = None # MyMail instance
bUseMFA = False # Multi-Factor Authentication flag
SecretMFAKey = None # Secret key for MFA
MFA_URL = None # URL for MFA QR code provisioning
bUseSecureHTTP = False # HTTPS flag
bUseSelfSignedCert = True # Self-signed certificate flag for HTTPS
SSLContext = None # SSL context for HTTPS
HTTPPort = 8000 # Default HTTP port
loglocation = ProgramDefaults.LogPath # Path for log files
clientport = ProgramDefaults.ServerPort # Port for genmon client interface
log = None # Main logger instance for genserv
console = None # Console logger instance
AppPath = "" # Path of the application
favicon = "favicon.ico" # Default favicon
ConfigFilePath = ProgramDefaults.ConfPath # Path to configuration files

# --- Configuration File Constants ---
MAIL_SECTION = "MyMail"
GENMON_SECTION = "GenMon"

# --- Login Lockout Variables ---
WebUILocked = False # Flag indicating if web UI login is locked
LoginAttempts = 0 # Counter for failed login attempts
MaxLoginAttempts = 5 # Maximum allowed failed login attempts before lockout
LockOutDuration = 5 * 60 # Lockout duration in seconds (5 minutes)
LastLoginTime = datetime.datetime.now() # Timestamp of the last successful login
LastFailedLoginTime = datetime.datetime.now() # Timestamp of the last failed login attempt
securityMessageSent = None # Timestamp when a security lockout message was last sent

# --- Application State Variables ---
Closing = False # Flag indicating if the application is in the process of closing
Restarting = False # Flag indicating if the application is restarting
ControllerType = "generac_evo_nexus" # Default controller type
CriticalLock = threading.Lock() # Thread lock for critical sections
CachedToolTips = {} # Cache for tooltips (currently unused as CacheToolTips is commented out)
CachedRegisterDescriptions = {} # Cache for register descriptions
# -------------------------------------------------------------------------------
@app.route("/logout")
def logout():
    """
    Handles user logout.

    Clears session variables related to login status, write access, and MFA.
    Redirects the user to the root page (which will typically show the login page).
    """
    try:
        # remove the session data
        if LoginActive(): # Check if login functionality is even active
            session["logged_in"] = False # Mark user as logged out
            session["write_access"] = False # Revoke write access
            session["mfa_ok"] = False # Reset MFA status
            log.info("User logged out successfully.")
        return redirect(url_for("root")) # Redirect to the main page
    except Exception as e1:
        LogError("Error on logout: " + str(e1))
        return redirect(url_for("root")) # Redirect even on error


# -------------------------------------------------------------------------------
@app.after_request
def add_header(r):
    """
    Adds headers to every response to prevent caching.

    This ensures that the browser always fetches the latest version of pages
    and resources, which is important for a dynamic monitoring application.
    """
    r.headers[
        "Cache-Control"
    ] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"
    return r


# -------------------------------------------------------------------------------
# Global variable for UIPresenter instance
ui_presenter = None
# -------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():
    """
    Serves the main root page (usually index.html).

    If Multi-Factor Authentication (MFA) is enabled (`bUseMFA` is True)
    and the user's MFA status is not confirmed in the session, it resets
    the login state and effectively forces a re-login or MFA step.
    Otherwise, it calls `ServePage("index.html")` to render the main page.
    """
    # If MFA is enabled, check if the MFA step has been completed.
    if bUseMFA:
        if not "mfa_ok" in session or not session["mfa_ok"] == True:
            # If MFA not confirmed, reset login state to force re-authentication / MFA.
            session["logged_in"] = False
            session["write_access"] = False
            session["mfa_ok"] = False
            # Redirecting to root will typically lead to login or MFA page via ServePage logic.
            # No explicit redirect here, as ServePage will handle it.
    return ServePage("index.html") # Serve the main index page.


# -------------------------------------------------------------------------------
@app.route("/verbose", methods=["GET"])
def verbose():
    """
    Serves the verbose status page.

    This page typically displays a more detailed or raw view of the generator status.
    It calls `ui_presenter.get_verbose_page_data()` to get the necessary data
    and then renders the `index_verbose.html` template.
    """
    page_data = ui_presenter.get_verbose_page_data()
    return render_template("index_verbose.html", **page_data)


# -------------------------------------------------------------------------------
@app.route("/low", methods=["GET"])
def lowbandwidth():
    """
    Serves a low-bandwidth version of the status page.

    This page is designed for clients with slow internet connections, showing
    essential information with minimal data transfer.
    It calls `ui_presenter.get_lowbandwidth_page_data()` for data and renders
    the `index_lowbandwith.html` template. (Note: "lowbandwith" might be a typo for "lowbandwidth").
    """
    page_data = ui_presenter.get_lowbandwidth_page_data()
    return render_template("index_lowbandwith.html", **page_data)


# -------------------------------------------------------------------------------
@app.route("/internal", methods=["GET"])
def display_internal():
    """
    Serves a page displaying internal genmon or controller data.

    Requires login. It calls `ui_presenter.get_internal_page_data()` for data
    and renders the `internal.html` template. This page is often used for
    debugging or advanced diagnostics.
    """
    # Check login status. If not logged in, redirect to login page.
    if LoginActive() and not session.get("logged_in"):
        return render_template("login.html")
    # Get data for the internal page from the UI presenter.
    page_data = ui_presenter.get_internal_page_data()
    # Render the internal.html template with the retrieved data.
    return render_template("internal.html", **page_data)


# -------------------------------------------------------------------------------
@app.route("/locked", methods=["GET"])
def locked():
    """
    Serves the "account locked" page.

    This page is displayed when a user's account is temporarily locked due to
    too many failed login attempts. It typically shows a countdown or message
    indicating when the user can try logging in again.
    """
    # Log that the locked page is being accessed.
    LogError("Locked Page accessed by a user.")
    # Render the locked.html template.
    return render_template("locked.html")

# -------------------------------------------------------------------------------
@app.route("/upload", methods=["PUT"])
def upload():
    # TODO: Implement file upload functionality.
    # This route is a placeholder for a future file upload feature.
    # Currently, it just logs the access and redirects to the root page.
    LogError("genserv: Upload route accessed (Not Implemented).")
    return redirect(url_for("root"))

# -------------------------------------------------------------------------------
def ServePage(page_file):
    """
    Serves a requested page, handling login and page-specific data.

    This function is a central handler for serving HTML pages.
    -   **Login Check:** If login is active (`LoginActive()` returns True) but
        the user is not marked as logged in in the session, it renders the
        `login.html` page.
    -   **Index Page Handling:** If the requested `page_file` is "index.html",
        it calls `ui_presenter.get_index_page_data()` to get dynamic data
        for the main dashboard and then renders `index.html` as a template.
    -   **Other Static Files:** For any other `page_file`, it attempts to serve
        it as a static file from Flask's static folder using
        `app.send_static_file(page_file)`.

    Args:
        page_file (str): The filename of the page to serve (e.g., "index.html",
                         "about.html").

    Returns:
        Flask Response: The rendered HTML page or a static file.
    """
    # Check if login functionality is enabled globally.
    if LoginActive():
        # If login is enabled, check if the current user is logged in via session.
        if not session.get("logged_in"):
            # If not logged in, render the login page.
            return render_template("login.html")
        else:
            # If logged in:
            if page_file == "index.html":
                # For index.html, get dynamic data from the UI presenter.
                page_data = ui_presenter.get_index_page_data()
                # Render index.html as a template with the dynamic data.
                return render_template("index.html", **page_data)
            # For other pages requested by a logged-in user, serve them as static files.
            # This assumes other HTML pages are static or handled by different routes.
            return app.send_static_file(page_file)
    else: # If login functionality is NOT active globally (e.g., HTTPAuthUser not set).
        # For non-login case, if index.html is requested, get its data and render as template.
        if page_file == "index.html":
            page_data = ui_presenter.get_index_page_data()
            return render_template("index.html", **page_data)
        # For any other file, serve it as a static file.
        return app.send_static_file(page_file)


# -------------------------------------------------------------------------------
@app.route("/mfa", methods=["POST"])
def mfa_auth():
    """
    Handles Multi-Factor Authentication (MFA) based on One-Time Password (OTP).

    This route is typically accessed after a successful primary login if MFA is enabled.
    -   It validates the OTP code submitted by the user (`request.form["code"]`)
        using `ValidateOTP()`.
    -   If validation is successful, it sets `session["mfa_ok"] = True` and
        redirects to the root page (which should now grant full access).
    -   If validation fails, it resets all login-related session variables
        (`logged_in`, `write_access`, `mfa_ok`) and redirects to logout,
        effectively forcing a full re-login.
    -   If MFA is not enabled (`bUseMFA` is False), it simply redirects to root.
    """
    try:
        # Check if Multi-Factor Authentication is enabled globally.
        if bUseMFA:
            # Validate the One-Time Password (OTP) submitted in the form.
            if ValidateOTP(request.form["code"]):
                # If OTP is valid, mark MFA as completed in the session.
                session["mfa_ok"] = True
                log.info("MFA successful.")
                return redirect(url_for("root")) # Redirect to the main application page.
            else:
                # If OTP is invalid, reset all login and MFA session flags.
                log.warning("MFA validation failed.")
                session["logged_in"] = False
                session["write_access"] = False
                session["mfa_ok"] = False
                return redirect(url_for("logout")) # Redirect to logout to force re-authentication.
        else:
            # If MFA is not enabled, simply redirect to the root page.
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in mfa_auth: " + str(e1))
        # On error, render the login page as a fallback.
        return render_template("login.html")


# -------------------------------------------------------------------------------
def admin_login_helper():
    """
    Helper function called after a successful primary login (username/password or LDAP).

    -   If MFA is enabled (`bUseMFA`), it renders the `mfa.html` template to prompt
        the user for their One-Time Password (OTP). The `GetOTP()` function (which
        is commented out in the original but would typically send an OTP via email
        or generate one) might have been intended to be called here or before.
    -   If MFA is not enabled, it directly redirects the user to the root page,
        granting them access to the application.

    Returns:
        Flask Response: Either renders the MFA page or redirects to the root page.
                        Returns False (though this return is not standard for Flask)
                        on an exception, which is not typical Flask behavior.
    """
    global LoginAttempts # Access the global LoginAttempts counter.

    LoginAttempts = 0 # Reset failed login attempts counter upon successful primary login.
    try:
        if bUseMFA:
            # If MFA is enabled, render the MFA input page.
            # GetOTP() # Original code had a call to GetOTP() here, possibly to send/display OTP.
            # This is commented out as its implementation was also commented.
            response = make_response(render_template("mfa.html"))
            return response
        else:
            # If MFA is not enabled, login is complete, redirect to the main application page.
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in admin_login_helper: " + str(e1))
        # Returning False here is not standard Flask practice; a redirect or error page is typical.
        # This path indicates an issue after primary login but before MFA/final redirect.
        return False # Should ideally be a Flask response, e.g., error page.


# -------------------------------------------------------------------------------
@app.route("/", methods=["POST"])
def do_admin_login():
    """
    Handles the admin login form submission.

    This function processes login attempts from the `login.html` page.
    1.  **Lockout Check:** Calls `CheckLockOutDuration()` to see if the UI is
        currently locked due to too many failed attempts. If locked, it renders
        the `locked.html` page with a countdown.
    2.  **Admin Login:** Checks if the submitted username and password match the
        configured admin credentials (`HTTPAuthUser`, `HTTPAuthPass`). If so,
        sets session variables (`logged_in`, `write_access`) and calls
        `admin_login_helper()` to proceed (e.g., to MFA or main page).
    3.  **Read-Only Login:** Checks for read-only credentials (`HTTPAuthUser_RO`,
        `HTTPAuthPass_RO`). If matched, sets `logged_in` but `write_access` to False.
    4.  **LDAP Login:** If local admin/read-only login fails, attempts LDAP
        authentication via `doLdapLogin()`.
    5.  **Failed Login:** If all authentication methods fail, it calls
        `CheckFailedLogin()` to record the failure (which might trigger a lockout)
        and re-renders `login.html` (likely with an error message).
    """
    # Check if the Web UI is currently locked due to excessive failed login attempts.
    CheckLockOutDuration()
    if WebUILocked:
        # Calculate remaining lockout time.
        next_time = (datetime.datetime.now() - LastFailedLoginTime).total_seconds()
        str_seconds = str(int(LockOutDuration - next_time))
        # Render the locked page, passing the remaining time.
        response = make_response(render_template("locked.html", time=str_seconds))
        response.headers["Content-type"] = "text/html; charset=utf-8" # Ensure correct content type.
        response.mimetype = "text/html; charset=utf-8"
        return response

    # Check against primary admin username and password (case-insensitive for username).
    if (
        request.form["password"] == HTTPAuthPass
        and request.form["username"].lower() == HTTPAuthUser.lower()
    ):
        session["logged_in"] = True # Mark as logged in.
        session["write_access"] = True # Grant write access.
        LogError("Admin Login successful for user: " + request.form["username"])
        return admin_login_helper() # Proceed to MFA or main page.
    # Check against read-only username and password.
    elif (
        request.form["password"] == HTTPAuthPass_RO
        and request.form["username"].lower() == HTTPAuthUser_RO.lower()
    ):
        session["logged_in"] = True # Mark as logged in.
        session["write_access"] = False # Grant read-only access (no write access).
        LogError("Limited Rights Login successful for user: " + request.form["username"])
        return admin_login_helper() # Proceed to MFA or main page.
    # Attempt LDAP login if local credentials don't match.
    elif doLdapLogin(request.form["username"], request.form["password"]):
        # LDAP login success is handled within doLdapLogin, which sets session variables.
        # Log message for LDAP success is also handled in doLdapLogin.
        return admin_login_helper() # Proceed to MFA or main page.
    # If username was provided but all authentication methods failed.
    elif request.form["username"] != "":
        LogError("Invalid login attempt for user: " + request.form["username"])
        CheckFailedLogin() # Record the failed attempt, potentially triggering lockout.
        return render_template("login.html") # Re-render login page (likely with error message).
    else:
        # If username field was empty, just re-render login page.
        return render_template("login.html")


# -------------------------------------------------------------------------------
def CheckLockOutDuration():
    """
    Checks and manages login lockout status based on failed attempts.

    -   If `MaxLoginAttempts` is 0 (disabled), this function does nothing.
    -   If the number of `LoginAttempts` meets or exceeds `MaxLoginAttempts`:
        -   It checks if the `LockOutDuration` has passed since `LastFailedLoginTime`.
            -   If duration has passed, it unlocks the UI (`WebUILocked = False`)
                and resets `LoginAttempts`.
            -   If duration has NOT passed, `WebUILocked` remains True.
        -   If `WebUILocked` is True and a security message about lockout hasn't
            been sent recently (within the last 4 hours), it sends a notification
            via `ui_presenter.handle_notify_message()` and updates
            `securityMessageSent` timestamp.
    """
    global WebUILocked       # Flag indicating if UI is locked.
    global LoginAttempts     # Counter for failed login attempts.
    global securityMessageSent # Timestamp of the last lockout notification.

    # If MaxLoginAttempts is 0, lockout feature is disabled.
    if MaxLoginAttempts == 0:
        return

    # Check if the number of login attempts has reached the maximum limit.
    if LoginAttempts >= MaxLoginAttempts:
        # If lockout duration has passed since the last failed attempt, unlock.
        if (datetime.datetime.now() - LastFailedLoginTime).total_seconds() > LockOutDuration:
            WebUILocked = False # Unlock the UI.
            LoginAttempts = 0   # Reset the login attempts counter.
            log.info("Login lockout duration expired. UI unlocked.")
        else:
            # If lockout duration has not passed, keep UI locked.
            WebUILocked = True
            # Send a security message if one hasn't been sent recently (e.g., within last 4 hours).
            # This prevents spamming notifications for an ongoing lockout.
            if securityMessageSent == None or (
                (datetime.datetime.now() - securityMessageSent).total_seconds() > (4 * 60 * 60) # 4 hours in seconds
            ):
                message_details = {
                    "title": "Security Warning: Genmon Login Locked",
                    "body": f"Genmon login at site '{SiteName}' is temporarily locked due to exceeding the maximum ({MaxLoginAttempts}) allowed login attempts. Lockout duration is {LockOutDuration // 60} minutes.",
                    "type": "error", # Use error type for high visibility.
                    # "oncedaily": False, # These are defaults if not present in JSON for handler
                    # "onlyonce": False,
                }
                command_params_json = json.dumps(message_details)
                # Use ui_presenter to handle sending the notification (typically via email).
                response_data = ui_presenter.handle_notify_message(command_params_json)
                if response_data.get("status") == "OK":
                    securityMessageSent = datetime.datetime.now() # Update timestamp of last sent notification.
                    log.info("Security lockout notification sent.")
                else:
                    LogError(f"Failed to send security lockout notification: {response_data.get('message')}")


# -------------------------------------------------------------------------------
def CheckFailedLogin():
    """
    Records a failed login attempt and checks if a lockout should occur.

    This function is called after a login attempt fails.
    -   It increments the global `LoginAttempts` counter.
    -   It updates `LastFailedLoginTime` to the current time.
    -   It then calls `CheckLockOutDuration()` to determine if this failed
        attempt should trigger a lockout or if a lockout is already active.
    """
    global LoginAttempts         # Counter for failed attempts.
    global WebUILocked           # Not directly set here, but CheckLockOutDuration might set it.
    global LastFailedLoginTime   # Timestamp of the last failed attempt.

    # Increment the count of failed login attempts.
    LoginAttempts += 1
    # Record the time of this failed login.
    LastFailedLoginTime = datetime.datetime.now()
    log.warning(f"Failed login attempt recorded. Total attempts: {LoginAttempts}")

    # Check if this failed attempt triggers or maintains a lockout.
    CheckLockOutDuration()


# -------------------------------------------------------------------------------
def doLdapLogin(username, password):
    """
    Attempts to authenticate a user against an LDAP server.

    This function is called if local authentication fails and LDAP is configured.
    It requires the `ldap3` library.

    Configuration (from `genmon.conf` via `LoadConfig`):
    -   `LdapServer`: Address of the LDAP server.
    -   `LdapBase`: Base DN for user searches.
    -   `DomainNetbios`: NetBIOS domain name (used if username is not in `DOMAIN\\user` format).
    -   `LdapAdminGroup`: DN or CN of the LDAP group for admin access.
    -   `LdapReadOnlyGroup`: DN or CN of the LDAP group for read-only access.

    Logic:
    1.  Returns False immediately if LDAP is not configured (`LdapServer` is None).
    2.  Imports `ldap3` library. If import fails, logs error and returns False.
    3.  Parses username (handles `DOMAIN\\user` or just `user` formats).
    4.  Connects to LDAP server using NTLM authentication with provided credentials.
    5.  Searches for the user in `LdapBase` to retrieve their group memberships (`memberOf`).
    6.  Checks if the user is a member of `LdapAdminGroup` or `LdapReadOnlyGroup`.
    7.  Sets session variables (`logged_in`, `write_access`) based on group membership.
    8.  Unbinds from LDAP and returns True if authentication and group check were successful
        for either admin or read-only access, False otherwise.

    Args:
        username (str): The username for LDAP authentication.
        password (str): The password for LDAP authentication.

    Returns:
        bool: True if LDAP authentication is successful and user is in a permitted
              group (admin or read-only). False otherwise.
    """
    # If LDAP server is not configured, LDAP login is not possible.
    if LdapServer == None or LdapServer == "":
        return False
    try:
        # Dynamically import ldap3 library. This allows genmon to run without ldap3
        # if LDAP authentication is not used.
        from ldap3 import ALL, NTLM, Connection, Server
        from ldap3.utils.dn import escape_rdn # For escaping DN components.
        from ldap3.utils.conv import escape_filter_chars # For escaping LDAP filter characters.
    except ImportError as importException:
        LogError(
            "LDAP3 library import failed. If LDAP authentication is desired, run 'sudo pip install ldap3' (or pip3). Error: " + str(importException)
        )
        return False # Cannot proceed without ldap3.

    HasAdmin = False    # Flag if user has admin rights via LDAP group.
    HasReadOnly = False # Flag if user has read-only rights via LDAP group.

    try:
        # Parse username: check for "DOMAIN\user" format.
        SplitName = username.split("\\")
        if len(SplitName) == 2: # If "DOMAIN\user" format.
            DomainName = SplitName[0].strip()
            AccountName = SplitName[1].strip()
        else: # If only username is provided, use DomainNetbios from config.
            LogConsole("Using domain name from config file for LDAP login.")
            DomainName = DomainNetbios
            AccountName = username.strip()
    except IndexError: # Fallback if splitting fails unexpectedly.
        LogConsole("Error parsing username for LDAP. Using domain name from config file.")
        DomainName = DomainNetbios
        AccountName = username.strip()

    try:
        # Establish connection to the LDAP server.
        server = Server(LdapServer, get_info=ALL) # Get server info.
        conn = Connection(
            server,
            user="{}\\{}".format(DomainName, AccountName), # Format username as DOMAIN\user.
            password=password,
            authentication=NTLM, # Use NTLM authentication.
            auto_bind=True,      # Attempt to bind automatically upon connection.
        )
        # If auto_bind fails, conn.bind() would be False or raise an exception.
        # For ldap3, successful auto_bind means conn.bound is True.
        if not conn.bound:
            LogError(f"LDAP bind failed for user {DomainName}\\{AccountName}. Check credentials or server availability.")
            return False

        # Construct LDAP search filter for the user.
        # escape_filter_chars is important to prevent LDAP injection vulnerabilities.
        loginbasestr = escape_filter_chars(f"(&(objectclass=user)(sAMAccountName={AccountName}))")

        # Search for the user and retrieve their 'memberOf' attribute (group memberships).
        conn.search(
            LdapBase,       # Base DN to search within.
            loginbasestr,   # Search filter.
            attributes=["memberOf"], # Attributes to retrieve.
        )

        # Process search results (should be at most one user entry).
        for user_entry in conn.entries: # Iterate through found user entries.
            for group_dn in user_entry.memberOf: # Iterate through the user's group DNs.
                # Check for admin group membership (case-insensitive comparison of CN).
                if LdapAdminGroup and group_dn.upper().find(f"CN={LdapAdminGroup.upper()}" + ",") >= 0:
                    HasAdmin = True
                # Check for read-only group membership.
                elif LdapReadOnlyGroup and group_dn.upper().find(f"CN={LdapReadOnlyGroup.upper()}" + ",") >= 0:
                    HasReadOnly = True
        conn.unbind() # Close the LDAP connection.
    except Exception as e_ldap:
        LogError(f"Error during LDAP login processing for user {username}: {str(e_ldap)}. Check credentials, server, and config parameters (Base DN, Group Names).")
        return False # LDAP operation failed.

    # Set session variables based on LDAP group membership.
    session["logged_in"] = HasAdmin or HasReadOnly # User is logged in if in either group.
    session["write_access"] = HasAdmin           # Write access only if in admin group.

    if HasAdmin:
        LogError("Admin Login via LDAP successful for user: " + username)
    elif HasReadOnly:
        LogError("Limited Rights Login via LDAP successful for user: " + username)
    else:
        LogError("LDAP authentication successful for user: " + username + ", but user not in a permitted group (Admin or ReadOnly). Access denied.")

    return HasAdmin or HasReadOnly # Return True if user is in a permitted group.


# -------------------------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):
    """
    Main endpoint for handling client commands via URL path.

    This route receives a command as part of the URL path (e.g., "/cmd/status").
    -   It checks if the application is closing or restarting, returning "Closing" if so.
    -   If HTTP authentication is configured (`HTTPAuthUser` and `HTTPAuthPass` are set),
        it verifies if the user is logged in via the session. If not, it renders
        the `login.html` page.
    -   If authentication passes (or is not configured), it calls
        `ProcessCommand(command)` to handle the actual command execution and
        returns its response.

    Args:
        command (str): The command string extracted from the URL.

    Returns:
        Flask Response: The result of `ProcessCommand`, which can be a JSON
                        response, rendered HTML, or a file download.
                        Returns "Closing" if the application is shutting down.
                        Renders `login.html` if authentication is required and fails.
    """
    # If the application is in the process of closing or restarting, do not process new commands.
    if Closing or Restarting:
        return jsonify("Closing") # Send a simple "Closing" message.

    # If HTTP authentication is enabled (admin user/pass is set).
    if HTTPAuthUser is not None and HTTPAuthPass is not None:
        # Check if the user is logged in via the session.
        if not session.get("logged_in"):
            # If not logged in, render the login page.
            return render_template("login.html")
        else:
            # If logged in, process the command.
            return ProcessCommand(command)
    else:
        # If HTTP authentication is not enabled, process the command directly.
        return ProcessCommand(command)


# -------------------------------------------------------------------------------
def ProcessCommand(command):
    """
    Central dispatcher for processing various client commands.

    This function takes a command string (after basic validation and stripping
    of "generator:" prefix by the caller like the /cmd/<command> route),
    determines the action to take, calls the appropriate method in `UIPresenter`
    or legacy handlers, and returns the result.

    Args:
        command (str): The base command string (e.g., "status", "status_json", "setexercise").
                       For commands with parameters (like "setexercise=data"), this `command`
                       argument is just the command part (e.g., "setexercise"), and parameters
                       are typically fetched from `request.args` within specific handlers.

    Returns:
        Flask Response or str or dict:
            - For text-based display commands (status, maint, logs, etc.), returns
              HTML rendered via `render_template("command_template.html", ...)`.
            - For "_json" commands, returns a JSON response via `jsonify(data)`.
            - For action commands, typically returns a JSON status like `{"status": "OK"}`.
            - For file download commands (backup, get_logs), returns a file via `send_file`.
            - For unknown commands or errors, returns an error page or JSON error.
    """
    try:
        # --- Text-based command rendering (using UIPresenter) ---
        # These commands render HTML pages using a common template.
        if command == "status":
            page_data = ui_presenter.get_status_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon)
        elif command == "maint":
            page_data = ui_presenter.get_maint_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon)
        elif command == "logs":
            page_data = ui_presenter.get_logs_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon)
        elif command == "monitor":
            page_data = ui_presenter.get_monitor_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon, command=command)
        elif command == "outage":
            page_data = ui_presenter.get_outage_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon, command=command)
        elif command == "help":
            page_data = ui_presenter.get_help_text_data()
            return render_template("command_template.html", **page_data, favicon_path=favicon, command=command)

        # --- JSON data commands (using UIPresenter) ---
        # These commands return data in JSON format.
        data = None # Initialize data to None
        if command == "status_json":
            data = ui_presenter.get_status_json()
        elif command == "outage_json":
            data = ui_presenter.get_outage_json()
        elif command == "maint_json":
            data = ui_presenter.get_maint_json()
        elif command == "logs_json":
            data = ui_presenter.get_logs_json()
        elif command == "monitor_json":
            data = ui_presenter.get_monitor_json()
        elif command == "registers_json":
            data = ui_presenter.get_registers_json()
        elif command == "allregs_json":
            data = ui_presenter.get_allregs_json()
        elif command == "start_info_json":
            # For start_info_json, provide session context to the presenter.
            session_data_for_presenter = {
                "write_access": session.get("write_access", True), # Default to True if not set, but should be.
                "LoginActive": LoginActive()
            }
            data = ui_presenter.get_start_info_json(session_data_for_presenter)
        elif command == "gui_status_json":
            data = ui_presenter.get_gui_status_json()
        elif command == "power_log_json":
            # Extract 'power_log_json' parameter which specifies the period (e.g., "1440").
            log_period_str = request.args.get("power_log_json", default=None, type=str)
            data = ui_presenter.get_power_log_json(log_period=log_period_str)
            # Special handling: power_log_json from presenter returns a dict where the actual log is in 'processed_content'.
            return jsonify(data.get("processed_content", [])) 
        elif command == "status_num_json":
            data = ui_presenter.get_status_num_json()
        elif command == "maint_num_json":
            data = ui_presenter.get_maint_num_json()
        elif command == "monitor_num_json":
            data = ui_presenter.get_monitor_num_json()
        elif command == "outage_num_json":
            data = ui_presenter.get_outage_num_json()
        elif command == "get_maint_log_json":
            data = ui_presenter.get_maint_log_json()
        elif command == "support_data_json":
            data = ui_presenter.get_support_data_json()
        elif command == "getbase":
            data = {"response": ui_presenter.get_base_status()}
        elif command == "getsitename":
            data = {"response": ui_presenter.get_site_name()}
        elif command == "getdebug":
            data = ui_presenter.get_debug_info() # Assumes this returns a dict.

        # --- Action commands (using UIPresenter) ---
        # These commands perform an action and typically return a status (OK/error).
        # Check for write access before executing modifying commands.
        elif command == "setexercise":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("setexercise", default=None, type=str)
            if param_val: data = ui_presenter.handle_set_exercise(param_val)
            else: data = {"status": "error", "message": "setexercise parameter not provided."}
        elif command == "setquiet":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("setquiet", default=None, type=str)
            if param_val: data = ui_presenter.handle_set_quiet_mode(param_val)
            else: data = {"status": "error", "message": "setquiet parameter not provided."}
        elif command == "setremote":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("setremote", default=None, type=str)
            if param_val: data = ui_presenter.handle_set_remote_command(param_val)
            else: data = {"status": "error", "message": "setremote parameter not provided."}
        elif command == "add_maint_log":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("add_maint_log", default=None, type=str) # JSON data expected as string
            if param_val: data = ui_presenter.handle_add_maint_log(param_val)
            else: data = {"status": "error", "message": "add_maint_log parameter not provided."}
        elif command == "delete_row_maint_log":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("delete_row_maint_log", default=None, type=str)
            if param_val: data = ui_presenter.handle_delete_row_maint_log(param_val)
            else: data = {"status": "error", "message": "delete_row_maint_log parameter not provided."}
        elif command == "edit_row_maint_log":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("edit_row_maint_log", default=None, type=str) # JSON data expected
            if param_val: data = ui_presenter.handle_edit_row_maint_log(param_val)
            else: data = {"status": "error", "message": "edit_row_maint_log parameter not provided."}
        elif command == "power_log_clear":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_power_log_clear()
        elif command == "fuel_log_clear":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_fuel_log_clear()
        elif command == "sendregisters":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_send_registers()
        elif command == "sendlogfiles":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_send_log_files()
        elif command == "notify_message":
            param_val = request.args.get("notify_message", default=None, type=str) # JSON data expected
            if param_val: data = ui_presenter.handle_notify_message(param_val)
            else: data = {"status": "error", "message": "notify_message parameter not provided."}
        elif command == "set_button_command":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            param_val = request.args.get("set_button_command", default=None, type=str) # JSON data expected
            if param_val: data = ui_presenter.handle_set_button_command(param_val)
            else: data = {"status": "error", "message": "set_button_command parameter not provided."}
        elif command == "settime":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_set_time()
        elif command == "clear_maint_log":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            data = ui_presenter.handle_clear_maint_log()
        
        # If 'data' was set by one of the above JSON/action command handlers, jsonify it.
        if data is not None:
            if isinstance(data, (dict, list)): # Check if it's already a type jsonify can handle.
                return jsonify(data)
            else: # If it's a simple string (e.g., "OK" from older handlers), wrap it for jsonify.
                return jsonify({"response": str(data)})

        # --- Settings and System Operation Commands ---
        # These commands often involve file operations or system-level changes.
        elif command == "updatesoftware":
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.update_software() # Calls a script to update software.
            return jsonify(result)
        elif command == "getfavicon": # Fetches the configured favicon path.
            path = ui_presenter.get_favicon_path()
            return jsonify({"favicon_path": path})
        elif command == "settings": # Gets general settings.
            settings_data = ui_presenter.get_general_settings()
            return jsonify(settings_data)
        elif command == "setsettings": # Saves general settings.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            # Expects settings as a JSON string in the 'setsettings' query parameter.
            query_param_str = request.args.get("setsettings", "{}")
            try:
                settings_dict = json.loads(query_param_str) if query_param_str else {}
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Invalid JSON format for setsettings."})
            result = ui_presenter.save_general_settings(settings_dict)
            return jsonify(result)
        elif command == "notifications": # Gets notification settings.
            settings_data = ui_presenter.get_notification_settings()
            return jsonify(settings_data)
        elif command == "setnotifications": # Saves notification settings.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            # Expects a JSON string with 'notifications' list and 'order' string.
            full_params_str = request.args.get("setnotifications", "{}")
            try:
                params_dict = json.loads(full_params_str)
                notifications_list = params_dict.get("notifications", [])
                order_str = params_dict.get("order", "")
            except json.JSONDecodeError:
                 return jsonify({"status": "error", "message": "Invalid JSON for setnotifications parameters."})
            result = ui_presenter.save_notification_settings(notifications_list, order_str)
            return jsonify(result)
        elif command == "get_add_on_settings": # Gets settings for add-on modules.
            settings_data = ui_presenter.get_addon_settings()
            return jsonify(settings_data)
        elif command == "set_add_on_settings": # Saves settings for add-on modules.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            query_param_str = request.args.get("set_add_on_settings", "{}")
            try:
                settings_dict = json.loads(query_param_str) if query_param_str else {}
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Invalid JSON for set_add_on_settings."})
            result = ui_presenter.save_addon_settings(settings_dict)
            return jsonify(result)
        elif command == "get_advanced_settings": # Gets advanced genmon settings.
            settings_data = ui_presenter.get_advanced_settings()
            return jsonify(settings_data)
        elif command == "set_advanced_settings": # Saves advanced genmon settings.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            query_param_str = request.args.get("set_advanced_settings", "{}")
            try:
                settings_dict = json.loads(query_param_str) if query_param_str else {}
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Invalid JSON for set_advanced_settings."})
            result = ui_presenter.save_advanced_settings(settings_dict)
            return jsonify(result)
        elif command == "getreglabels": # Gets register labels for UI display.
            labels_dict = ui_presenter.get_register_labels()
            return jsonify(labels_dict)
        elif command == "restart": # Restarts the genmon service.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.restart_genmon()
            return jsonify(result)
        elif command == "stop": # Stops the genmon service (and this Flask app).
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            Close() # Calls the global Close() function which includes sys.exit().
            return jsonify({"status": "OK", "message": "Stop command issued. Server is shutting down."}) # This line might not be reached.
        elif command == "shutdown": # Shuts down the host system.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.shutdown_system()
            return jsonify(result)
        elif command == "reboot": # Reboots the host system.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.reboot_system()
            return jsonify(result)
        elif command == "backup": # Creates and serves a backup of configuration files.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.backup_configuration()
            if result.get("status") == "OK" and "path" in result:
                return send_file(result["path"], as_attachment=True) # Send the backup file for download.
            else:
                return jsonify(result) # Return error if backup failed.
        elif command == "get_logs": # Creates and serves an archive of log files.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            result = ui_presenter.get_log_archive()
            if result.get("status") == "OK" and "path" in result:
                return send_file(result["path"], as_attachment=True) # Send log archive for download.
            else:
                return jsonify(result) # Return error if log archiving failed.
        elif command == "test_email": # Sends a test email with provided parameters.
            if not session.get("write_access", True): return jsonify({"status": "error", "message": "Read Only Mode"})
            email_params_str = request.args.get("test_email", "{}") # Expects JSON string of email params.
            try:
                email_params_dict = json.loads(email_params_str)
            except json.JSONDecodeError:
                return jsonify({"status": "error", "message": "Invalid JSON for test_email parameters."})
            result = ui_presenter.send_test_email(email_params_dict)
            return jsonify(result)
        else:
            # --- Fallback logic for unknown commands ---
            # If the command is not recognized by any of the above handlers.
            LogErrorLine(f"Unknown command received in ProcessCommand: {command}")
            return render_template("command_template.html", title="Unknown Command", command=command, data_content=f"Command '{command}' not recognized.", favicon_path=favicon), 404

    except Exception as e1:
        # --- Top-level try-except block for general error handling ---
        # Catches any unhandled exceptions during command processing.
        LogErrorLine("Error in Process Command: " + command + ": " + str(e1))
        # Ensure 'command' variable is defined for the error template, even if error occurred early.
        current_command_for_error = command if 'command' in locals() and command else "Unknown"
        return render_template("command_template.html", title="Error", command=current_command_for_error, data_content=f"Error processing command: {str(e1)}", favicon_path=favicon), 500


# -------------------------------------------------------------------------------
def LoginActive():
    """
    Checks if HTTP authentication (local or LDAP) is configured and active.

    Returns:
        bool: True if either local HTTP authentication (`HTTPAuthUser` and
              `HTTPAuthPass` are set) or LDAP authentication (`LdapServer` is set)
              is configured. False otherwise.
    """
    # Check if local HTTP username/password authentication is set up.
    if HTTPAuthUser != None and HTTPAuthPass != None:
        return True
    # Check if LDAP server authentication is set up.
    if LdapServer != None:
        return True
    return False # Return False if neither is configured.


# -------------------------------------------------------------------------------
# def SendTestEmail(query_string): # Commented out - functionality moved to UIPresenter
#     try:
#         if query_string == None or not len(query_string):
#             return "No parameters given for email test."
#         parameters = json.loads(query_string)
#         if not len(parameters):
#             return "No parameters"  # nothing to change return
# 
#     except Exception as e1:
#         LogErrorLine("Error getting parameters in SendTestEmail: " + str(e1))
#         return "Error getting parameters in email test: " + str(e1)
#     try:
#         smtp_server = str(parameters["smtp_server"])
#         smtp_server = smtp_server.strip()
#         smtp_port = int(parameters["smtp_port"])
#         email_account = str(parameters["email_account"])
#         email_account = email_account.strip()
#         sender_account = str(parameters["sender_account"])
#         sender_account = sender_account.strip()
#         if not len(sender_account):
#             sender_account == None
#         sender_name = str(parameters["sender_name"])
#         sender_name = sender_name.strip()
#         if not len(sender_name):
#             sender_name == None
#         recipient = str(parameters["recipient"])
#         recipient = recipient.strip()
#         password = str(parameters["password"])
#         if parameters["use_ssl"].lower() == "true":
#             use_ssl = True
#         else:
#             use_ssl = False
# 
#         if parameters["tls_disable"].lower() == "true":
#             tls_disable = True
#         else:
#             tls_disable = False
# 
#         if parameters["smtpauth_disable"].lower() == "true":
#             smtpauth_disable = True
#         else:
#             smtpauth_disable = False
# 
#     except Exception as e1:
#         LogErrorLine("Error parsing parameters in SendTestEmail: " + str(e1))
#         LogError(str(parameters))
#         return "Error parsing parameters in email test: " + str(e1)
# 
#     try:
#         # This now needs to call ui_presenter.send_test_email if kept,
#         # but the main call is already refactored in ProcessCommand.
#         # For now, commenting out the core logic.
#         # ReturnMessage = MyMail.TestSendSettings( # MyMail is not directly available here anymore
#         #     smtp_server=smtp_server,
#         #     smtp_port=smtp_port,
#         #     email_account=email_account,
#         #     sender_account=sender_account,
#         #     sender_name=sender_name,
#         #     recipient=recipient,
#         #     password=password,
#         #     use_ssl=use_ssl,
#         #     tls_disable=tls_disable,
#         #     smtpauth_disable=smtpauth_disable,
#         # )
#         # return ReturnMessage
#         return "SendTestEmail function in genserv.py is deprecated. Use UIPresenter."
#     except Exception as e1:
#         LogErrorLine("Error sending test email : " + str(e1))
#         return "Error sending test email : " + str(e1)


# -------------------------------------------------------------------------------
# def GetAddOns(): # Commented out - functionality moved to UIPresenter
#     AddOnCfg = collections.OrderedDict()
#     # ... (original content of GetAddOns) ...
#     return AddOnCfg


# ------------ AddNotificationAddOnParam ----------------------------------------
# def AddNotificationAddOnParam(AddOnCfg, addon_name, config_file): # Commented out - helper for GetAddOns
#     # ... (original content) ...
#     return AddOnCfg


# ------------ AddRetryAddOnParam -----------------------------------------------
# def AddRetryAddOnParam(AddOnCfg, addon_name, config_file): # Commented out - helper for GetAddOns
#     # ... (original content) ...
#     return AddOnCfg


# ------------ MyCommon::StripJson ----------------------------------------------
# def StripJson(InputString): # Commented out - utility function, ensure not used or move if needed
#     for char in '{}[]"':
#         InputString = InputString.replace(char, "")
#     return InputString


# ------------ MyCommon::DictToString -------------------------------------------
# def DictToString(InputDict, ExtraStrip=False): # Commented out - utility function
#     if InputDict == None:
#         return ""
#     ReturnString = json.dumps(
#         InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
#     )
#     return ReturnString
#     if ExtraStrip:
#         ReturnString = ReturnString.replace("} \n", "")
#     return StripJson(ReturnString) # StripJson is also commented out


# -------------------------------------------------------------------------------
# def CreateAddOnParam( # Commented out - helper for GetAddOns
#     value="", type="string", description="", bounds="", display_name=""
# ):
#     Parameter = collections.OrderedDict()
#     Parameter["value"] = value
#     Parameter["type"] = type
#     Parameter["description"] = description
#     Parameter["bounds"] = bounds
#     Parameter["display_name"] = display_name
#     return Parameter


# -------------------------------------------------------------------------------
# def GetAddOnSettings(): # Commented out - functionality moved to UIPresenter
#     try:
#         # return GetAddOns() # This would now call the commented-out GetAddOns
#         return {} # Return empty dict as placeholder
#     except Exception as e1:
#         LogErrorLine("Error in GetAddOnSettings: " + str(e1))
#         return {}


# -------------------------------------------------------------------------------
# def SaveAddOnSettings(query_string): # Commented out - functionality moved to UIPresenter
#     try:
#         # ... (original content) ...
#         # Restart() # This global Restart is also being refactored/removed
#         return
#     except Exception as e1:
#         LogErrorLine("Error in SaveAddOnSettings: " + str(e1))
#         return


# -------------------------------------------------------------------------------
# def ReadNotificationsFromFile(): # Commented out - functionality moved to UIPresenter
#     NotificationSettings = {}
#     # ... (original content) ...
#     return NotificationSettings


# -------------------------------------------------------------------------------
# def SaveNotifications(query_string): # Commented out - functionality moved to UIPresenter
#     # ... (original content) ...
#     try:
#         # ... (original content) ...
#         # Restart() # This global Restart is also being refactored/removed
#         pass # Original had no explicit return
#     except Exception as e1:
#         LogErrorLine("Error in SaveNotifications: " + str(e1))
#     return


# -------------------------------------------------------------------------------
# def ReadSingleConfigValue( # Commented out - this logic is now within MyConfig, used by UIPresenter
#     entry, filename=None, section=None, type="string", default="", bounds=None
# ):
#     # ... (original content) ...
#     return default


# -------------------------------------------------------------------------------
# def GetImportConfigFileNames(): # Commented out - potentially unused or should be in UIPresenter if needed
#     try:
#         # ... (original content) ...
#         return ",".join(listing)
#     except Exception as e1:
#         # ... (original content) ...
#         return ""


# -------------------------------------------------------------------------------
# def ReadAdvancedSettingsFromFile(): # Commented out - functionality moved to UIPresenter
#     ConfigSettings = collections.OrderedDict()
#     # ... (original content) ...
#     return ConfigSettings


# -------------------------------------------------------------------------------
# def SaveAdvancedSettings(query_string): # Commented out - functionality moved to UIPresenter
#     try:
#         # ... (original content) ...
#         # Restart() # This global Restart is also being refactored/removed
#         pass # Original had return, but was inside try
#     except Exception as e1:
#         # ... (original content) ...
#         pass


# -------------------------------------------------------------------------------
# def ReadSettingsFromFile(): # Commented out - functionality moved to UIPresenter
#     ConfigSettings = collections.OrderedDict()
#     # ... (original content) ...
#     return ConfigSettings


# -------------------------------------------------------------------------------
# def GetAllConfigValues(FileName, section): # Commented out - MyConfig handles this, used by UIPresenter
#     ReturnDict = {}
#     # ... (original content) ...
#     return ReturnDict


# -------------------------------------------------------------------------------
# def GetControllerInfo(request=None): # Commented out - this info should come from UIPresenter via start_info_json
#     ReturnValue = "Evolution, Air Cooled"
#     # ... (original content) ...
#     return ReturnValue


# -------------------------------------------------------------------------------
# def CacheToolTips(): # Commented out - tooltip/label logic should be in UIPresenter if needed, or via get_register_labels
#     global CachedToolTips
#     # ... (original content) ...
#     pass


# -------------------------------------------------------------------------------
# def GetToolTips(ConfigSettings): # Commented out - helper for above
#     try:
#         # ... (original content) ...
#         pass
#     except Exception as e1:
#         # ... (original content) ...
#         pass


# -------------------------------------------------------------------------------
# def SaveSettings(query_string): # Commented out - functionality moved to UIPresenter
#     try:
#         # ... (original content) ...
#         # Restart() # This global Restart is also being refactored/removed
#         pass
#     except Exception as e1:
#         # ... (original content) ...
#         pass


# ---------------------MySupport::UpdateConfigFile-------------------------------
# Add or update config item
# def UpdateConfigFile(FileName, section, Entry, Value): # Commented out - MyConfig handles this
#     # ... (original content) ...
#     return False


# -------------------------------------------------------------------------------
# return False if File not present
def CheckCertFiles(CertFile, KeyFile):
    """
    Checks if the SSL certificate and key files exist.

    Args:
        CertFile (str): Path to the SSL certificate file.
        KeyFile (str): Path to the SSL private key file.

    Returns:
        bool: True if both files exist, False otherwise.
    """
    try:
        if not os.path.isfile(CertFile):
            LogConsole("Missing cert file : " + CertFile)
            return False
        if not os.path.isfile(KeyFile):
            LogConsole("Missing key file : " + KeyFile)
            return False
    except Exception as e1:
        LogErrorLine(
            "Error in CheckCertFiles: Unable to open Cert or Key file: "
            + CertFile
            + ", "
            + KeyFile
            + " : "
            + str(e1)
        )
        return False
    return True


# -------------------------------------------------------------------------------
def generate_adhoc_ssl_context():
    """
    Generates a temporary, self-signed SSL context for HTTPS if one is not provided.
    This uses the OpenSSL library via the `crypto` module from `pyOpenSSL`.

    Returns:
        ssl.SSLContext or None: An SSL context object if successful, or None on error.
    """
    # Generates an adhoc SSL context web server.
    try:
        import atexit # To schedule removal of temp files on exit.
        import ssl    # Standard Python SSL module.
        import tempfile # For creating temporary certificate files.
        from random import random # For generating a random serial number.

        from OpenSSL import crypto # pyOpenSSL library for certificate manipulation.

        # Create an X.509 certificate object.
        cert = crypto.X509()
        # Set a random serial number for the certificate.
        cert.set_serial_number(int(random() * sys.maxsize))
        # Set validity period: not before now, not after 1 year.
        cert.gmtime_adj_notBefore(0) # 0 seconds from now.
        cert.gmtime_adj_notAfter(60 * 60 * 24 * 365) # 1 year in seconds.

        # Set certificate subject (identifies the entity the certificate belongs to).
        subject = cert.get_subject()
        subject.CN = "*" # Common Name: wildcard, matches any hostname.
        subject.O = "Dummy Certificate" # Organization.

        # Set certificate issuer (identifies the entity that signed the certificate).
        # For self-signed certs, subject and issuer are often similar or the same.
        issuer = cert.get_issuer()
        issuer.CN = "Untrusted Authority"
        issuer.O = "Self-Signed"

        # Generate a new RSA private/public key pair (2048 bits).
        pkey = crypto.PKey()
        pkey.generate_key(crypto.TYPE_RSA, 2048)
        # Assign the public key to the certificate.
        cert.set_pubkey(pkey)
        # Sign the certificate with the private key using SHA256 hash algorithm.
        cert.sign(pkey, "sha256")

        # Create temporary files to store the certificate and private key.
        # These files are needed by ssl.SSLContext.load_cert_chain().
        cert_handle, cert_file_path = tempfile.mkstemp()
        pkey_handle, pkey_file_path = tempfile.mkstemp()

        # Schedule the removal of these temporary files when the program exits.
        atexit.register(os.remove, pkey_file_path)
        atexit.register(os.remove, cert_file_path)

        # Write the certificate and private key to the temporary files in PEM format.
        os.write(cert_handle, crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        os.write(pkey_handle, crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        os.close(cert_handle)
        os.close(pkey_handle)

        # Create an SSL context. PROTOCOL_SSLv23 is often used for broad compatibility,
        # though modern practice might prefer PROTOCOL_TLS.
        ctx = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        # Load the certificate chain (cert + private key) into the context.
        ctx.load_cert_chain(cert_file_path, pkey_file_path)
        # For self-signed, no CA verification is typically done by the server itself.
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    except Exception as e1:
        LogError("Error in generate_adhoc_ssl_context: " + str(e1))
        return None


# -------------------------------------------------------------------------------
def LoadConfig():
    """
    Loads various configuration settings from `genmon.conf` and `mymail.conf`
    into global variables used by the Flask application.

    This function is critical for initializing the web server's behavior,
    including networking, authentication, security, and paths.

    Global variables set by this function:
    -   `log`: The main logger instance.
    -   `clientport`: Port for genmon's internal client interface.
    -   `loglocation`: Directory for log files.
    -   `bUseMFA`, `SecretMFAKey`, `MFA_URL`: MFA related settings.
    -   `bUseSecureHTTP`, `SSLContext`, `bUseSelfSignedCert`: HTTPS settings.
    -   `ListenIPAddress`, `HTTPPort`: Web server listening address and port.
    -   `HTTPAuthUser`, `HTTPAuthPass`, `HTTPAuthUser_RO`, `HTTPAuthPass_RO`: Local auth credentials.
    -   `LdapServer`, `LdapBase`, `DomainNetbios`, `LdapAdminGroup`, `LdapReadOnlyGroup`: LDAP settings.
    -   `favicon`: Path to the website favicon.
    -   `MaxLoginAttempts`, `LockOutDuration`: Login security settings.

    Returns:
        bool: True if configuration is loaded successfully, False otherwise.
    """
    global log
    global clientport
    global loglocation
    global bUseMFA
    global SecretMFAKey
    global MFA_URL # Added for completeness, used by SetupMFA
    global bUseSecureHTTP
    global LdapServer
    global LdapBase
    global DomainNetbios
    global LdapAdminGroup
    global LdapReadOnlyGroup

    global ListenIPAddress
    global HTTPPort
    global HTTPAuthUser
    global HTTPAuthPass
    global HTTPAuthUser_RO
    global HTTPAuthPass_RO
    global SSLContext
    global favicon
    global MaxLoginAttempts
    global LockOutDuration

    # Initialize some defaults or ensure they are reset
    HTTPAuthPass = None
    HTTPAuthUser = None
    SSLContext = None # This will be set to 'adhoc', a tuple (cert, key), or None
    LdapServer = None
    LdapBase = None
    DomainNetbios = None
    LdapAdminGroup = None
    LdapReadOnlyGroup = None

    try:
        # --- Client Port for genmon Backend ---
        # Port used by genserv to communicate with the main genmon.py process.
        if ConfigFiles[GENMON_CONFIG].HasOption("server_port"): # genmon.conf [GenMon] section
            clientport = ConfigFiles[GENMON_CONFIG].ReadValue(
                "server_port", return_type=int, default=ProgramDefaults.ServerPort
            )

        # --- Multi-Factor Authentication (MFA) Settings ---
        # bUseMFA: Enable/disable MFA for web UI login.
        bUseMFA = ConfigFiles[GENMON_CONFIG].ReadValue(
            "usemfa", return_type=bool, default=False
        )
        # SecretMFAKey: The secret key used for generating OTPs. Auto-generated if not present.
        SecretMFAKey = ConfigFiles[GENMON_CONFIG].ReadValue("secretmfa", default=None)
        if SecretMFAKey == None or SecretMFAKey == "": # If no key, generate and save one.
            SecretMFAKey = str(pyotp.random_base32())
            ConfigFiles[GENMON_CONFIG].WriteValue("secretmfa", str(SecretMFAKey))
        SetupMFA() # Generate MFA_URL based on the key.

        # --- HTTPS Settings ---
        # bUseSecureHTTP: Enable/disable HTTPS for the web UI.
        if ConfigFiles[GENMON_CONFIG].HasOption("usehttps"):
            bUseSecureHTTP = ConfigFiles[GENMON_CONFIG].ReadValue(
                "usehttps", return_type=bool
            )
        if not bUseSecureHTTP:
            bUseMFA = False # MFA should only be used over HTTPS for security.

        # --- Web Server Network Settings ---
        # ListenIPAddress: IP address for the Flask web server to listen on (e.g., "0.0.0.0" for all interfaces).
        ListenIPAddress = ConfigFiles[GENMON_CONFIG].ReadValue("flask_listen_ip_address", default="0.0.0.0")
        # HTTPPort: Port for the HTTP (or HTTPS if bUseSecureHTTP is True) web server.
        if ConfigFiles[GENMON_CONFIG].HasOption("http_port"):
            HTTPPort = ConfigFiles[GENMON_CONFIG].ReadValue(
                "http_port", return_type=int, default=8000
            )
        # Favicon: Path or filename for the website's favicon.
        if ConfigFiles[GENMON_CONFIG].HasOption("favicon"):
            favicon = ConfigFiles[GENMON_CONFIG].ReadValue("favicon")

        # --- Login Lockout Settings ---
        # MaxLoginAttempts: Number of failed login attempts before locking out the UI. 0 disables lockout.
        MaxLoginAttempts = ConfigFiles[GENMON_CONFIG].ReadValue(
            "max_login_attempts", return_type=int, default=5
        )
        # LockOutDuration: Duration in seconds for how long the UI remains locked.
        LockOutDuration = ConfigFiles[GENMON_CONFIG].ReadValue(
            "login_lockout_seconds", return_type=int, default=(5 * 60) # Default 5 minutes.
        )

        # --- Authentication Settings (Local HTTP Auth and LDAP) ---
        # HTTP authentication and LDAP are typically only meaningful if HTTPS is used.
        if bUseSecureHTTP:
            # LDAP Settings:
            if ConfigFiles[GENMON_CONFIG].HasOption("ldap_server"):
                LdapServer = ConfigFiles[GENMON_CONFIG].ReadValue("ldap_server", default="").strip()
                if LdapServer == "": LdapServer = None # Disable if empty.
                else: # If LdapServer is set, try to read related LDAP settings.
                    LdapBase = ConfigFiles[GENMON_CONFIG].ReadValue("ldap_base", default="").strip()
                    DomainNetbios = ConfigFiles[GENMON_CONFIG].ReadValue("domain_netbios", default="").strip()
                    LdapAdminGroup = ConfigFiles[GENMON_CONFIG].ReadValue("ldap_admingroup", default="").strip()
                    LdapReadOnlyGroup = ConfigFiles[GENMON_CONFIG].ReadValue("ldap_readonlygroup", default="").strip()
                    # Nullify if any essential related field is empty.
                    if LdapBase == "": LdapBase = None
                    if DomainNetbios == "": DomainNetbios = None
                    if LdapAdminGroup == "": LdapAdminGroup = None
                    if LdapReadOnlyGroup == "": LdapReadOnlyGroup = None
                    # If critical LDAP settings are missing, disable LDAP.
                    if not (LdapBase and DomainNetbios and (LdapAdminGroup or LdapReadOnlyGroup)):
                        LdapServer = None
                        log.warning("LDAP server configured but missing critical related settings (Base DN, Domain, or Group). LDAP disabled.")

            # Local HTTP Authentication Settings:
            if ConfigFiles[GENMON_CONFIG].HasOption("http_user"):
                HTTPAuthUser = ConfigFiles[GENMON_CONFIG].ReadValue("http_user", default="").strip()
                if HTTPAuthUser == "": HTTPAuthUser = None # Disable if username is empty.
                elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass"):
                    HTTPAuthPass = ConfigFiles[GENMON_CONFIG].ReadValue("http_pass", default="").strip()

                # Read-only user, if primary admin user is set.
                if HTTPAuthUser is not None and HTTPAuthPass is not None:
                    if ConfigFiles[GENMON_CONFIG].HasOption("http_user_ro"):
                        HTTPAuthUser_RO = ConfigFiles[GENMON_CONFIG].ReadValue("http_user_ro", default="").strip()
                        if HTTPAuthUser_RO == "": HTTPAuthUser_RO = None
                        elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass_ro"):
                            HTTPAuthPass_RO = ConfigFiles[GENMON_CONFIG].ReadValue("http_pass_ro", default="").strip()

            # SSL Context for HTTPS:
            HTTPSPort = ConfigFiles[GENMON_CONFIG].ReadValue("https_port", return_type=int, default=443) # Port for HTTPS.
            OldHTTPPort = HTTPPort # Store original HTTPPort in case HTTPS setup fails.
            HTTPPort = HTTPSPort # Switch to HTTPS port.

            if ConfigFiles[GENMON_CONFIG].HasOption("useselfsignedcert"):
                bUseSelfSignedCert = ConfigFiles[GENMON_CONFIG].ReadValue("useselfsignedcert", return_type=bool)

            if bUseSelfSignedCert:
                SSLContext = generate_adhoc_ssl_context() # Generate a self-signed cert.
                if SSLContext is None: # If generation failed.
                    log.error("Failed to generate self-signed SSL certificate. HTTPS will use Flask's adhoc if available, or might fail.")
                    SSLContext = "adhoc" # Fallback to Flask's built-in adhoc SSL if cert generation fails.
            else: # Use user-provided certificate files.
                CertFile = ConfigFiles[GENMON_CONFIG].ReadValue("certfile", default="").strip()
                KeyFile = ConfigFiles[GENMON_CONFIG].ReadValue("keyfile", default="").strip()
                if CheckCertFiles(CertFile, KeyFile): # Validate that the files exist.
                    SSLContext = (CertFile, KeyFile)
                else:
                    # If cert files are invalid/missing, revert to HTTP and disable HTTPS.
                    log.error("User-specified SSL cert/key files invalid or missing. Reverting to HTTP.")
                    HTTPPort = OldHTTPPort
                    bUseSecureHTTP = False # Effectively disable HTTPS.
                    SSLContext = None
                    bUseMFA = False # MFA disabled if HTTPS is not active.
        else: # If bUseSecureHTTP is False
             bUseMFA = False # MFA disabled if HTTPS is not active.


        app.secret_key = os.urandom(12) # Set a random secret key for Flask session management.
        return True
    except Exception as e1:
        LogConsole("Missing config file or config file entries during LoadConfig: " + str(e1))
        return False


# ---------------------ValidateOTP-----------------------------------------------
def ValidateOTP(password):
    """
    Validates a One-Time Password (OTP) against the configured MFA secret key.

    Args:
        password (str): The OTP code entered by the user.

    Returns:
        bool: True if the OTP is valid, False otherwise or if MFA is not configured.
    """
    if bUseMFA and SecretMFAKey: # Ensure MFA is enabled and a secret key exists.
        try:
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30) # Create TOTP object.
            return TimeOTP.verify(password) # Verify the provided OTP.
        except Exception as e1:
            LogErrorLine("Error in ValidateOTP: " + str(e1))
    return False # Return False if MFA not enabled, no key, or verification error.


# ---------------------GetOTP----------------------------------------------------
def GetOTP():
    """
    Generates the current OTP and sends it via email (intended functionality).

    Note: The original implementation of sending the OTP via email is commented out.
    This function, if called, would compute the OTP but not actively deliver it
    unless the email sending part is restored. It's typically used for scenarios
    where the user needs to be provided the OTP, e.g., if they can't use an
    authenticator app.

    Returns:
        str or None: The current OTP string if MFA is enabled, otherwise None.
                     The email sending part is currently non-operational.
    """
    try:
        if bUseMFA and SecretMFAKey: # Ensure MFA is enabled and a secret key exists.
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30) # Create TOTP object.
            OTP = TimeOTP.now() # Generate the current OTP.

            # The following email sending logic was in the original but commented out.
            # If restored, it would send the OTP via email.
            # msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
            # mail.sendEmail("Generator Monitor login one time password", msgbody)
            log.info(f"GetOTP: Generated OTP (email sending is typically disabled in default code): {OTP}")
            return OTP
    except Exception as e1:
        LogErrorLine("Error in GetOTP: " + str(e1))
    return None


# ---------------------SetupMFA--------------------------------------------------
def SetupMFA():
    """
    Sets up Multi-Factor Authentication (MFA) by generating the provisioning URL.

    This function uses the `SecretMFAKey` to create a provisioning URI (typically
    for QR code generation) that authenticator apps like Google Authenticator or Authy
    can use to set up OTP generation for genmon. The URI includes the sender's
    email account (from mail settings) as the account name and "Genmon" as the issuer.

    The generated URI is stored in the global `MFA_URL`.
    It also initializes the `MyMail` instance if not already done, as the sender
    email is used in the provisioning URI.
    """
    global MFA_URL # URL for QR code provisioning.
    global mail    # MyMail instance.

    try:
        # Initialize MyMail if not already done, to get sender_account for provisioning URI.
        if mail is None: # Check if mail object is already initialized.
            mail = MyMail(ConfigFilePath=ConfigFilePath, log=log) # Pass current ConfigFilePath and log.

        # Generate the provisioning URI for OTP authenticator apps.
        # Uses the email_account from mail settings as the username part of the URI.
        # Uses "Genmon" as the issuer name.
        MFA_URL = pyotp.totp.TOTP(SecretMFAKey).provisioning_uri(
            mail.SenderAccount if mail and mail.SenderAccount else "user@example.com", # Fallback account name
            issuer_name="Genmon"
        )
        # Original code had an attempt to add an image to the URL, which is not standard.
        # MFA_URL += "&image=https://raw.githubusercontent.com/jgyates/genmon/master/static/images/Genmon.png"
        log.info(f"MFA Provisioning URL generated (first part): {MFA_URL[:60]}...")
    except Exception as e1:
        LogErrorLine("Error setting up MFA provisioning URL: " + str(e1))
        MFA_URL = None # Set to None on error.


# ---------------------LogConsole------------------------------------------------
def LogConsole(Message):
    """Utility function to log a message to the console logger."""
    if not console == None:
        console.error(Message) # console logger often uses .error for visibility like print to stderr


# ---------------------LogError--------------------------------------------------
def LogError(Message):
    """Utility function to log an error message to the main file logger."""
    if not log == None:
        log.error(Message)


# ---------------------FatalError------------------------------------------------
def FatalError(Message):
    """
    Logs a fatal error message and then raises an exception to halt execution.

    Args:
        Message (str): The fatal error message to log.

    Raises:
        Exception: Always raises an exception with the provided message.
    """
    if not log == None:
        log.error("FATAL: " + Message)
    raise Exception(Message)


# ---------------------LogErrorLine----------------------------------------------
def LogErrorLine(Message):
    """
    Logs an error message along with the file name and line number where the
    error occurred.
    """
    if not log == None:
        LogError(Message + " : " + GetErrorLine())


# ---------------------GetErrorLine----------------------------------------------
def GetErrorLine():
    """
    Helper function to get the filename and line number of the current exception.

    Returns:
        str: A string in the format "filename:lineno".
    """
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# -------------------------------------------------------------------------------
def SignalClose(signum, frame):
    """
    Signal handler for SIGTERM and SIGINT.

    This method is registered as the handler for termination signals.
    When genmon receives SIGTERM (e.g., from `systemctl stop genmon`) or
    SIGINT (e.g., Ctrl+C), this method is called.

    It initiates the graceful shutdown process by calling `Close()`
    and then exits the program with status code 1.

    Args:
        signum (int): The signal number received.
        frame (frame object): The current stack frame at the time of the signal.
    """
    log.warning(f"SignalClose: Received signal {signum}. Initiating shutdown...")
    Close() # Call the main shutdown method.
    # sys.exit(1) # Close() now handles sys.exit


# -------------------------------------------------------------------------------
def Close():
    """
    Performs a graceful shutdown of the genserv Flask application and related components.

    This function is called when genserv is exiting, typically due to a signal
    (SIGTERM, SIGINT) or a "stop" command. It's responsible for:
    1.  Setting the global `Closing` flag to True to indicate shutdown is in progress.
        This can be checked by long-running request handlers or threads if any were
        to be added to genserv itself (though most threads are in the main genmon.py).
    2.  Calling `MyClientInterface.Close()` to close the connection to the main
        genmon.py backend. This is important to release resources.
    3.  Exiting the program using `sys.exit(0)` for a clean shutdown.

    Error handling is included for the `MyClientInterface.Close()` call.
    """
    global Closing # Use the global Closing flag.

    if Closing: # Prevent re-entry if Close is already in progress.
        return
    Closing = True # Set the flag to indicate shutdown has started.

    log.info("Close method called for genserv. Initiating shutdown of client interface...")
    try:
        # Close the client interface connection to the main genmon daemon.
        if 'MyClientInterface' in globals() and MyClientInterface is not None:
            MyClientInterface.Close()
            log.info("MyClientInterface closed.")
        else:
            log.info("MyClientInterface was not initialized, skipping close.")
    except Exception as e1:
        LogErrorLine("Error during MyClientInterface.Close() in genserv: " + str(e1))

    log.info("genserv shutdown complete. Exiting now.")
    sys.exit(0) # Exit the Flask application process.


# -------------------------------------------------------------------------------
if __name__ == "__main__":
    # --- Main execution block when genserv.py is run directly ---

    # Setup an initial console logger for messages before file logging is fully configured.
    # This MySupport.SetupAddOnProgram likely sets up basic logging and command-line arg parsing.
    (
        console, # Console logger instance.
        ConfigFilePath, # Path to configuration files (e.g., /etc/genmon/).
        address, # IP address for client interface to connect to (main genmon.py).
        port,    # Port for client interface.
        loglocation, # Path for log files.
        log,     # Main file logger instance (can be None initially).
    ) = MySupport.SetupAddOnProgram("genserv") # "genserv" is the program name for logging.

    # Register signal handlers for SIGTERM and SIGINT to ensure graceful shutdown.
    signal.signal(signal.SIGTERM, SignalClose)
    signal.signal(signal.SIGINT, SignalClose)

    # --- Configuration File Paths ---
    # Define full paths to various configuration files used by genserv and its components.
    # These globals are used by LoadConfig and potentially other functions.
    MAIL_CONFIG = os.path.join(ConfigFilePath, "mymail.conf")
    GENMON_CONFIG = os.path.join(ConfigFilePath, "genmon.conf")
    GENLOADER_CONFIG = os.path.join(ConfigFilePath, "genloader.conf") # Used by Add-on settings
    GENSMS_CONFIG = os.path.join(ConfigFilePath, "gensms.conf")
    MYMODEM_CONFIG = os.path.join(ConfigFilePath, "mymodem.conf")
    GENPUSHOVER_CONFIG = os.path.join(ConfigFilePath, "genpushover.conf")
    GENMQTT_CONFIG = os.path.join(ConfigFilePath, "genmqtt.conf")
    GENMQTTIN_CONFIG = os.path.join(ConfigFilePath, "genmqttin.conf")
    GENSLACK_CONFIG = os.path.join(ConfigFilePath, "genslack.conf")
    GENCALLMEBOT_CONFIG = os.path.join(ConfigFilePath, "gencallmebot.conf")
    GENGPIOIN_CONFIG = os.path.join(ConfigFilePath, "gengpioin.conf")
    GENGPIOLEDBLINK_CONFIG = os.path.join(ConfigFilePath, "gengpioledblink.conf")
    GENEXERCISE_CONFIG = os.path.join(ConfigFilePath, "genexercise.conf")
    GENEMAIL2SMS_CONFIG = os.path.join(ConfigFilePath, "genemail2sms.conf")
    GENTANKUTIL_CONFIG = os.path.join(ConfigFilePath, "gentankutil.conf")
    GENCENTRICONNECT_CONFIG = os.path.join(ConfigFilePath, "gencentriconnect.conf")
    GENTANKDIY_CONFIG = os.path.join(ConfigFilePath, "gentankdiy.conf")
    GENALEXA_CONFIG = os.path.join(ConfigFilePath, "genalexa.conf")
    GENSNMP_CONFIG = os.path.join(ConfigFilePath, "gensnmp.conf")
    GENTEMP_CONFIG = os.path.join(ConfigFilePath, "gentemp.conf")
    GENCTHAT_CONFIG = os.path.join(ConfigFilePath, "gencthat.conf")
    GENMOPEKA_CONFIG = os.path.join(ConfigFilePath, "genmopeka.conf")
    GENSMS_VOIP_CONFIG = os.path.join(ConfigFilePath, "gensms_voip.conf")

    # List of all configuration files to be loaded into MyConfig objects.
    ConfigFileList = [
        GENMON_CONFIG, MAIL_CONFIG, GENLOADER_CONFIG, GENSMS_CONFIG, MYMODEM_CONFIG,
        GENPUSHOVER_CONFIG, GENMQTT_CONFIG, GENMQTTIN_CONFIG, GENSLACK_CONFIG,
        GENCALLMEBOT_CONFIG, GENGPIOIN_CONFIG, GENGPIOLEDBLINK_CONFIG, GENEXERCISE_CONFIG,
        GENEMAIL2SMS_CONFIG, GENTANKUTIL_CONFIG, GENCENTRICONNECT_CONFIG, GENTANKDIY_CONFIG,
        GENALEXA_CONFIG, GENSNMP_CONFIG, GENTEMP_CONFIG, GENCTHAT_CONFIG, GENMOPEKA_CONFIG,
        GENSMS_VOIP_CONFIG,
    ]

    # Validate existence of all listed configuration files.
    for ConfigFile in ConfigFileList:
        if not os.path.isfile(ConfigFile):
            LogConsole(f"CRITICAL: Missing required config file: {ConfigFile}. Exiting.")
            sys.exit(1)

    # --- Load Configuration Files ---
    # Create a dictionary of MyConfig objects, one for each configuration file.
    # This allows different parts of the code to access their specific configurations.
    ConfigFiles = {}
    for ConfigFile in ConfigFileList:
        # Use main file logger if available, otherwise use console logger for MyConfig.
        config_logger_to_use = log if log is not None else console
        ConfigFiles[ConfigFile] = MyConfig(filename=ConfigFile, log=config_logger_to_use)

    AppPath = sys.argv[0] # Get the path of the currently running script.
    # Load main application configurations (HTTP ports, auth, SSL, etc.) from GENMON_CONFIG and MAIL_CONFIG.
    if not LoadConfig(): # LoadConfig populates global variables like HTTPPort, SSLContext, etc.
        LogConsole("Error reading main application configuration from genmon.conf/mymail.conf. Exiting.")
        sys.exit(1)

    # Ensure all MyConfig instances use the main file logger after it's fully set up.
    for ConfigFile_instance in ConfigFileList: # Iterate through paths
        if ConfigFiles[ConfigFile_instance] is not None:
            ConfigFiles[ConfigFile_instance].log = log

    # Log application startup details.
    LogError(
        f"Starting {AppPath}, Port:{HTTPPort}, Secure HTTP: {bUseSecureHTTP}, "
        f"SelfSignedCert: {bUseSelfSignedCert}, UseMFA:{bUseMFA}"
    )
    # Validate presence of essential helper scripts.
    filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "startgenmon.sh")
    if not os.path.isfile(filename):
        LogError("CRITICAL: Required file missing: startgenmon.sh. Exiting.")
        sys.exit(1)
    filename = os.path.join(os.path.dirname(os.path.realpath(__file__)), "genmonmaint.sh")
    if not os.path.isfile(filename):
        LogError("CRITICAL: Required file missing: genmonmaint.sh. Exiting.")
        sys.exit(1)

    # --- Initialize Core Components ---
    # MyClientInterface: Handles communication with the main genmon.py backend.
    MyClientInterface = ClientInterface(host=address, port=clientport, log=log)
    # UIPresenter: Handles business logic and data preparation for the UI.
    # Pass GENMON_CONFIG path for presenter to access its specific settings if needed.
    ui_presenter = UIPresenter(MyClientInterface, GENMON_CONFIG, ConfigFilePath, log) # Pass full ConfigFilePath too

    # --- Initial Health Check and Startup Info Fetch ---
    # Loop to check if the main genmon backend is responsive and initialized.
    Start = datetime.datetime.now()
    health_ok = False
    while (datetime.datetime.now() - Start).total_seconds() < 10: # Timeout after 10 seconds.
        # Fetch health status directly via MyClientInterface as presenter might not be fully ready
        # or to ensure a basic backend check.
        health_data_str = MyClientInterface.ProcessMonitorCommand("generator: gethealth")
        if health_data_str and "OK" in health_data_str: # Check if "OK" is in the response string.
            LogConsole("Initial health check OK - genmon backend is responsive.")
            health_ok = True
            break
        time.sleep(0.5) # Wait before retrying.
    
    if not health_ok:
        LogError("CRITICAL: Failed to get OK health status from genmon backend after 10 seconds. genserv might not function correctly.")
        # Depending on requirements, could sys.exit(1) here. For now, allow Flask to try starting.

    # Global GStartInfo to store initial startup data from genmon backend.
    # This is used by some older template rendering parts directly.
    # Modern approach is for presenter to handle this data.
    GStartInfo = {}
    try:
        # Fetch initial startup information using the presenter.
        # Session data is not available at this stage, so pass placeholders.
        placeholder_session_data = {"write_access": False, "LoginActive": False}
        start_info_data_dict = ui_presenter.get_start_info_json(placeholder_session_data)
        if "error" in start_info_data_dict: # Check if presenter returned an error.
            LogError(f"Error getting start_info_json via UIPresenter: {start_info_data_dict['error']}")
        else:
            GStartInfo = start_info_data_dict # Populate global GStartInfo.
    except Exception as e1:
        LogError("Exception during initial fetch of start_info_json via UIPresenter: " + str(e1))
        # GStartInfo remains empty; some UI parts might not display correctly.

    # CacheToolTips() was commented out in original. Its functionality (loading tooltips)
    # is likely now integrated into UIPresenter or handled differently (e.g., getreglabels_json).
    # If GetControllerInfo was needed by CacheToolTips, that info is now within GStartInfo.

    # --- Run Flask Application ---
    try:
        # Start the Flask development server.
        # `threaded=True` allows handling multiple requests concurrently.
        # `ssl_context` is set if HTTPS is enabled (can be 'adhoc', (cert,key), or None).
        # `use_reloader=False` is important for production/stable environments to avoid unexpected restarts.
        # `debug=False` should be used for production; Flask's debug mode has security implications.
        log.info(f"Starting Flask app on {ListenIPAddress}:{HTTPPort} with SSLContext: {SSLContext}")
        app.run(
            host=ListenIPAddress,
            port=HTTPPort,
            threaded=True,
            ssl_context=SSLContext,
            use_reloader=False, # Important: reloader can cause issues with threads/signal handlers.
            debug=False, # Flask debug mode should be off in production.
        )

    except Exception as e1: # Catch errors during app.run(), like port already in use.
        LogErrorLine("Error in app.run: " + str(e1))
        # Specifically check for "Address already in use" (Errno 98 on Linux).
        if hasattr(e1, 'errno') and e1.errno == errno.EADDRINUSE:
            LogError(f"Port {HTTPPort} is already in use. Attempting retry...")
            time.sleep(2) # Wait for 2 seconds before retrying.
            try:
                app.run( # Retry app.run() once.
                    host=ListenIPAddress,
                    port=HTTPPort,
                    threaded=True,
                    ssl_context=SSLContext,
                    use_reloader=False,
                    debug=False,
                )
            except Exception as e2: # If retry also fails.
                LogErrorLine("Error in app.run (retry attempt): " + str(e2))
                sys.exit(1) # Exit if retry fails.
        else:
            sys.exit(1) # Exit for other app.run() errors.
    sys.exit(0) # Should not be reached if app.run() is blocking, but as a fallback.
