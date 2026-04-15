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
import errno
import hashlib
import json
import os
import os.path
import secrets
import signal
import subprocess
import sys
import threading
import time
import uuid

try:
    from flask import (
        Flask,
        Response,
        jsonify,
        make_response,
        redirect,
        render_template,
        request,
        send_file,
        send_from_directory,
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
    from genmonlib.myplatform import MyPlatform
    from genmonlib.program_defaults import ProgramDefaults

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

HTTPAuthUser = None
HTTPAuthPass = None
HTTPAuthUser_RO = None
HTTPAuthPass_RO = None
LdapServer = None
LdapBase = None
DomainNetbios = None
LdapAdminGroup = None
LdapReadOnlyGroup = None

mail = None
bUseMFA = False
bMfaEnrolled = False
SecretMFAKey = None
MFA_URL = None
RememberMeDays = 0
MfaTrustDays = 90
bMfaTrustExtend = False
LastOTPSendTime = None
bUseSecureHTTP = False
CertMode = "selfsigned"  # selfsigned | localca | custom
SSLContext = None
HTTPPort = 8000
OldHTTPPort = None
loglocation = ProgramDefaults.LogPath
clientport = ProgramDefaults.ServerPort
log = None
console = None
debug = False
AppPath = ""
favicon = "favicon.ico"
ConfigFilePath = ProgramDefaults.ConfPath

MAIL_SECTION = "MyMail"
GENMON_SECTION = "GenMon"

RedirectServer = None
WebUILocked = False
LoginAttempts = 0
MaxLoginAttempts = 5
LockOutDuration = 5 * 60
LastLoginTime = datetime.datetime.now()
LastFailedLoginTime = datetime.datetime.now()
securityMessageSent = None

Closing = False
Restarting = False
ControllerType = "generac_evo_nexus"
CriticalLock = threading.Lock()
CachedToolTips = {}
CachedRegisterDescriptions = {}


# -------------------------------------------------------------------------------
def StartHTTPRedirectServer():
    """Start a lightweight HTTP server on OldHTTPPort that 301-redirects
    every request to the HTTPS port.  Runs in a daemon thread so it dies
    with the main process."""
    import http.server
    import socketserver

    redirect_port = OldHTTPPort
    target_port = HTTPPort  # already set to HTTPSPort at this point

    class RedirectHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "localhost").split(":")[0]
            if target_port == 443:
                location = "https://" + host + self.path
            else:
                location = "https://" + host + ":" + str(target_port) + self.path
            # Serve an HTML page with JS redirect instead of a raw 302.
            # Chrome aggressively caches 301/302 redirects for IP addresses,
            # making it impossible to reach the HTTP site after HTTPS is disabled.
            # An HTML page is not cached as a redirect by the browser.
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            page = (
                "<!DOCTYPE html><html><head>"
                '<meta http-equiv="refresh" content="1;url={loc}">'
                "</head><body>"
                '<p>Redirecting to <a href="{loc}">{loc}</a>&hellip;</p>'
                "<script>location.replace('{loc}');</script>"
                "</body></html>"
            ).format(loc=location)
            self.wfile.write(page.encode("utf-8"))

        do_POST = do_GET
        do_PUT = do_GET
        do_DELETE = do_GET
        do_HEAD = do_GET

        def log_message(self, format, *args):
            pass  # suppress request logs

    global RedirectServer
    try:
        socketserver.TCPServer.allow_reuse_address = True
        RedirectServer = socketserver.TCPServer(
            (ListenIPAddress, redirect_port), RedirectHandler
        )
        LogDebug(
            "HTTP->HTTPS redirect active on port "
            + str(redirect_port)
            + " -> "
            + str(target_port)
        )
        RedirectServer.serve_forever()
    except Exception as e1:
        LogErrorLine(
            "Unable to start HTTP redirect server on port "
            + str(redirect_port)
            + ": "
            + str(e1)
        )


# -------------------------------------------------------------------------------
def HasWriteAccess():
    """Return True if the current request has write access.
    When authentication is disabled everyone gets full access.
    When authentication is enabled the session must carry an explicit True."""
    if not LoginActive():
        return True
    return session.get("write_access", False)


# -------------------------------------------------------------------------------
@app.before_request
def csrf_check():
    """Block cross-origin state-changing requests (CSRF protection).

    Reverse-proxy aware: trusts X-Forwarded-Host so that the browser's
    Origin (the public domain) matches even when Flask sees the backend
    address as request.host.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return  # safe methods — SameSite cookie handles GET-based CSRF
    # Login endpoints are protected by credentials, not session — exempt from CSRF
    if request.endpoint in ("do_admin_login", "passkey_login_begin", "passkey_login_complete", "mfa_auth"):
        return
    origin = request.headers.get("Origin")
    referer = request.headers.get("Referer")
    if not origin and not referer:
        LogError("CSRF blocked: missing Origin and Referer")
        return jsonify({"error": "CSRF validation failed"}), 403
    # Build the set of hosts we trust: the direct host Flask sees plus
    # any X-Forwarded-Host a reverse proxy (Caddy, nginx, etc.) provides.
    trusted_hosts = {request.host}
    fwd_host = request.headers.get("X-Forwarded-Host")
    if fwd_host:
        # X-Forwarded-Host may be a comma-separated list; trust all entries
        for h in fwd_host.split(","):
            trusted_hosts.add(h.strip())
    if origin:
        parsed = urlparse(origin)
        if parsed.netloc not in trusted_hosts:
            LogError("CSRF blocked: Origin mismatch: " + origin
                     + " (trusted: " + ", ".join(sorted(trusted_hosts)) + ")")
            return jsonify({"error": "Cross-origin request blocked"}), 403
    elif referer:
        parsed = urlparse(referer)
        if parsed.netloc not in trusted_hosts:
            LogError("CSRF blocked: Referer mismatch: " + referer
                     + " (trusted: " + ", ".join(sorted(trusted_hosts)) + ")")
            return jsonify({"error": "Cross-origin request blocked"}), 403


# -------------------------------------------------------------------------------
@app.route("/logout")
def logout():
    try:
        # remove the session data
        if LoginActive():
            session["logged_in"] = False
            session["write_access"] = False
            session["mfa_ok"] = False
        return redirect(url_for("root"))
    except Exception as e1:
        LogError("Error on logout: " + str(e1))


# -------------------------------------------------------------------------------
@app.after_request
def add_header(r):
    """
    Force cache header and add security headers
    """
    r.headers[
        "Cache-Control"
    ] = "no-cache, no-store, must-revalidate, public, max-age=0"
    r.headers["Pragma"] = "no-cache"
    r.headers["Expires"] = "0"

    # --- security headers ---
    r.headers["X-Content-Type-Options"] = "nosniff"
    r.headers["X-Frame-Options"] = "DENY"
    r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    r.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    r.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self' https://raw.githubusercontent.com; "
        "frame-ancestors 'none'"
    )

    # When HTTPS is off, tell browsers to stop forcing HTTPS (clears cached HSTS)
    if not bUseSecureHTTP:
        r.headers["Strict-Transport-Security"] = "max-age=0"

    return r


# -------------------------------------------------------------------------------
@app.route("/", methods=["GET"])
def root():

    if bUseMFA:
        if not "mfa_ok" in session or not session["mfa_ok"] == True:
            session["logged_in"] = False
            session["write_access"] = False
            session["mfa_ok"] = False
    return ServePage("index.html")


# -------------------------------------------------------------------------------
@app.route("/locked", methods=["GET"])
def locked():

    LogError("Locked Page")
    return render_template("locked.html", theme=get_theme_pref())

# -------------------------------------------------------------------------------
@app.route("/upload", methods=["POST"])
def upload():

    try:
        if not HasWriteAccess():
            return jsonify({"status": "error", "message": "Write access required."}), 403

        if "file" not in request.files:
            return jsonify({"status": "error", "message": "No file provided."}), 400

        f = request.files["file"]
        if f.filename == "":
            return jsonify({"status": "error", "message": "No file selected."}), 400

        if not f.filename.lower().endswith(".tar.gz"):
            return jsonify({"status": "error", "message": "Invalid file type. Expected a .tar.gz archive."}), 400

        # Read into memory and enforce size limit (10 MB)
        data = f.read()
        MAX_UPLOAD = 10 * 1024 * 1024
        if len(data) > MAX_UPLOAD:
            return jsonify({"status": "error", "message": "File too large. Maximum size is 10 MB."}), 400

        import tarfile, io, tempfile

        # Validate it's a real tar.gz archive
        try:
            buf = io.BytesIO(data)
            with tarfile.open(fileobj=buf, mode="r:gz") as tf:
                names = tf.getnames()
                # Security: reject path traversal
                for name in names:
                    if name.startswith("/") or ".." in name:
                        return jsonify({"status": "error", "message": "Archive contains unsafe paths."}), 400
                # Sanity check: must contain genmon_backup/ with at least one .conf
                has_conf = any(
                    n.startswith("genmon_backup/") and n.endswith(".conf") for n in names
                )
                if not has_conf:
                    return jsonify({"status": "error", "message": "Archive does not appear to be a valid genmon backup (no genmon_backup/*.conf found)."}), 400
        except tarfile.TarError:
            return jsonify({"status": "error", "message": "File is not a valid tar.gz archive."}), 400

        # Save to temp file and run restore script
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        upload_path = os.path.join(pathtofile, "genmon_restore_upload.tar.gz")
        try:
            with open(upload_path, "wb") as out:
                out.write(data)
            if not RestoreBackup(upload_path):
                return jsonify({"status": "error", "message": "Restore script failed. Check server logs."}), 500
        finally:
            if os.path.exists(upload_path):
                os.remove(upload_path)

        threading.Thread(target=Restart, daemon=True).start()
        return jsonify({"status": "ok", "message": "Configuration restored. Service is restarting\u2026"})

    except Exception as e1:
        LogErrorLine("Error in upload: " + str(e1))
        return jsonify({"status": "error", "message": "Server error during upload."}), 500

# -------------------------------------------------------------------------------
@app.route("/download/ca.crt")
def download_ca_der():
    """Serve the Local CA certificate in DER format for browser import."""
    try:
        ca_path = os.path.join(ConfigFilePath, "ca.crt")
        if not os.path.isfile(ca_path):
            return "CA certificate not found", 404
        from OpenSSL import crypto

        with open(ca_path, "rb") as f:
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        der = crypto.dump_certificate(crypto.FILETYPE_ASN1, ca_cert)
        return Response(
            der,
            mimetype="application/x-x509-ca-cert",
            headers={"Content-Disposition": "attachment; filename=genmon-ca.crt"},
        )
    except Exception as e1:
        LogErrorLine("Error in download_ca_der: " + str(e1))
        return "Error serving certificate", 500


# -------------------------------------------------------------------------------
@app.route("/import/ca.crt")
def import_ca_inline():
    """Serve the CA cert inline (no attachment header) so Firefox opens its
    native import dialog and Chrome/Edge download it automatically."""
    try:
        ca_path = os.path.join(ConfigFilePath, "ca.crt")
        if not os.path.isfile(ca_path):
            return "CA certificate not found", 404
        from OpenSSL import crypto

        with open(ca_path, "rb") as f:
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        der = crypto.dump_certificate(crypto.FILETYPE_ASN1, ca_cert)
        return Response(der, mimetype="application/x-x509-ca-cert")
    except Exception as e1:
        LogErrorLine("Error in import_ca_inline: " + str(e1))
        return "Error serving certificate", 500


# -------------------------------------------------------------------------------
@app.route("/download/ca.pem")
def download_ca_pem():
    """Serve the Local CA certificate in PEM format."""
    try:
        ca_path = os.path.join(ConfigFilePath, "ca.crt")
        if not os.path.isfile(ca_path):
            return "CA certificate not found", 404
        with open(ca_path, "rb") as f:
            pem_data = f.read()
        return Response(
            pem_data,
            mimetype="application/x-pem-file",
            headers={"Content-Disposition": "attachment; filename=genmon-ca.pem"},
        )
    except Exception as e1:
        LogErrorLine("Error in download_ca_pem: " + str(e1))
        return "Error serving certificate", 500


# -------------------------------------------------------------------------------
def get_theme_pref():
    try:
        raw = ConfigFiles[GENMON_CONFIG].ReadValue(
            "ui_prefs", return_type=str, section="GenMon", default="{}"
        )
        return json.loads(raw).get("theme", "dark")
    except Exception:
        return "dark"


# -------------------------------------------------------------------------------
def _render_login():
    """Render login page with theme and passkey availability."""
    has_pk = bUseMFA and bUseSecureHTTP and bool(_load_passkeys())
    return render_template("login.html", theme=get_theme_pref(), has_passkeys=has_pk, remember_me_enabled=RememberMeDays > 0)


# -------------------------------------------------------------------------------
def _get_mfa_trust_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.secret_key, salt="mfa-trust")


# -------------------------------------------------------------------------------
def _set_mfa_trust_cookie(response, username):
    s = _get_mfa_trust_serializer()
    token = s.dumps({"u": username})
    response.set_cookie(
        "mfa_trust", token,
        max_age=MfaTrustDays * 86400,
        httponly=True, secure=True, samesite="Lax",
    )
    return response


# -------------------------------------------------------------------------------
def _check_mfa_trust_cookie():
    if not bMfaTrustExtend:
        return None
    token = request.cookies.get("mfa_trust")
    if not token:
        return None
    try:
        s = _get_mfa_trust_serializer()
        data = s.loads(token, max_age=MfaTrustDays * 86400)
        return data.get("u")
    except Exception:
        return None


# -------------------------------------------------------------------------------
def ServePage(page_file):

    if LoginActive():
        if not session.get("logged_in"):
            return _render_login()
        else:
            return app.send_static_file(page_file)
    else:
        return app.send_static_file(page_file)


# -------------------------------------------------------------------------------
@app.route("/mfa", methods=["POST"])
def mfa_auth():

    try:
        if bUseMFA:
            code = request.form.get("code", "")
            verified = False
            # Check if this is a backup code (8 hex chars) or TOTP (6 digits)
            if len(code) == 8 and all(c in "0123456789abcdef" for c in code.lower()):
                verified = _validate_backup_code(session.get("username", ""), code)
            else:
                verified = ValidateOTP(code)

            if verified:
                session["mfa_ok"] = True
                resp = redirect(url_for("root"))
                # Set MFA trust cookie if checkbox was checked and trust is enabled
                if bMfaTrustExtend and request.form.get("trust_browser"):
                    username = session.get("username", "")
                    resp = _set_mfa_trust_cookie(resp, username)
                return resp
            else:
                session["logged_in"] = False
                session["write_access"] = False
                session["mfa_ok"] = False
                CheckFailedLogin()  # count toward brute-force lockout
                return redirect(url_for("logout"))
        else:
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in mfa_auth: " + str(e1))

    return _render_login()


# -------------------------------------------------------------------------------
def admin_login_helper():

    global LoginAttempts

    LoginAttempts = 0
    try:
        # remember-me: make session persistent if checkbox was checked and days > 0
        if request.form.get("remember_me") and RememberMeDays > 0:
            session.permanent = True

        if bUseMFA:
            # Check MFA trust cookie before showing MFA screen
            trust_user = _check_mfa_trust_cookie()
            if trust_user and trust_user == session.get("username", ""):
                session["mfa_ok"] = True
                resp = redirect(url_for("root"))
                resp = _set_mfa_trust_cookie(resp, trust_user)
                return resp
            # GetOTP()
            email_ok = mail is not None and not getattr(mail, 'DisableEmail', True) and not getattr(mail, 'DisableSMTP', True)
            uname = session.get("username", "").lower()
            bc_data = _load_backup_codes()
            has_bc = len(bc_data.get(uname, [])) > 0
            response = make_response(render_template("mfa.html", theme=get_theme_pref(), trust_enabled=bMfaTrustExtend, trust_days=MfaTrustDays, email_available=email_ok, has_backup_codes=has_bc))
            return response
        else:
            return redirect(url_for("root"))
    except Exception as e1:
        LogErrorLine("Error in admin_login_helper: " + str(e1))
        return False


# -------------------------------------------------------------------------------
@app.route("/", methods=["POST"])
def do_admin_login():

    CheckLockOutDuration()
    if WebUILocked:
        next_time = (datetime.datetime.now() - LastFailedLoginTime).total_seconds()
        str_seconds = str(int(LockOutDuration - next_time))
        response = make_response(render_template("locked.html", time=str_seconds, theme=get_theme_pref()))
        response.headers["Content-type"] = "text/html; charset=utf-8"
        response.mimetype = "text/html; charset=utf-8"
        return response

    submitted_user = request.form["username"].lower()
    submitted_pass = request.form["password"]

    # Timing-safe comparisons to prevent user/password enumeration
    admin_user_ok = secrets.compare_digest(submitted_user, (HTTPAuthUser or "").lower())
    admin_pass_ok = secrets.compare_digest(submitted_pass, HTTPAuthPass or "")
    ro_user_ok = secrets.compare_digest(submitted_user, (HTTPAuthUser_RO or "").lower())
    ro_pass_ok = secrets.compare_digest(submitted_pass, HTTPAuthPass_RO or "")

    if admin_user_ok and admin_pass_ok:
        session["logged_in"] = True
        session["write_access"] = True
        session["username"] = submitted_user
        LogError("Admin Login")
        return admin_login_helper()
    elif ro_user_ok and ro_pass_ok:
        session["logged_in"] = True
        session["write_access"] = False
        session["username"] = submitted_user
        LogError("Limited Rights Login")
        return admin_login_helper()
    elif doLdapLogin(request.form["username"], request.form["password"]):
        session["username"] = request.form["username"].lower()
        return admin_login_helper()
    elif request.form["username"] != "":
        LogError("Invalid login: " + request.form["username"])
        CheckFailedLogin()
        return _render_login()
    else:
        return _render_login()


# -------------------------------------------------------------------------------
def CheckLockOutDuration():

    global WebUILocked
    global LoginAttempts
    global securityMessageSent

    if MaxLoginAttempts == 0:
        return

    if LoginAttempts >= MaxLoginAttempts:
        if (
            datetime.datetime.now() - LastFailedLoginTime
        ).total_seconds() > LockOutDuration:
            WebUILocked = False
            LoginAttempts = 0
        else:
            WebUILocked = True
            # send message to user only once every 4 hours
            if securityMessageSent == None or (
                (datetime.datetime.now() - securityMessageSent).total_seconds()
                > (4 * 60)
            ):

                message = {
                    "title": "Security Warning",
                    "body": "Genmon login is locked due to exceeding the maximum login attempts.",
                    "type": "error",
                    "oncedaily": False,
                    "onlyonce": False,
                }
                command = "generator: notify_message=" + json.dumps(message)

                data = MyClientInterface.ProcessMonitorCommand(command)
                securityMessageSent = datetime.datetime.now()


# -------------------------------------------------------------------------------
def CheckFailedLogin():

    global LoginAttempts
    global WebUILocked
    global LastFailedLoginTime

    LoginAttempts += 1
    LastFailedLoginTime = datetime.datetime.now()

    CheckLockOutDuration()


# -------------------------------------------------------------------------------
def doLdapLogin(username, password):
    if LdapServer == None or LdapServer == "":
        return False
    try:
        from ldap3 import ALL, NTLM, Connection, Server
        from ldap3.utils.dn import escape_rdn
        from ldap3.utils.conv import escape_filter_chars
    except ImportError as importException:
        LogError(
            "LDAP3 import not found, run 'sudo pip install ldap3 && sudo pip3 install ldap3'"
        )
        LogError(importException)
        return False

    HasAdmin = False
    HasReadOnly = False
    try:
        SplitName = username.split("\\")
        DomainName = SplitName[0]
        DomainName = DomainName.strip()
        AccountName = SplitName[1]
        AccountName = AccountName.strip()
    except IndexError:
        LogError("Using domain name in config file")
        DomainName = DomainNetbios
        AccountName = username.strip()
    try:
        server = Server(LdapServer, get_info=ALL)
        conn = Connection(
            server,
            user="{}\\{}".format(DomainName, AccountName),
            password=password,
            authentication=NTLM,
            auto_bind=True,
        )
        loginbasestr = escape_filter_chars("(&(objectclass=user)(sAMAccountName=" + AccountName + "))")
        conn.search(
            LdapBase,
            loginbasestr,
            attributes=["memberOf"],
        )
        for user in sorted(conn.entries):
            for group in user.memberOf:
                if group.upper().find("CN=" + LdapAdminGroup.upper() + ",") >= 0:
                    HasAdmin = True
                elif group.upper().find("CN=" + LdapReadOnlyGroup.upper() + ",") >= 0:
                    HasReadOnly = True
        conn.unbind()
    except Exception:
        LogError("Error in LDAP login. Check credentials and config parameters")

    session["logged_in"] = HasAdmin or HasReadOnly
    session["write_access"] = HasAdmin
    if HasAdmin:
        LogError("Admin Login via LDAP")
    elif HasReadOnly:
        LogError("Limited Rights Login via LDAP")
    else:
        LogError("No rights for login via LDAP")

    return HasAdmin or HasReadOnly


# -------------------------------------------------------------------------------
@app.route("/cmd/<command>")
def command(command):

    if Closing or Restarting:
        return jsonify("Closing")
    if HTTPAuthUser == None or HTTPAuthPass == None:

        # Not everything sent to this function is a json string
        # so try to jsonify it and if that fails just return the
        # original string
        commandResponse = ProcessCommand(command)
        try:
            # Set Content-Type to application/json
            return jsonify(json.loads(commandResponse))
        except Exception as e1:
            return commandResponse
    if not session.get("logged_in"):
        return _render_login()
    else:
        commandResponse = ProcessCommand(command)
        try:
            return jsonify(json.loads(commandResponse))
        except Exception as e1:
            return commandResponse


# -------------------------------------------------------------------------------
def ProcessCommand(command):

    try:
        command_list = [
            "status",
            "status_json",
            "outage",
            "outage_json",
            "maint",
            "maint_json",
            "logs",
            "logs_json",
            "monitor",
            "monitor_json",
            "registers_json",
            "allregs_json",
            "start_info_json",
            "gui_status_json",
            "power_log_json",
            "power_log_clear",
            "getbase",
            "getsitename",
            "setexercise",
            "setquiet",
            "setremote",
            "settime",
            "sendregisters",
            "sendlogfiles",
            "getdebug",
            "status_num_json",
            "maint_num_json",
            "monitor_num_json",
            "outage_num_json",
            "get_maint_log_json",
            "add_maint_log",
            "clear_maint_log",
            "delete_row_maint_log",
            "edit_row_maint_log",
            "support_data_json",
            "fuel_log_clear",
            "notify_message",
            "set_button_command",
        ]
        # LogError(request.url)
        if command in command_list:
            finalcommand = "generator: " + command

            try:
                if command in [
                    "setexercise",
                    "setquiet",
                    "setremote",
                    "add_maint_log",
                    "delete_row_maint_log",
                    "edit_row_maint_log",
                ] and not HasWriteAccess():
                    return jsonify("Read Only Mode")

                if command == "setexercise":
                    settimestr = request.args.get("setexercise", 0, type=str)
                    if settimestr:
                        finalcommand += "=" + settimestr
                elif command == "setquiet":
                    # /cmd/setquiet?setquiet=off
                    setquietstr = request.args.get("setquiet", 0, type=str)
                    if setquietstr:
                        finalcommand += "=" + setquietstr
                elif command == "setremote":
                    setremotestr = request.args.get("setremote", 0, type=str)
                    if setremotestr:
                        finalcommand += "=" + setremotestr

                if command == "power_log_json":
                    # example: /cmd/power_log_json?power_log_json=1440
                    setlogstr = request.args.get("power_log_json", 0, type=str)
                    if setlogstr:
                        finalcommand += "=" + setlogstr
                # Sanitize command parameters: strip null bytes and newlines
                # to prevent header/log injection, cap length to limit abuse.
                if command == "add_maint_log":
                    # use direct method instead of request.args.get due to unicode
                    # input for add_maint_log for international users
                    input = request.args["add_maint_log"]
                    input = input.replace("\x00", "").replace("\n", " ").replace("\r", " ")[:2048]
                    finalcommand += "=" + input
                if command == "delete_row_maint_log":
                    input = request.args["delete_row_maint_log"]
                    input = input.replace("\x00", "").replace("\n", " ").replace("\r", " ")[:512]
                    finalcommand += "=" + input
                if command == "edit_row_maint_log":
                    input = request.args["edit_row_maint_log"]
                    input = input.replace("\x00", "").replace("\n", " ").replace("\r", " ")[:2048]
                    finalcommand += "=" + input
                if command == "set_button_command":
                    input = request.args["set_button_command"]
                    input = input.replace("\x00", "").replace("\n", " ").replace("\r", " ")[:512]
                    finalcommand += "=" + input
                data = MyClientInterface.ProcessMonitorCommand(finalcommand)

            except Exception as e1:
                data = "Retry"
                LogErrorLine("Error on command function: " + str(e1))

            if command in [
                "status_json",
                "outage_json",
                "maint_json",
                "monitor_json",
                "logs_json",
                "registers_json",
                "allregs_json",
                "start_info_json",
                "gui_status_json",
                "power_log_json",
                "status_num_json",
                "maint_num_json",
                "monitor_num_json",
                "outage_num_json",
                "get_maint_log_json",
                "support_data_json",
            ]:

                if command in ["start_info_json"]:
                    try:
                        StartInfo = json.loads(data)
                        StartInfo["write_access"] = HasWriteAccess()
                        if not StartInfo["write_access"]:
                            StartInfo["pages"]["settings"] = False
                            StartInfo["pages"]["notifications"] = False
                        StartInfo["LoginActive"] = LoginActive()
                        data = json.dumps(StartInfo, sort_keys=False)
                    except Exception as e1:
                        LogErrorLine("Error in JSON parse / decode: " + str(e1))
                return data
            return jsonify(data)

        elif command in ["updatesoftware"]:
            if HasWriteAccess():
                Update()
                return "OK"
            else:
                return "Access denied"

        elif command in ["getfavicon"]:
            return jsonify(favicon)

        elif command in ["settings"]:
            if HasWriteAccess():
                data = ReadSettingsFromFile()
                return json.dumps(data, sort_keys=False)
            else:
                return "Access denied"

        elif command in ["notifications"]:
            data = ReadNotificationsFromFile()
            return jsonify(data)
        elif command in ["setnotifications"]:
            if HasWriteAccess():
                SaveNotifications(request.args.get("setnotifications", 0, type=str))
            return "OK"

        # Add on items
        elif command in ["get_add_on_settings", "set_add_on_settings"]:
            if HasWriteAccess():
                if command == "get_add_on_settings":
                    data = GetAddOnSettings()
                    return json.dumps(data, sort_keys=False)
                elif command == "set_add_on_settings":
                    SaveAddOnSettings(
                        request.args.get("set_add_on_settings", default=None, type=str)
                    )
                else:
                    return "OK"
            return "OK"

        elif command in ["get_advanced_settings", "set_advanced_settings"]:
            if HasWriteAccess():
                if command == "get_advanced_settings":
                    data = ReadAdvancedSettingsFromFile()
                    return json.dumps(data, sort_keys=False)
                elif command == "set_advanced_settings":
                    SaveAdvancedSettings(
                        request.args.get(
                            "set_advanced_settings", default=None, type=str
                        )
                    )
                else:
                    return "OK"
            return "OK"

        elif command in ["setsettings"]:
            if HasWriteAccess():
                SaveSettings(request.args.get("setsettings", 0, type=str))
            return "OK"

        # ---- UI preferences (persisted to genmon.conf, no restart) ----
        elif command in ["get_ui_prefs", "set_ui_prefs"]:
            if command == "get_ui_prefs":
                try:
                    return ConfigFiles[GENMON_CONFIG].ReadValue(
                        "ui_prefs", return_type=str, section="GenMon", default="{}"
                    )
                except Exception:
                    return "{}"
            elif command == "set_ui_prefs":
                if HasWriteAccess():
                    raw = request.args.get("set_ui_prefs", "{}", type=str)
                    if len(raw) > 16384:  # 16 KB cap to prevent memory/storage abuse
                        return "Error: payload too large"
                    try:
                        json.loads(raw)  # validate JSON
                    except Exception:
                        return "Error: invalid JSON"
                    ConfigFiles[GENMON_CONFIG].WriteValue(
                        "ui_prefs", raw, section="GenMon"
                    )
                return "OK"

        elif command in ["getreglabels"]:
            return jsonify(CachedRegisterDescriptions)

        elif command in ["restart"]:
            if HasWriteAccess():
                Restart()
        elif command in ["stop"]:
            if HasWriteAccess():
                Close()
                sys.exit(0)
        elif command in ["shutdown"]:
            if HasWriteAccess():
                Shutdown()
                sys.exit(0)
        elif command in ["reboot"]:
            if HasWriteAccess():
                Reboot()
                sys.exit(0)
        elif command in ["backup"]:
            if HasWriteAccess():
                Backup()  # Create backup file
                # Now send the file
                pathtofile = os.path.dirname(os.path.realpath(__file__))
                return send_file(
                    os.path.join(pathtofile, "genmon_backup.tar.gz"), as_attachment=True
                )
        elif command in ["get_logs"]:
            if HasWriteAccess():
                GetLogs()  # Create log archive file
                # Now send the file
                pathtofile = os.path.dirname(os.path.realpath(__file__))
                return send_file(
                    os.path.join(pathtofile, "genmon_logs.tar.gz"), as_attachment=True
                )
        elif command in ["test_email"]:
            if HasWriteAccess():
                return SendTestEmail(request.args.get("test_email", default=None, type=str))
        else:
            return render_template("command_template.html", command=command)
    except Exception as e1:
        LogErrorLine("Error in Process Command: " + command + ": " + str(e1))
        return render_template("command_template.html", command=command)


# -------------------------------------------------------------------------------
def LoginActive():

    if HTTPAuthUser != None and HTTPAuthPass != None or LdapServer != None:
        return True
    return False


# -------------------------------------------------------------------------------
def SendTestEmail(query_string):
    try:
        if query_string == None or not len(query_string):
            return jsonify({"error": "No parameters given for email test."})
        parameters = json.loads(query_string)
        if not len(parameters):
            return jsonify({"error": "No parameters"})  # nothing to change return

    except Exception as e1:
        LogErrorLine("Error getting parameters in SendTestEmail: " + str(e1))
        return jsonify({"error": "Error getting parameters in email test: " + str(e1)})
    try:
        smtp_server = str(parameters["smtp_server"])
        smtp_server = smtp_server.strip()
        smtp_port = int(parameters["smtp_port"])
        email_account = str(parameters["email_account"])
        email_account = email_account.strip()
        sender_account = str(parameters["sender_account"])
        sender_account = sender_account.strip()
        if not len(sender_account):
            sender_account == None
        sender_name = str(parameters["sender_name"])
        sender_name = sender_name.strip()
        if not len(sender_name):
            sender_name == None
        recipient = str(parameters["recipient"])
        recipient = recipient.strip()
        password = str(parameters["password"])
        use_ssl = parameters["use_ssl"] in (True, "true", "True", "1", 1)
        tls_disable = parameters["tls_disable"] in (True, "true", "True", "1", 1)
        smtpauth_disable = parameters["smtpauth_disable"] in (True, "true", "True", "1", 1)

    except Exception as e1:
        LogErrorLine("Error parsing parameters in SendTestEmail: " + str(e1))
        LogError(str(parameters))
        return jsonify({"error": "Error parsing parameters in email test: " + str(e1)})

    try:
        ReturnMessage = MyMail.TestSendSettings(
            smtp_server=smtp_server,
            smtp_port=smtp_port,
            email_account=email_account,
            sender_account=sender_account,
            sender_name=sender_name,
            recipient=recipient,
            password=password,
            use_ssl=use_ssl,
            tls_disable=tls_disable,
            smtpauth_disable=smtpauth_disable,
        )
        return jsonify({"message": ReturnMessage})
    except Exception as e1:
        LogErrorLine("Error sending test email : " + str(e1))
        return jsonify({"error": "Error sending test email : " + str(e1)})


# -------------------------------------------------------------------------------
def GetAddOns():
    AddOnCfg = collections.OrderedDict()

    # Default icon name should be "Genmon" to get a generic icon
    try:
        # GENGPIO
        Temp = collections.OrderedDict()
        AddOnCfg["gengpio"] = collections.OrderedDict()
        AddOnCfg["gengpio"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpio", default=False
        )
        AddOnCfg["gengpio"]["title"] = "Genmon GPIO Outputs"
        AddOnCfg["gengpio"][
            "description"
        ] = "Genmon will set Raspberry Pi GPIO outputs (see documentation for details)"
        AddOnCfg["gengpio"]["icon"] = "rpi"
        AddOnCfg["gengpio"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpiopy-optional"
        AddOnCfg["gengpio"]["parameters"] = None

        # GENGPIOIN
        AddOnCfg["gengpioin"] = collections.OrderedDict()
        AddOnCfg["gengpioin"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpioin", default=False
        )
        AddOnCfg["gengpioin"]["title"] = "Genmon GPIO Inputs"
        AddOnCfg["gengpioin"][
            "description"
        ] = "Genmon will set Raspberry Pi GPIO inputs (see documentation for details)"
        AddOnCfg["gengpioin"]["icon"] = "rpi"
        AddOnCfg["gengpioin"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpioinpy-optional"
        AddOnCfg["gengpioin"]["parameters"] = collections.OrderedDict()
        AddOnCfg["gengpioin"]["parameters"]["trigger"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "trigger", return_type=str, default="falling"
            ),
            "list",
            "Set GPIO input to trigger on rising or falling edge.",
            bounds="falling,rising,both",
            display_name="GPIO Edge Trigger",
        )
        AddOnCfg["gengpioin"]["parameters"]["resistorpull"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "resistorpull", return_type=str, default="up"
            ),
            "list",
            "Set GPIO input internal pull up or pull down resistor.",
            bounds="up,down,off",
            display_name="Internal resistor pull",
        )
        AddOnCfg["gengpioin"]["parameters"]["bounce"] = CreateAddOnParam(
            ConfigFiles[GENGPIOIN_CONFIG].ReadValue(
                "bounce", return_type=int, default=0
            ),
            "int",
            "Minimum interval in milliseconds between valid input changes. Zero to disable, or positive whole number.",
            bounds="number",
            display_name="Software Debounce",
        )

        # GENGPIOLEDBLINK
        AddOnCfg["gengpioledblink"] = collections.OrderedDict()
        AddOnCfg["gengpioledblink"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gengpioledblink", default=False
        )
        AddOnCfg["gengpioledblink"]["title"] = "Genmon GPIO Output to blink LED"
        AddOnCfg["gengpioledblink"][
            "description"
        ] = "Genmon will blink LED connected to GPIO pin to indicate genmon status"
        AddOnCfg["gengpioledblink"]["icon"] = "rpi"
        AddOnCfg["gengpioledblink"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gengpioledblinkpy-optional"
        AddOnCfg["gengpioledblink"]["parameters"] = collections.OrderedDict()
        AddOnCfg["gengpioledblink"]["parameters"]["ledpin"] = CreateAddOnParam(
            ConfigFiles[GENGPIOLEDBLINK_CONFIG].ReadValue(
                "ledpin", return_type=int, default=12
            ),
            "int",
            "GPIO pin number that an LED is connected (valid numbers are 0 - 27)",
            bounds="required digits range:0:27",
            display_name="GPIO LED pin",
        )

        # GENLOG
        AddOnCfg["genlog"] = collections.OrderedDict()
        AddOnCfg["genlog"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genlog", default=False
        )
        AddOnCfg["genlog"]["title"] = "Notifications to CSV Log"
        AddOnCfg["genlog"][
            "description"
        ] = "Log Genmon and utility state changes to a file. Log file is in text CSV format."
        AddOnCfg["genlog"]["icon"] = "csv"
        AddOnCfg["genlog"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genlogpy-optional"
        AddOnCfg["genlog"]["parameters"] = collections.OrderedDict()
        Args = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "args",
            return_type=str,
            section="genlog",
            default="-f /home/pi/genmon/LogFile.csv",
        )
        ArgList = Args.split()
        if len(ArgList) == 2:
            Value = ArgList[1]
        else:
            Value = ""
        AddOnCfg["genlog"]["parameters"]["Log File Name"] = CreateAddOnParam(
            Value,
            "string",
            "Filename for log. Full path of the file must be included (i.e. /home/pi/genmon/LogFile.csv)",
            bounds="required UnixFile",
            display_name="Log File Name",
        )

        # GENSMS
        AddOnCfg["gensms"] = collections.OrderedDict()
        AddOnCfg["gensms"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms", default=False
        )
        AddOnCfg["gensms"]["title"] = "Notifications via SMS - Twilio"
        AddOnCfg["gensms"][
            "description"
        ] = "Send Genmon and utility state changes via Twilio SMS"
        AddOnCfg["gensms"]["icon"] = "twilio"
        AddOnCfg["gensms"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensmspy-optional"
        AddOnCfg["gensms"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms"]["parameters"]["accountsid"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "accountsid", return_type=str, default=""
            ),
            "string",
            "Twilio account SID. This can be obtained from a valid Twilio account",
            bounds="required minmax:10:50",
            display_name="Twilio Account SID",
        )
        AddOnCfg["gensms"]["parameters"]["authtoken"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "authtoken", return_type=str, default=""
            ),
            "string",
            "Twilio authentication token. This can be obtained from a valid Twilio account",
            bounds="required minmax:10:50",
            display_name="Twilio Authentication Token",
        )
        AddOnCfg["gensms"]["parameters"]["to_number"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "to_number", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        AddOnCfg["gensms"]["parameters"]["from_number"] = CreateAddOnParam(
            ConfigFiles[GENSMS_CONFIG].ReadValue(
                "from_number", return_type=str, default=""
            ),
            "string",
            "Number to send SMS message from. This should be a twilio phone number.",
            bounds="required InternationalPhone",
            display_name="Twilio Phone Number",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gensms", GENSMS_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "gensms", GENSMS_CONFIG)

        # GENSMS_VOIP
        Description = "SMS Support vis VoIP using voip.ms"
        try:
            import voipms
        except Exception as e1:
            Description = (
                Description
                + "<br/><font color='red'>The required libraries for this add on are not installed, please run the installation script.</font>"
            )

        AddOnCfg["gensms_voip"] = collections.OrderedDict()
        AddOnCfg["gensms_voip"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms_voip", default=False
        )
        AddOnCfg["gensms_voip"]["title"] = "SMS via VoIP using voip.ms"

        AddOnCfg["gensms_voip"]["description"] = Description
        AddOnCfg["gensms_voip"]["icon"] = "voipms"
        AddOnCfg["gensms_voip"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_voippy-optional"
        AddOnCfg["gensms_voip"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms_voip"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Voip.ms account username",
            bounds="required minmax:5:50",
            display_name="VoIP.ms User Name",
        )
        AddOnCfg["gensms_voip"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "VoIP.ms API password. This is NOT the account login, but rather then API password",
            bounds="required minmax:8:50",
            display_name="VoIP.ms API password",
        )
        AddOnCfg["gensms_voip"]["parameters"]["did"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "did", return_type=str, default=""
            ),
            "string",
            "DID number for your voip.ms account to send the SMS.",
            bounds="required InternationalPhone",
            display_name="Sender DID Number",
        )
        AddOnCfg["gensms_voip"]["parameters"]["destination"] = CreateAddOnParam(
            ConfigFiles[GENSMS_VOIP_CONFIG].ReadValue(
                "destination", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message to. This can be any mobile number. Separate multilpe recipients with commas.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        # GENSMS_MODEM
        AddOnCfg["gensms_modem"] = collections.OrderedDict()
        AddOnCfg["gensms_modem"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensms_modem", default=False
        )
        AddOnCfg["gensms_modem"]["title"] = "Notifications via SMS - LTE Hat"
        AddOnCfg["gensms_modem"][
            "description"
        ] = "Send Genmon and utility state changes via cellular SMS (additional hardware required)"
        AddOnCfg["gensms_modem"]["icon"] = "sms"
        AddOnCfg["gensms_modem"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensms_modempy-optional"
        AddOnCfg["gensms_modem"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensms_modem"]["parameters"]["recipient"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "recipient", return_type=str, default=""
            ),
            "string",
            "Mobile number to send SMS message. This can be any mobile number. No dashes or spaces.",
            bounds="required InternationalPhone",
            display_name="Recipient Phone Number",
        )
        AddOnCfg["gensms_modem"]["parameters"]["port"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue("port", return_type=str, default=""),
            "string",
            "This is the serial device to send AT modem commands. This *must* be different from the serial port used by the generator monitor software.",
            bounds="required UnixDevice",
            display_name="Modem Serial Port",
        )

        AddOnCfg["gensms_modem"]["parameters"]["rate"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "rate", return_type=int, default=115200
            ),
            "int",
            "The baud rate for the port. Use 115200 for the LTEPiHat.",
            bounds="required digits",
            display_name="Modem Serial Rate",
        )
        AddOnCfg["gensms_modem"]["parameters"]["log_at_commands"] = CreateAddOnParam(
            ConfigFiles[MYMODEM_CONFIG].ReadValue(
                "log_at_commands", return_type=bool, default=False
            ),
            "boolean",
            "Enable to log at commands to the log file.",
            display_name="Log AT Commands",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gensms_modem", MYMODEM_CONFIG)

        # modem type - select the type of modem used. For future use. Presently "LTEPiHat" is the only option
        # modem_type = LTEPiHat

        # GENPUSHOVER
        AddOnCfg["genpushover"] = collections.OrderedDict()
        AddOnCfg["genpushover"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genpushover", default=False
        )
        AddOnCfg["genpushover"]["title"] = "Notifications via Pushover"
        AddOnCfg["genpushover"][
            "description"
        ] = "Send Genmon and utility state changes via Pushover service"
        AddOnCfg["genpushover"]["icon"] = "pushover"
        AddOnCfg["genpushover"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genpushoverpy-optional"
        AddOnCfg["genpushover"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genpushover"]["parameters"]["appid"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "appid", return_type=str, default=""
            ),
            "string",
            "Pushover app ID. This is generated by pushover.net when an application is created for your account.",
            bounds="required minmax:30:30",
            display_name="Application ID",
        )
        AddOnCfg["genpushover"]["parameters"]["userid"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "userid", return_type=str, default=""
            ),
            "string",
            "Pushover User Key. Note: this is not your login user name but a key generated by pushover.net for your account",
            bounds="required minmax:30:30",
            display_name="Pushover User Key",
        )
        AddOnCfg["genpushover"]["parameters"]["pushsound"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "pushsound", return_type=str, default="updown"
            ),
            "string",
            "Notification sound identifier. See https://pushover.net/api#sounds for a full list of sound IDs. All sounds must be lower case.",
            bounds="minmax:3:20",
            display_name="Push Sound",
        )
        AddOnCfg["genpushover"]["parameters"]["alarm_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "alarm_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Alarm Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Alarm Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["sw_update_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "sw_update_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Software Update Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Software Update Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "system_health_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "system_health_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "System Health Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="System Health Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["fuel_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "fuel_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Fuel Level Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Fuel Level Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["outage_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "outage_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Fuel Level Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Outage Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "switch_state_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "switch_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Switch State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Switch State Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["run_state_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "run_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Run State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Run State Priority",
        )
        AddOnCfg["genpushover"]["parameters"][
            "service_state_priority"
        ] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "service_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Service State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Service State Priority",
        )
        AddOnCfg["genpushover"]["parameters"]["pi_state_priority"] = CreateAddOnParam(
            ConfigFiles[GENPUSHOVER_CONFIG].ReadValue(
                "pi_state_priority", return_type=str, default="NORMAL"
            ),
            "list",
            "Pi Hardware Sensor State Notification priority identifier. See https://pushover.net/api#priority",
            bounds="LOWEST,LOW,NORMAL,HIGH,EMERGENCY",
            display_name="Pi Hardware Sensor State Priority",
        )

        AddOnCfg = AddNotificationAddOnParam(
            AddOnCfg, "genpushover", GENPUSHOVER_CONFIG
        )
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "genpushover", GENPUSHOVER_CONFIG)

        # GENSYSLOG
        AddOnCfg["gensyslog"] = collections.OrderedDict()
        AddOnCfg["gensyslog"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensyslog", default=False
        )
        AddOnCfg["gensyslog"]["title"] = "Linux System Logging"
        AddOnCfg["gensyslog"][
            "description"
        ] = "Write generator and utility state changes to system log (/var/log/syslog)"
        AddOnCfg["gensyslog"]["icon"] = "linux"
        AddOnCfg["gensyslog"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensyslogpy-optional"
        AddOnCfg["gensyslog"]["parameters"] = None

        # GENMQTT
        AddOnCfg["genmqtt"] = collections.OrderedDict()
        AddOnCfg["genmqtt"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genmqtt", default=False
        )
        AddOnCfg["genmqtt"]["title"] = "MQTT integration"
        AddOnCfg["genmqtt"][
            "description"
        ] = "Export Genmon data and status to MQTT server for automation integration"
        AddOnCfg["genmqtt"]["icon"] = "mqtt"
        AddOnCfg["genmqtt"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmqttpy-optional"
        AddOnCfg["genmqtt"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genmqtt"]["parameters"]["mqtt_address"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "mqtt_address", return_type=str, default=""
            ),
            "string",
            "Address of your MQTT server.",
            bounds="required InternetAddress",
            display_name="MQTT Server Address",
        )
        AddOnCfg["genmqtt"]["parameters"]["mqtt_port"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "mqtt_port", return_type=int, default=1833
            ),
            "int",
            "The port of the MQTT server in a decimal number.",
            bounds="required digits",
            display_name="MQTT Server Port Number",
        )
        AddOnCfg["genmqtt"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Username",
        )
        AddOnCfg["genmqtt"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Password",
        )
        AddOnCfg["genmqtt"]["parameters"]["poll_interval"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "poll_interval", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["genmqtt"]["parameters"]["root_topic"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "root_topic", return_type=str, default=""
            ),
            "string",
            "(Optional) Prepend this value to the MQTT data path i.e. 'Home' would result in 'Home/generator/...''",
            bounds="minmax:1:50",
            display_name="Root Topic",
        )
        AddOnCfg["genmqtt"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "blacklist", return_type=str, default=""
            ),
            "string",
            "(Optional) Names of data not exported to the MQTT server, separated by commas.",
            bounds="",
            display_name="Blacklist Filter",
        )
        AddOnCfg["genmqtt"]["parameters"]["flush_interval"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "flush_interval", return_type=float, default=0
            ),
            "float",
            "(Optional) Time in seconds where even unchanged values will be published to their MQTT topic. Set to zero to disable flushing.",
            bounds="number",
            display_name="Flush Interval",
        )
        AddOnCfg["genmqtt"]["parameters"]["numeric_json"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "numeric_json", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return numeric values in the Status, Maintenance and Outage topics as separate topics for unit, type and value.",
            bounds="",
            display_name="Numeric Topics",
        )
        AddOnCfg["genmqtt"]["parameters"]["numeric_json_object"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "numeric_json_object", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return a JSON object for numeric values in the Status, Maintenance and Outage topics as an object with unit, type and value members.",
            bounds="",
            display_name="JSON for Numerics",
        )
        AddOnCfg["genmqtt"]["parameters"]["strlist_json"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "strlist_json", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return a JSON list for any list of strings like the Outage log. Does not apply if JSON for Numerics is enabled.",
            bounds="",
            display_name="JSON for String Lists",
        )
        AddOnCfg["genmqtt"]["parameters"]["remove_spaces"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "remove_spaces", return_type=bool, default=False
            ),
            "boolean",
            "If enabled any spaces in the topic path will be converted to underscores",
            bounds="",
            display_name="Remove Spaces in Topic Path",
        )
        AddOnCfg["genmqtt"]["parameters"]["retain"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "retain", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, published messages will be retained by the MQTT broker server after a the Add On disconnects from the server.",
            bounds="",
            display_name="Retain Data",
        )
        AddOnCfg["genmqtt"]["parameters"]["cert_authority_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "cert_authority_path", return_type=str, default=""
            ),
            "string",
            "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
            bounds="",
            display_name="SSL/TLS CA certificate file",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_cert_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_cert_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Certificate File",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_key_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_key_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client key file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Key File",
        )
        AddOnCfg["genmqtt"]["parameters"]["tls_version"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "tls_version", return_type=str, default="1.0"
            ),
            "list",
            "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
            bounds="1.0,1.1,1.2",
            display_name="TLS Version",
        )
        AddOnCfg["genmqtt"]["parameters"]["cert_reqs"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "cert_reqs", return_type=str, default="Required"
            ),
            "list",
            "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
            bounds="None,Optional,Required",
            display_name="Certificate Requirements",
        )
        AddOnCfg["genmqtt"]["parameters"]["client_id"] = CreateAddOnParam(
            ConfigFiles[GENMQTT_CONFIG].ReadValue(
                "client_id", return_type=str, default="genmon"
            ),
            "string",
            "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
            bounds="",
            display_name="Client ID",
        )

        # GENMQTTIN
        AddOnCfg["genmqttin"] = collections.OrderedDict()
        AddOnCfg["genmqttin"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genmqttin", default=False
        )
        AddOnCfg["genmqttin"]["title"] = "MQTT Sensor Input"
        AddOnCfg["genmqttin"][
            "description"
        ] = "Import data from MQTT broker for genmon use"
        AddOnCfg["genmqttin"]["icon"] = "mqtt"
        AddOnCfg["genmqttin"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmqttinpy-optional"
        AddOnCfg["genmqttin"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genmqttin"]["parameters"]["topics"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "topics", return_type=str, default=""
            ),
            "string",
            "Comma separated list of MQTT topics to subscribe and import into genmon. All topics must return a numeric value or a string representation of a numeric value.",
            bounds="",
            display_name="Topics",
        )
        AddOnCfg["genmqttin"]["parameters"]["labels"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "labels", return_type=str, default=""
            ),
            "string",
            "Comma separated list of display names for each topic listed above. These will be the displayed label for each topic value.",
            bounds="",
            display_name="Displayed Name",
        )
        AddOnCfg["genmqttin"]["parameters"]["units"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "units", return_type=str, default=""
            ),
            "string",
            "Comma separated list of units for each topic listed above. If no labled is used for a given topic, use a space. If using the imported MQTT data for genmon calculations, for power use W or kW, for current use A, for voltage use V. ",
            bounds="",
            display_name="Units",
        )
        AddOnCfg["genmqttin"]["parameters"]["types"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "types", return_type=str, default=""
            ),
            "string",
            "Comma separated list of value types for each topic listed above. Valid types are: ct1,ct2,ctpower1,ctpower2,fuel,temperature,power,current,voltage or pressure. See the wiki entry for this add on for more details.",
            bounds="",
            display_name="Sensor Type",
        )
        AddOnCfg["genmqttin"]["parameters"]["exclude_gauge"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "exclude_gauge", return_type=str, default=""
            ),
            "string",
            "Comma separated list of Displayed Names that will not be displayed as a gauge. If you enable 'Use Data for Calculations' then you can remove duplicate gagues with this setting if they show up in the user interface.",
            bounds="",
            display_name="Exclude Gauge",
        )
        AddOnCfg["genmqttin"]["parameters"]["nominal_values"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "nominal_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of nominal values for each topic listed above.",
            bounds="",
            display_name="Nominal Values",
        )
        AddOnCfg["genmqttin"]["parameters"]["maximum_values"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "maximum_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of maximum values for each topic listed above.",
            bounds="",
            display_name="Maximum Values",
        )

        AddOnCfg["genmqttin"]["parameters"]["use_for_power_fuel"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "use_for_power_fuel", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, the data from sensor types fuel,power,current,ct1,ct2,voltageleg1, voltageleg2, ctpower1 and ctpower2 will be imported and used for power and fuel calculations (instead of just displaying) within genmon.",
            bounds="",
            display_name="Use Data for Calculations",
        )
        AddOnCfg["genmqttin"]["parameters"]["strict"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "strict", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, genmon will only use Data for Calculations if the generator utility line is in an outage. If your sensors are connected after the transfer switch (i.e. utility and generator are monitored) the you will want to enable this setting to keep genmon from using the sensor readings when there is not an outage.",
            bounds="",
            display_name="Strict Import Rules",
        )
        AddOnCfg["genmqttin"]["parameters"]["mqtt_address"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "mqtt_address", return_type=str, default=""
            ),
            "string",
            "Address of your MQTT server.",
            bounds="required InternetAddress",
            display_name="MQTT Server Address",
        )
        AddOnCfg["genmqttin"]["parameters"]["mqtt_port"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "mqtt_port", return_type=int, default=1833
            ),
            "int",
            "The port of the MQTT server in a decimal number.",
            bounds="required digits",
            display_name="MQTT Server Port Number",
        )
        AddOnCfg["genmqttin"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "This value is used for the username if your MQTT server requires authentication. Leave blank for no authentication.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Username",
        )
        AddOnCfg["genmqttin"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "This value is used for the password if your MQTT server requires authentication. Leave blank for no authentication or no password.",
            bounds="minmax:4:50",
            display_name="MQTT Authentication Password",
        )
        AddOnCfg["genmqttin"]["parameters"]["cert_authority_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "cert_authority_path", return_type=str, default=""
            ),
            "string",
            "(Optional) Full path to Certificate Authority file. Leave empty to not use SSL/TLS. If used port will be forced to 8883.",
            bounds="",
            display_name="SSL/TLS CA certificate file",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_cert_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_cert_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client certificate file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Certificate File",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_key_path"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_key_path", return_type=str, default=""
            ),
            "string",
            "Optional. Full path the client key file. Leave empty to not use MTLS.",
            bounds="",
            display_name="Client Key File",
        )
        AddOnCfg["genmqttin"]["parameters"]["tls_version"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "tls_version", return_type=str, default="1.0"
            ),
            "list",
            "(Optional) TLS version used (integer). Default is 1.0. Must be 1.0, 1.1, or 1.2. This is ignored if a CA cert file is not used. ",
            bounds="1.0,1.1,1.2",
            display_name="TLS Version",
        )
        AddOnCfg["genmqttin"]["parameters"]["cert_reqs"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "cert_reqs", return_type=str, default="Required"
            ),
            "list",
            "(Optional) Defines the certificate requirements that the client imposes on the broker. Used if Certificate Authority file is used.",
            bounds="None,Optional,Required",
            display_name="Certificate Requirements",
        )
        AddOnCfg["genmqttin"]["parameters"]["client_id"] = CreateAddOnParam(
            ConfigFiles[GENMQTTIN_CONFIG].ReadValue(
                "client_id", return_type=str, default="genmon"
            ),
            "string",
            "Unique identifier. Must be unique for each instance of genmon and add on running on a given system. ",
            bounds="",
            display_name="Client ID",
        )
        # GENHOMEASSISTANT
        AddOnCfg["genhomeassistant"] = collections.OrderedDict()
        AddOnCfg["genhomeassistant"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genhomeassistant", default=False
        )
        AddOnCfg["genhomeassistant"]["title"] = "Home Assistant MQTT Discovery"
        AddOnCfg["genhomeassistant"][
            "description"
        ] = "Publish MQTT auto-discovery messages for Home Assistant integration"
        AddOnCfg["genhomeassistant"]["icon"] = "homeassistant"
        AddOnCfg["genhomeassistant"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genhomeassistantpy-optional"
        AddOnCfg["genhomeassistant"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genhomeassistant"]["parameters"]["mqtt_address"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "mqtt_address", return_type=str, default=""
            ),
            "string",
            "Address of your MQTT broker server (IP address or hostname).",
            bounds="required InternetAddress",
            display_name="MQTT Server Address",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["mqtt_port"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "mqtt_port", return_type=int, default=1883
            ),
            "int",
            "Port of the MQTT broker. Default is 1883 (or 8883 for TLS).",
            bounds="required digits",
            display_name="MQTT Port",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Username for MQTT broker authentication (leave empty if not required).",
            bounds="minmax:4:50",
            display_name="Username",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "Password for MQTT broker authentication (leave empty if not required).",
            bounds="",
            display_name="Password",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["discovery_prefix"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "discovery_prefix", return_type=str, default="homeassistant"
            ),
            "string",
            "Home Assistant MQTT discovery prefix. Default is 'homeassistant'. Only change if you configured a different prefix in HA.",
            bounds="",
            display_name="Discovery Prefix",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["base_topic"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "base_topic", return_type=str, default="genmon"
            ),
            "string",
            "Base topic for state and command messages. Default is 'genmon'.",
            bounds="",
            display_name="Base Topic",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["device_id"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "device_id", return_type=str, default="generator"
            ),
            "string",
            "Unique device identifier used in entity IDs. Change if running multiple genmon instances.",
            bounds="",
            display_name="Device ID",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["device_name"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "device_name", return_type=str, default="Generator"
            ),
            "string",
            "Friendly device name shown in Home Assistant.",
            bounds="",
            display_name="Device Name",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["poll_interval"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "poll_interval", return_type=float, default=3.0
            ),
            "int",
            "Interval in seconds between polling genmon for status updates. Default is 3.",
            bounds="",
            display_name="Poll Interval",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["discovery_interval"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "discovery_interval", return_type=int, default=300
            ),
            "int",
            "Interval in seconds to republish discovery messages. Set to 0 to only publish on startup. Default is 300.",
            bounds="",
            display_name="Discovery Interval",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "blacklist", return_type=str, default="Tiles"
            ),
            "string",
            "Comma-separated list of strings. Entities with names containing these strings will not be created. Matches against entity name, ID, and data path.",
            bounds="",
            display_name="Entity Blacklist",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["include_monitor_stats"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "include_monitor_stats", return_type=bool, default=True
            ),
            "boolean",
            "Include platform/monitor statistics (CPU, memory, etc.) as entities.",
            bounds="",
            display_name="Include Monitor Stats",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["include_weather"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "include_weather", return_type=bool, default=True
            ),
            "boolean",
            "Include weather data entities if weather is configured in genmon.",
            bounds="",
            display_name="Include Weather",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["include_logs"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "include_logs", return_type=bool, default=False
            ),
            "boolean",
            "Include log entries as sensor attributes.",
            bounds="",
            display_name="Include Logs",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["numeric_json"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "numeric_json", return_type=bool, default=True
            ),
            "boolean",
            "Use numeric JSON format when querying genmon (cleaner values without embedded units).",
            bounds="",
            display_name="Use Numeric JSON",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["monitor_address"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "monitor_address", return_type=str, default=""
            ),
            "string",
            "IP address of genmon if running on a different system. Leave empty for localhost.",
            bounds="InternetAddress",
            display_name="Genmon Address",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["cert_authority_path"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "cert_authority_path", return_type=str, default=""
            ),
            "string",
            "Full path to Certificate Authority file. Leave empty to not use SSL/TLS.",
            bounds="",
            display_name="CA Certificate Path",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["tls_version"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "tls_version", return_type=str, default="1.2"
            ),
            "list",
            "TLS version to use. Default is 1.2. Ignored if CA certificate is not used.",
            bounds="1.0,1.1,1.2",
            display_name="TLS Version",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["cert_reqs"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "cert_reqs", return_type=str, default="Required"
            ),
            "list",
            "Certificate requirements that the client imposes on the broker.",
            bounds="None,Optional,Required",
            display_name="Certificate Requirements",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["client_cert_path"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "client_cert_path", return_type=str, default=""
            ),
            "string",
            "Full path to client certificate file for MTLS.",
            bounds="",
            display_name="Client Certificate Path",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["client_key_path"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "client_key_path", return_type=str, default=""
            ),
            "string",
            "Full path to client key file for MTLS.",
            bounds="",
            display_name="Client Key Path",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["client_id"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "client_id", return_type=str, default="genmon_ha"
            ),
            "string",
            "Unique MQTT client identifier. Must be unique per genmon instance.",
            bounds="",
            display_name="Client ID",
        )
        AddOnCfg["genhomeassistant"]["parameters"]["button_passcode"] = CreateAddOnParam(
            ConfigFiles[GENHOMEASSISTANT_CONFIG].ReadValue(
                "button_passcode", return_type=str, default=""
            ),
            "password",
            "Passcode for controllers that require authentication for remote commands (e.g. MEBAY). Leave empty if not required.",
            bounds="",
            display_name="Button Passcode",
        )
        # GENSLACK
        AddOnCfg["genslack"] = collections.OrderedDict()
        AddOnCfg["genslack"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genslack", default=False
        )
        AddOnCfg["genslack"]["title"] = "Notifications via Slack"
        AddOnCfg["genslack"][
            "description"
        ] = "Send Genmon and utility state changes via Slack service"
        AddOnCfg["genslack"]["icon"] = "slack"
        AddOnCfg["genslack"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genslackpy-optional"
        AddOnCfg["genslack"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genslack"]["parameters"]["webhook_url"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "webhook_url", return_type=str, default=""
            ),
            "string",
            "Full Slack Webhook URL. Retrieve from Slack custom integration configuration.",
            bounds="required HTTPAddress",
            display_name="Web Hook URL",
        )
        AddOnCfg["genslack"]["parameters"]["channel"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "channel", return_type=str, default=""
            ),
            "string",
            "Slack channel to which the message will be sent.",
            display_name="Channel",
        )
        AddOnCfg["genslack"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Slack username.",
            bounds="required username",
            display_name="Username",
        )
        AddOnCfg["genslack"]["parameters"]["icon_emoji"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "icon_emoji", return_type=str, default=":red_circle:"
            ),
            "string",
            "Emoji that appears as the icon of the user who sent the message i.e. :red_circle:n",
            bounds="",
            display_name="Icon Emoji",
        )
        AddOnCfg["genslack"]["parameters"]["title_link"] = CreateAddOnParam(
            ConfigFiles[GENSLACK_CONFIG].ReadValue(
                "title_link", return_type=str, default=""
            ),
            "string",
            "Use this to make the title of the message a link i.e. link to the genmon web interface.",
            bounds="HTTPAddress",
            display_name="Title Link",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "genslack", GENSLACK_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "genslack", GENSLACK_CONFIG)

        # GENCALLMEBOT
        AddOnCfg["gencallmebot"] = collections.OrderedDict()
        AddOnCfg["gencallmebot"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencallmebot", default=False
        )
        AddOnCfg["gencallmebot"]["title"] = "Notifications via CallMeBot"
        AddOnCfg["gencallmebot"][
            "description"
        ] = "Send Genmon and utility state changes via CallMeBot service"
        AddOnCfg["gencallmebot"]["icon"] = "callmebot"
        AddOnCfg["gencallmebot"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencallmebotpy-optional"
        AddOnCfg["gencallmebot"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencallmebot"]["parameters"]["notification_type"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "notification_type", return_type=str, default=""
            ),
            "list",
            "Type of CallMeBot Notifications. For more information, see http://www.callmebot.com.",
            bounds="WhatsApp,Telegram,Signal",  # Facebook, 
            display_name="Notification Type",
        )
        AddOnCfg["gencallmebot"]["parameters"]["api_key"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "api_key", return_type=str, default=""
            ),
            "string",
            "API Key required for WhatsApp Notifications.", # and Facebook Messanger, Signal 
            display_name="API Key",
        )
        AddOnCfg["gencallmebot"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "CallMeBot username required for Telegram Notifications.",
            bounds="required username",
            display_name="Username",
        )
        AddOnCfg["gencallmebot"]["parameters"]["recipient_number"] = CreateAddOnParam(
            ConfigFiles[GENCALLMEBOT_CONFIG].ReadValue(
                "recipient_number", return_type=str, default="+1XXXXXXXXXX"
            ),
            "string",
            "Recipient Number requried for WhatsApp Notification. Must be without spaces and start with a plus. For Signal this must be the numeric key sent to your signal account when registering with CallMeBot (in the form xxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx)",
            bounds="",
            display_name="Recipient Number",
        )

        AddOnCfg = AddNotificationAddOnParam(AddOnCfg, "gencallmebot", GENCALLMEBOT_CONFIG)
        AddOnCfg = AddRetryAddOnParam(AddOnCfg, "gencallmebot", GENCALLMEBOT_CONFIG)

        # GENEXERCISE
        ControllerInfo = GetControllerInfo("controller").lower()
        if "evolution" in ControllerInfo or "nexus" in ControllerInfo:
            AddOnCfg["genexercise"] = collections.OrderedDict()
            AddOnCfg["genexercise"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genexercise", default=False
            )
            AddOnCfg["genexercise"]["title"] = "Enhanced Exercise"
            AddOnCfg["genexercise"][
                "description"
            ] = "Add additional exercise cycles with new functionality for Evolution/Nexus Controllers"
            AddOnCfg["genexercise"]["icon"] = "selftest"
            AddOnCfg["genexercise"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genexercisepy-optional"
            AddOnCfg["genexercise"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genexercise"]["parameters"]["exercise_type"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_type", return_type=str, default="Normal"
                ),
                "list",
                "Quiet Exercise (reduced RPM, Hz and Voltage), Normal Exercise, Exercise with Transfer Switch Activated.",
                bounds="Quiet,Normal,Transfer",
                display_name="Exercise Type",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_frequency"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_frequency", return_type=str, default="Monthly"
                ),
                "list",
                "Exercise Frequency options are Daily, Weekly, Biweekly,Monthly  or Post-Controller (immediately after the controller exercise cycle). Hour, Minute, Month, Day of Week are ignored if Post-Controller exercise frequency is enabled.",
                bounds="Daily,Weekly,Biweekly,Monthly,Post-Controller",
                display_name="Exercise Frequency",
            )
            AddOnCfg["genexercise"]["parameters"]["use_gen_time"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "use_gen_time", return_type=bool, default=False
                ),
                "boolean",
                "Enable to use the generator time for the exercise cycle, otherwise it will use the system time.",
                display_name="Use Generator Time",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_hour"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_hour", return_type=int, default=12
                ),
                "int",
                "The hour of the exercise time. Valid input is 0 - 23.",
                bounds="required digits range:0:23",
                display_name="Exercise Time Hour",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_minute"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_minute", return_type=int, default=0
                ),
                "int",
                "The minute of the exercise time.  Valid input is 0 - 59",
                bounds="required digits range:0:59",
                display_name="Exercise Time Minute",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_day_of_month"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_day_of_month", return_type=int, default=1
                ),
                "int",
                "The day of month if monthly exercise is selected.",
                bounds="required digits range:1:28",
                display_name="Exercise Day of Month",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_day_of_week"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_day_of_week", return_type=str, default="Monday"
                ),
                "list",
                "Exercise day of the week, if Weekly or Biweekly exercise frequency is selected.",
                bounds="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday,Sunday",
                display_name="Exercise Day of the Week",
            )
            AddOnCfg["genexercise"]["parameters"][
                "exercise_duration"
            ] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_duration", return_type=float, default=12
                ),
                "float",
                "The duration of the exercise time. Note: this time does not include warmup time for Transfer type exercise cycles.",
                bounds="number range:5:60",
                display_name="Exercise Duration",
            )
            AddOnCfg["genexercise"]["parameters"]["exercise_warmup"] = CreateAddOnParam(
                ConfigFiles[GENEXERCISE_CONFIG].ReadValue(
                    "exercise_warmup", return_type=float, default=0
                ),
                "float",
                "The duration of the warmup time. Note: this time only appies to the transfer type of exercise cycle. Zero will disable the warmup period.",
                bounds="number range:0:30",
                display_name="Warmup Duration",
            )

        # GENEMAIL2SMS
        AddOnCfg["genemail2sms"] = collections.OrderedDict()
        AddOnCfg["genemail2sms"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genemail2sms", default=False
        )
        AddOnCfg["genemail2sms"]["title"] = "Mobile Carrier Email to SMS"
        AddOnCfg["genemail2sms"][
            "description"
        ] = "Send Genmon and utility state changes via carrier email to SMS service"
        AddOnCfg["genemail2sms"]["icon"] = "text"
        AddOnCfg["genemail2sms"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genemail2smspy-optional"
        AddOnCfg["genemail2sms"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genemail2sms"]["parameters"]["destination"] = CreateAddOnParam(
            ConfigFiles[GENEMAIL2SMS_CONFIG].ReadValue(
                "destination", return_type=str, default=""
            ),
            "string",
            "Email to SMS email recipient. Must be a valid email address",
            bounds="required email",
            display_name="Email to SMS address",
        )

        AddOnCfg = AddNotificationAddOnParam(
            AddOnCfg, "genemail2sms", GENEMAIL2SMS_CONFIG
        )

        # GENCENTRICONNECT
        AddOnCfg["gencentriconnect"] = collections.OrderedDict()
        AddOnCfg["gencentriconnect"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencentriconnect", default=False
        )
        AddOnCfg["gencentriconnect"]["title"] = "Centri My Propane External Tank Fuel Monitor"
        AddOnCfg["gencentriconnect"][
            "description"
        ] = "Integrates Centriconnect.com propane tank sensor data"
        AddOnCfg["gencentriconnect"]["icon"] = "centri"
        AddOnCfg["gencentriconnect"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencentriconnectpy-optional"
        AddOnCfg["gencentriconnect"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencentriconnect"]["parameters"]["user_id"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "user_id", return_type=str, default=""
            ),
            "string",
            "User ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
            bounds="required min:36",
            display_name="User ID",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["device_id"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "device_id", return_type=str, default=""
            ),
            "string",
            "Device ID. Note that this is a long series of numbers and dashes in this format: 36e551aa-c215-4c9b-8c70-ba7729687654",
            bounds="required min:36",
            display_name="Device ID",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["device_auth"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "device_auth", return_type=str, default=""
            ),
            "password",
            "Device Auth for Centri propane tank sensor. This number is provided in the box with the sensor.",
            bounds="required min:6",
            display_name="Device Authentication Code",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "int",
            "The duration in minutes between poll of tank data. Note this must be equal or larger than 288 minutes as the maximum number of polls per day is around 5.",
            bounds="number range:288:20000",
            display_name="Poll Frequency",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["check_battery"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "check_battery", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check Sensor Battery",
        )
        AddOnCfg["gencentriconnect"]["parameters"]["check_reading"] = CreateAddOnParam(
            ConfigFiles[GENCENTRICONNECT_CONFIG].ReadValue(
                "check_reading", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check for Missed Readings",
        )

        # GENTANKUTIL
        AddOnCfg["gentankutil"] = collections.OrderedDict()
        AddOnCfg["gentankutil"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentankutil", default=False
        )
        AddOnCfg["gentankutil"]["title"] = "External Tank Fuel Monitor"
        AddOnCfg["gentankutil"][
            "description"
        ] = "Integrates tankutility.com propane tank sensor data"
        AddOnCfg["gentankutil"]["icon"] = "tankutility"
        AddOnCfg["gentankutil"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentankutilpy-optional"
        AddOnCfg["gentankutil"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentankutil"]["parameters"]["tank_name"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "tank_name", return_type=str, default=""
            ),
            "string",
            "Tank name as defined in tankutility.com",
            bounds="minmax:1:50",
            display_name="Tank Name",
        )
        AddOnCfg["gentankutil"]["parameters"]["tank_name_2"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "tank_name_2", return_type=str, default=""
            ),
            "string",
            "Second tank name, if applicable",
            bounds="minmax:1:50",
            display_name="Tank Name 2 (Optional)",
        )
        AddOnCfg["gentankutil"]["parameters"]["username"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "username", return_type=str, default=""
            ),
            "string",
            "Username at tankutility.com",
            bounds="required email",
            display_name="Username",
        )
        AddOnCfg["gentankutil"]["parameters"]["password"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "password", return_type=str, default=""
            ),
            "password",
            "Password at tankutility.com",
            bounds="minmax:4:50",
            display_name="Password",
        )
        AddOnCfg["gentankutil"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "float",
            "The duration in minutes between poll of tank data.",
            bounds="number",
            display_name="Poll Frequency",
        )
        AddOnCfg["gentankutil"]["parameters"]["check_battery"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "check_battery", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the battery level on the sensor is critical. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check Sensor Battery",
        )
        AddOnCfg["gentankutil"]["parameters"]["check_reading"] = CreateAddOnParam(
            ConfigFiles[GENTANKUTIL_CONFIG].ReadValue(
                "check_reading", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, and email will be sent if the sensor has not performed a reading within 50 hours. Outbound email must be enabled for this to function.",
            bounds="",
            display_name="Check for Missed Readings",
        )

        # GENTANKDIY
        AddOnCfg["gentankdiy"] = collections.OrderedDict()
        AddOnCfg["gentankdiy"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentankdiy", default=False
        )
        AddOnCfg["gentankdiy"]["title"] = "DIY Fuel Tank Gauge Sensor"
        Description = "Integrates DIY tank gauge sensor for Genmon"
        if (
            os.path.exists("/dev/i2c-1") == False
            and os.path.exists("/dev/i2c-2") == False
        ):
            Description = (
                Description
                + "<br/><font color='red'>The I2C bus not enabled but required for this add-on to function.</font>"
            )
        AddOnCfg["gentankdiy"]["description"] = Description
        AddOnCfg["gentankdiy"]["icon"] = "rpi"
        AddOnCfg["gentankdiy"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentankdiypy-optional"
        AddOnCfg["gentankdiy"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentankdiy"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTANKDIY_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=0
            ),
            "float",
            "The duration in minutes between poll of tank data.",
            bounds="number",
            display_name="Poll Frequency",
        )
        AddOnCfg["gentankdiy"]["parameters"]["gauge_type"] = CreateAddOnParam(
            ConfigFiles[GENTANKDIY_CONFIG].ReadValue(
                "gauge_type", return_type=str, default="1"
            ),
            "list",
            "DIY sensor type. Valid options are Type 1 and Type 2.",
            bounds="1,2",
            display_name="Sensor Type",
        )

        # GENALEXA
        AddOnCfg["genalexa"] = collections.OrderedDict()
        AddOnCfg["genalexa"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genalexa", default=False
        )
        AddOnCfg["genalexa"]["title"] = "Amazon Alexa voice commands"
        AddOnCfg["genalexa"][
            "description"
        ] = "Allow Amazon Alexa to start and stop the generator"
        AddOnCfg["genalexa"]["icon"] = "alexa"
        AddOnCfg["genalexa"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genalexapy-optional"
        AddOnCfg["genalexa"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genalexa"]["parameters"]["name"] = CreateAddOnParam(
            ConfigFiles[GENALEXA_CONFIG].ReadValue("name", return_type=str, default=""),
            "string",
            "Name to call the generator device, i.e. 'generator'",
            bounds="minmax:4:50",
            display_name="Name for generator device",
        )

        # GENSNMP
        AddOnCfg["gensnmp"] = collections.OrderedDict()
        AddOnCfg["gensnmp"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gensnmp", default=False
        )
        AddOnCfg["gensnmp"]["title"] = "SNMP Support"
        AddOnCfg["gensnmp"]["description"] = "Allow Genmon to respond to SNMP requests"
        AddOnCfg["gensnmp"]["icon"] = "snmp"
        AddOnCfg["gensnmp"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gensnmppy-optional"
        AddOnCfg["gensnmp"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gensnmp"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds between requesting status from genmon. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gensnmp"]["parameters"]["enterpriseid"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "enterpriseid", return_type=int, default=58399
            ),
            "int",
            "The enterprise ID used in the SNMP Object Identifier (OID). The genmon SNMP enterprise ID is 58399.",
            bounds="required digits",
            display_name="Enterprise ID",
        )
        AddOnCfg["gensnmp"]["parameters"]["community"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "community", return_type=str, default="public"
            ),
            "string",
            "SNMP Community string",
            bounds="minmax:4:50",
            display_name="SNMP Community",
        )
        AddOnCfg["gensnmp"]["parameters"]["use_numeric"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "use_numeric", return_type=bool, default=False
            ),
            "boolean",
            "If enabled will return numeric values (no units) in the Status, Maintenance (Evo/Nexus only) and Outage data.",
            bounds="",
            display_name="Numerics only",
        )
        AddOnCfg["gensnmp"]["parameters"]["use_integer"] = CreateAddOnParam(
            ConfigFiles[GENSNMP_CONFIG].ReadValue(
                "use_integer", return_type=bool, default=False
            ),
            "boolean",
            "If enabled, integer values (no units) will be returned when applicable in the Status, Maintenance (Evo/Nexus only) and Outage data. Enabling this value also enables 'Use Numerics'. Floating point numberic values are returned as strings",
            bounds="",
            display_name="Force Integers",
        )

        # GENTEMP
        AddOnCfg["gentemp"] = collections.OrderedDict()
        AddOnCfg["gentemp"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gentemp", default=False
        )
        AddOnCfg["gentemp"]["title"] = "External Temperature Sensors"
        Description = "Allow the display of external temperature sensor data"
        # TODO linux specific check
        if os.path.isdir("/sys/bus/w1/") == False:
            Description = (
                Description
                + "<br/><font color='red'>1-wire is not enabled but is required</font>"
            )
        AddOnCfg["gentemp"]["description"] = Description
        AddOnCfg["gentemp"]["icon"] = "rpi"
        AddOnCfg["gentemp"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gentemppy-optional"
        AddOnCfg["gentemp"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gentemp"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds that the temperature data is polled. The default value is 2 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gentemp"]["parameters"]["use_metric"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "use_metric", return_type=bool, default=False
            ),
            "boolean",
            "enable to use Celsius, disable for Fahrenheit",
            bounds="",
            display_name="Use Metric",
        )
        AddOnCfg["gentemp"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "blacklist", return_type=str, default=""
            ),
            "string",
            "Comma separated blacklist. If these vaues are found in 1 wire temperature sensor device names the sensor will be ignored.",
            bounds="",
            display_name="Sensor Device Blacklist",
        )
        AddOnCfg["gentemp"]["parameters"]["device_labels"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_labels", return_type=str, default=""
            ),
            "string",
            "Comma separated list of sensor names. These names will be displayed for each sensor. DS18B20 sensors are first, then type K thermocouples. Blacklisted devices are skipped.",
            bounds="",
            display_name="Sensor Names",
        )
        AddOnCfg["gentemp"]["parameters"]["device_nominal_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_nominal_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of nominal temperature values for the sensor. Nominal values help determine where the gauge green area ends and the yellow begins. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
            bounds="",
            display_name="Sensor Nominal Values",
        )
        AddOnCfg["gentemp"]["parameters"]["device_max_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_max_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of maximum temperature values for the sensor. This is the maximum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to disable External Temp Sensor gauges.",
            bounds="",
            display_name="Sensor Maximum Values",
        )
        AddOnCfg["gentemp"]["parameters"]["device_min_values"] = CreateAddOnParam(
            ConfigFiles[GENTEMP_CONFIG].ReadValue(
                "device_min_values", return_type=str, default=""
            ),
            "string",
            "Comma separated list of minimum temperature values for the sensor. This is the minimum gauge value. The order of these values must match the order of the Sensor Names. Leave blank to set all sensors minimum value to zero.",
            bounds="",
            display_name="Sensor Minimum Values",
        )
        # GENSENSORHAT
        AddOnCfg["gencthat"] = collections.OrderedDict()
        AddOnCfg["gencthat"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="gencthat", default=False
        )
        AddOnCfg["gencthat"]["title"] = "External Current Transformer (CT) Sensors"
        Description = "Support for Raspberry pi HAT with CTs from PintSize.me."
        # TODO linux specific check
        if os.path.exists("/dev/spidev1.0") == False:
            Description = (
                Description
                + "<br/><font color='red'>The SPI bus number one is not enabled but required for this add-on to function.</font>"
            )
        AddOnCfg["gencthat"]["description"] = Description
        AddOnCfg["gencthat"]["icon"] = "rpi"
        AddOnCfg["gencthat"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#gencthatpy-optional"
        AddOnCfg["gencthat"]["parameters"] = collections.OrderedDict()

        AddOnCfg["gencthat"]["parameters"]["poll_frequency"] = CreateAddOnParam(
            ConfigFiles[GENCTHAT_CONFIG].ReadValue(
                "poll_frequency", return_type=float, default=2.0
            ),
            "float",
            "The time in seconds that the sensors are polled. The default value is 15 seconds.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["gencthat"]["parameters"]["strict"] = CreateAddOnParam(
            ConfigFiles[GENCTHAT_CONFIG].ReadValue(
                "strict", return_type=bool, default=False
            ),
            "boolean",
            "Set to true to only use the CT data if the generator utility line is in an outage.",
            bounds="",
            display_name="Strict Usage of CT data",
        )

        # GENMOPEKA
        if sys.version_info >= (3, 7):
            Description = "Support Mopeka Pro Propane Tanks Sensor"
            try:
                import fluids
            except Exception as e1:
                Description = (
                    Description
                    + "<br/><font color='red'>The required libraries for this add on are not installed, please run the installation script.</font>"
                )

            AddOnCfg["genmopeka"] = collections.OrderedDict()
            AddOnCfg["genmopeka"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
                "enable", return_type=bool, section="genmopeka", default=False
            )
            AddOnCfg["genmopeka"]["title"] = "Mopeka Pro Propane Tank Sensor"

            AddOnCfg["genmopeka"]["description"] = Description
            AddOnCfg["genmopeka"]["icon"] = "mopeka"
            AddOnCfg["genmopeka"][
                "url"
            ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genmopekapy-optional"
            AddOnCfg["genmopeka"]["parameters"] = collections.OrderedDict()

            AddOnCfg["genmopeka"]["parameters"]["poll_frequency"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "poll_frequency", return_type=float, default=60
                ),
                "float",
                "The time in minutes that the sensors are polled. The default value is 60 minutes.",
                bounds="number",
                display_name="Poll Interval",
            )
            AddOnCfg["genmopeka"]["parameters"]["tank_address"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "tank_address", return_type=str, default=""
                ),
                "string",
                "This value is MAC address of the sensor. It must be in a format using hex numbers separated by colons (i.e. 9a:03:2b:67:25:12). Multiple tank sensors (up to 4) may be used with commas between each address",
                bounds="",
                display_name="Sensor Address",
            )
            AddOnCfg["genmopeka"]["parameters"]["tank_type"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "tank_type", return_type=str, default="1"
                ),
                "list",
                "Type of tank used. If Custom is used then Max and Min values must be setup in /etc/genmon/genmopeka.conf",
                bounds="20_LB,30_LB,40_LB,100_LB,200_LB,120_GAL,120_GAL_HORIZ,250_GAL,500_GAL,1000_GAL,Custom",
                display_name="Tank Size",
            )
            AddOnCfg["genmopeka"]["parameters"]["send_notices"] = CreateAddOnParam(
                ConfigFiles[GENMOPEKA_CONFIG].ReadValue(
                    "send_notices", return_type=bool, default=False
                ),
                "boolean",
                "Send email notices if unable to communicate with the senor or the sensor battery is low. Note: outbound email must be setup for this to work.",
                bounds="",
                display_name="Send Notices",
            )

        # GENHALINK - Native Home Assistant Integration
        AddOnCfg["genhalink"] = collections.OrderedDict()
        AddOnCfg["genhalink"]["enable"] = ConfigFiles[GENLOADER_CONFIG].ReadValue(
            "enable", return_type=bool, section="genhalink", default=False
        )
        AddOnCfg["genhalink"]["title"] = "Home Assistant Integration (Native)"
        AddOnCfg["genhalink"][
            "description"
        ] = "Native Home Assistant integration via REST/WebSocket API. No MQTT broker required."
        AddOnCfg["genhalink"]["icon"] = "homeassistant"
        AddOnCfg["genhalink"][
            "url"
        ] = "https://github.com/jgyates/genmon/wiki/1----Software-Overview#genhalinkpy-optional"
        AddOnCfg["genhalink"]["parameters"] = collections.OrderedDict()

        AddOnCfg["genhalink"]["parameters"]["port"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "port", return_type=int, default=9083
            ),
            "int",
            "Port for the REST/WebSocket API server.",
            bounds="required digits range:1024:65535",
            display_name="API Server Port",
        )
        genhalink_api_key = ConfigFiles[GENHALINK_CONFIG].ReadValue(
            "api_key", return_type=str, default=""
        )
        if not genhalink_api_key:
            genhalink_api_key = str(uuid.uuid4())
            ConfigFiles[GENHALINK_CONFIG].WriteValue("api_key", genhalink_api_key)
            LogError("Auto-generated API key for genhalink")
        AddOnCfg["genhalink"]["parameters"]["api_key"] = CreateAddOnParam(
            genhalink_api_key,
            "readonly",
            "API key for authentication (auto-generated). Copy this value into Home Assistant when adding the integration.",
            bounds="",
            display_name="API Key (read-only)",
        )
        AddOnCfg["genhalink"]["parameters"]["poll_interval"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "poll_interval", return_type=float, default=3.0
            ),
            "int",
            "Interval in seconds between polling genmon for status updates. Default is 3.",
            bounds="number",
            display_name="Poll Interval",
        )
        AddOnCfg["genhalink"]["parameters"]["blacklist"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "blacklist", return_type=str, default="Tiles"
            ),
            "string",
            "Comma-separated keywords to exclude from the API. Matches any data path containing the keyword (case-insensitive). Top-level sections: Status, Maintenance, Outage, Monitor, Tiles. Examples: 'Tiles' (UI tiles), 'Weather' (weather data), 'Platform Stats' (CPU/memory), 'Last Log Entries' (log snippets). You can also target specific values like 'Serial Number' or 'CRC Errors'.",
            bounds="",
            display_name="Excluded Data Paths",
        )
        AddOnCfg["genhalink"]["parameters"]["include_monitor_stats"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "include_monitor_stats", return_type=bool, default=True
            ),
            "boolean",
            "Include monitor/platform statistics (CPU temp, WiFi, memory).",
            bounds="",
            display_name="Include Monitor Stats",
        )
        AddOnCfg["genhalink"]["parameters"]["include_weather"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "include_weather", return_type=bool, default=True
            ),
            "boolean",
            "Include weather data if available.",
            bounds="",
            display_name="Include Weather",
        )
        AddOnCfg["genhalink"]["parameters"]["zeroconf_enabled"] = CreateAddOnParam(
            ConfigFiles[GENHALINK_CONFIG].ReadValue(
                "zeroconf_enabled", return_type=bool, default=True
            ),
            "boolean",
            "Enable Zeroconf/mDNS broadcasting so Home Assistant can auto-discover this generator. Disable for manual/fixed IP setup only.",
            bounds="",
            display_name="Zeroconf Discovery",
        )

    except Exception as e1:
        LogErrorLine("Error in GetAddOns: " + str(e1))

    return AddOnCfg


# ------------ AddNotificationAddOnParam ----------------------------------------
def AddNotificationAddOnParam(AddOnCfg, addon_name, config_file):

    try:
        AddOnCfg[addon_name]["parameters"]["notify_error"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_error", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for errors (Generator Alarms).",
            display_name="Notify for Errors",
        )
        AddOnCfg[addon_name]["parameters"]["notify_warn"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_warn", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for warnings (service due, fuel low).",
            display_name="Notify for Warnings",
        )
        AddOnCfg[addon_name]["parameters"]["notify_info"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_info", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for information (switch state change, engine state change, exercising).",
            display_name="Notify for Information",
        )
        AddOnCfg[addon_name]["parameters"]["notify_outage"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_outage", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for outages.",
            display_name="Notify for Outages",
        )
        AddOnCfg[addon_name]["parameters"]["notify_sw_update"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_sw_update", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for software updates.",
            display_name="Notify for Software Updates",
        )
        AddOnCfg[addon_name]["parameters"]["notify_pi_state"] = CreateAddOnParam(
            ConfigFiles[config_file].ReadValue(
                "notify_pi_state", return_type=bool, default=True
            ),
            "boolean",
            "Send messages for Pi hardware sensor status (CPU throttling, undervoltage, etc).",
            display_name="Notify for Pi Hardware Issues",
        )
    except Exception as e1:
        LogErrorLine("Error in AddNotificationAddOnParam: " + str(e1))

    return AddOnCfg


# ------------ AddRetryAddOnParam -----------------------------------------------
def AddRetryAddOnParam(AddOnCfg, addon_name, config_file):

    try:
        AddOnCfg[addon_name]["parameters"]["max_retry_time"] = CreateAddOnParam(
            value=ConfigFiles[config_file].ReadValue(
                "max_retry_time", return_type=int, default=600
            ),
            type="int",
            description="Maximum number of seconds to retry a failed message before dropping the message.",
            display_name="Max Retry Duration (seconds)",
        )
        AddOnCfg[addon_name]["parameters"]["default_wait"] = CreateAddOnParam(
            value=ConfigFiles[config_file].ReadValue(
                "default_wait", return_type=int, default=120
            ),
            type="int",
            description="The number of seconds to wait before retrying a failed message.",
            display_name="Retry Interval (seconds)",
        )
        # This paramerter is not exposed but a valid conf file setting
        #AddOnCfg[addon_name]["parameters"]["minimum_wait_between_messages"] = CreateAddOnParam(
        #    value=ConfigFiles[config_file].ReadValue(
        #        "minimum_wait_between_messages", return_type=int, default=0
        #    ),
        #    type="int",
        #    description="The minimum of seconds to wait between sending a message. This is typically zero, except for Callmebot Signal Messaging (should be at least 2 seconds) or other messaging apps that have minimum delays.",
        #    display_name="Min Time Between Messages (seconds)",
        #)
    except Exception as e1:
        LogErrorLine("Error in AddRetryAddOnParam: " + str(e1))
    return AddOnCfg


# ------------ MyCommon::StripJson ----------------------------------------------
def StripJson(InputString):
    for char in '{}[]"':
        InputString = InputString.replace(char, "")
    return InputString


# ------------ MyCommon::DictToString -------------------------------------------
def DictToString(InputDict, ExtraStrip=False):

    if InputDict == None:
        return ""
    ReturnString = json.dumps(
        InputDict, sort_keys=False, indent=4, separators=(" ", ": ")
    )
    return ReturnString
    if ExtraStrip:
        ReturnString = ReturnString.replace("} \n", "")
    return StripJson(ReturnString)


# -------------------------------------------------------------------------------
def CreateAddOnParam(
    value="", type="string", description="", bounds="", display_name=""
):

    # Bounds are defined in ReadSettingsFromFile comments
    Parameter = collections.OrderedDict()
    Parameter["value"] = value
    Parameter["type"] = type
    Parameter["description"] = description
    Parameter["bounds"] = bounds
    Parameter["display_name"] = display_name
    return Parameter


# -------------------------------------------------------------------------------
def GetAddOnSettings():
    try:
        return GetAddOns()
    except Exception as e1:
        LogErrorLine("Error in GetAddOnSettings: " + str(e1))
        return {}


# -------------------------------------------------------------------------------
def SaveAddOnSettings(query_string):
    try:
        if query_string == None:
            LogError("Empty query string in SaveAddOnSettings")
            return

        settings = json.loads(query_string)
        if not len(settings):
            return  # nothing to change

        ConfigDict = {
            "genmon": ConfigFiles[GENMON_CONFIG],
            "mymail": ConfigFiles[MAIL_CONFIG],
            "genloader": ConfigFiles[GENLOADER_CONFIG],
            "gensms": ConfigFiles[GENSMS_CONFIG],
            "gensms_modem": ConfigFiles[MYMODEM_CONFIG],
            "genpushover": ConfigFiles[GENPUSHOVER_CONFIG],
            "genmqtt": ConfigFiles[GENMQTT_CONFIG],
            "genmqttin": ConfigFiles[GENMQTTIN_CONFIG],
            "genslack": ConfigFiles[GENSLACK_CONFIG],
            "gencallmebot": ConfigFiles[GENCALLMEBOT_CONFIG],
            "genlog": ConfigFiles[GENLOADER_CONFIG],
            "gensyslog": ConfigFiles[GENLOADER_CONFIG],
            "gengpio": ConfigFiles[GENLOADER_CONFIG],
            "gengpioin": ConfigFiles[GENGPIOIN_CONFIG],
            "gengpioledblink": ConfigFiles[GENGPIOLEDBLINK_CONFIG],
            "genexercise": ConfigFiles[GENEXERCISE_CONFIG],
            "genemail2sms": ConfigFiles[GENEMAIL2SMS_CONFIG],
            "gentankutil": ConfigFiles[GENTANKUTIL_CONFIG],
            "gencentriconnect": ConfigFiles[GENCENTRICONNECT_CONFIG],
            "gentankdiy": ConfigFiles[GENTANKDIY_CONFIG],
            "genalexa": ConfigFiles[GENALEXA_CONFIG],
            "gensnmp": ConfigFiles[GENSNMP_CONFIG],
            "gentemp": ConfigFiles[GENTEMP_CONFIG],
            "gencthat": ConfigFiles[GENCTHAT_CONFIG],
            "genmopeka": ConfigFiles[GENMOPEKA_CONFIG],
            "gensms_voip": ConfigFiles[GENSMS_VOIP_CONFIG],
            "genhomeassistant": ConfigFiles[GENHOMEASSISTANT_CONFIG],
            "genhalink": ConfigFiles[GENHALINK_CONFIG],
        }

        for module, entries in settings.items():  # module
            ParameterConfig = ConfigDict.get(module, None)
            if ParameterConfig == None:
                LogError("Invalid module in SaveAddOnSettings: " + module)
                continue
            # Find if it needs to be enabled / disabled or if there are parameters
            for basesettings, basevalues in entries.items():  # base settings
                if basesettings == "enable":
                    ConfigFiles[GENLOADER_CONFIG].WriteValue(
                        "enable", basevalues, section=module
                    )
                    # TODO This may not be needed now
                    if module == "gentankutil":
                        # update genmon.conf also to let it know that it should watch for external fuel data
                        ConfigFiles[GENMON_CONFIG].WriteValue(
                            "use_external_fuel_data", basevalues, section="genmon"
                        )
                    if module == "gentankdiy":
                        # update genmon.conf also to let it know that it should watch for external fuel data
                        ConfigFiles[GENMON_CONFIG].WriteValue(
                            "use_external_fuel_data_diy", basevalues, section="genmon"
                        )
                    if module == "genhalink" and basevalues.lower() == "true":
                        # Auto-generate API key if empty when addon is enabled
                        current_key = ConfigFiles[GENHALINK_CONFIG].ReadValue(
                            "api_key", return_type=str, default=""
                        )
                        if not current_key:
                            new_key = str(uuid.uuid4())
                            ConfigFiles[GENHALINK_CONFIG].WriteValue("api_key", new_key)
                            LogError("Auto-generated API key for genhalink")

                if basesettings == "parameters":
                    for params, paramvalue in basevalues.items():
                        if module == "genlog" and params == "Log File Name":
                            ConfigFiles[GENLOADER_CONFIG].WriteValue(
                                "args", "-f " + paramvalue, section=module
                            )
                        else:
                            ParameterConfig.WriteValue(params, paramvalue)

        Restart()
        return
    except Exception as e1:
        LogErrorLine("Error in SaveAddOnSettings: " + str(e1))
        return


# -------------------------------------------------------------------------------
def ReadNotificationsFromFile():

    ### array containing information on the parameters
    ## 1st: email address
    ## 2nd: sort order, aka row number
    ## 3rd: comma delimited list of notidications that are enabled
    NotificationSettings = {}
    # e.g. {'myemail@gmail.com': [1]}
    # e.g. {'myemail@gmail.com': [1, 'error,warn,info']}

    EmailsToNotify = []
    try:
        # There should be only one "email_recipient" entry
        EmailsStr = ConfigFiles[MAIL_CONFIG].ReadValue("email_recipient")

        for email in EmailsStr.split(","):
            email = email.strip()
            EmailsToNotify.append(email)

        SortOrder = 1
        for email in EmailsToNotify:
            Notify = ConfigFiles[MAIL_CONFIG].ReadValue(email, default="")
            if Notify == "":
                NotificationSettings[email] = [SortOrder]
            else:
                NotificationSettings[email] = [SortOrder, Notify]
    except Exception as e1:
        LogErrorLine("Error in ReadNotificationsFromFile: " + str(e1))

    return NotificationSettings


# -------------------------------------------------------------------------------
def SaveNotifications(query_string):

    """
    email_recipient = email1@gmail.com,email2@gmail.com
    email1@gmail.com = outage,info
    email2@gmail.com = outage,info,error

    notifications = {'email1@gmail.com': ['outage,info'], 'email2@gmail.com': ['outage,info,error']}
    notifications_order_string = email1@gmail.com,email2@gmail.com

    or

    email_recipient = email1@gmail.com

    notifications = {'email1@gmail.com': ['']}
    notifications_order_string = email1@gmail.com

    """
    notifications = dict(parse_qs(query_string, 1))
    notifications_order_string = ",".join([v[0] for v in parse_qsl(query_string, 1)])

    oldEmailsList = []
    oldNotifications = {}
    oldEmailRecipientString = ""
    try:
        with CriticalLock:
            # get existing settings
            if ConfigFiles[MAIL_CONFIG].HasOption("email_recipient"):
                oldEmailRecipientString = ConfigFiles[MAIL_CONFIG].ReadValue(
                    "email_recipient"
                )
                oldEmailRecipientString.strip()
                oldEmailsList = oldEmailRecipientString.split(",")
                for oldEmailItem in oldEmailsList:
                    if ConfigFiles[MAIL_CONFIG].HasOption(oldEmailItem):
                        oldNotifications[oldEmailItem] = ConfigFiles[
                            MAIL_CONFIG
                        ].ReadValue(oldEmailItem)

            # compare, remove notifications if needed
            for oldEmailItem in oldEmailsList:
                if not oldEmailItem in notifications.keys() and ConfigFiles[
                    MAIL_CONFIG
                ].HasOption(oldEmailItem):
                    ConfigFiles[MAIL_CONFIG].WriteValue(oldEmailItem, "", remove=True)

            # add / update the entries
            # update email recipient if needed
            if oldEmailRecipientString != notifications_order_string:
                ConfigFiles[MAIL_CONFIG].WriteValue(
                    "email_recipient", notifications_order_string
                )

            # update catigories
            for newEmail, newCats in notifications.items():
                # remove catigories if needed from existing emails
                if not len(newCats[0]) and ConfigFiles[MAIL_CONFIG].HasOption(newEmail):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, "", remove=True)
                # update or add catigories
                if len(newCats[0]):
                    ConfigFiles[MAIL_CONFIG].WriteValue(newEmail, newCats[0])

        Restart()
    except Exception as e1:
        LogErrorLine("Error in SaveNotifications: " + str(e1))
    return


# -------------------------------------------------------------------------------
def ReadSingleConfigValue(
    entry, filename=None, section=None, type="string", default="", bounds=None
):

    try:

        try:
            if filename == None:
                config = ConfigFiles[GENMON_CONFIG]
            else:
                config = ConfigFiles[filename]
        except Exception as e1:
            LogErrorLine(
                "Unknow file in UpdateConfigFile: " + filename + ": " + str(e1)
            )
            return default

        if section != None:
            config.SetSection(section)

        if not config.HasOption(entry):
            return default

        if type.lower() == "string" or type == "password":
            return config.ReadValue(entry)
        elif type.lower() == "boolean":
            return config.ReadValue(
                entry, return_type=bool, default=default, NoLog=True
            )
        elif type.lower() == "int":
            return config.ReadValue(entry, return_type=int, default=default, NoLog=True)
        elif type.lower() == "float":
            return config.ReadValue(
                entry, return_type=float, default=default, NoLog=True
            )
        elif type.lower() == "list":
            Value = config.ReadValue(entry)
            if bounds != None:
                DefaultList = bounds.split(",")
                if Value.lower() in (name.lower() for name in DefaultList):
                    return Value
                else:
                    LogError(
                        "Warning: Reading Config File (value not in list): %s : %s"
                        % (entry, Value)
                    )
                return default
            else:
                LogError(
                    "Error Reading Config File (bounds not provided): %s : %s"
                    % (entry, Value)
                )
                return default
        else:
            LogError(
                "Error Reading Config File (unknown type): %s : %s" % (entry, type)
            )
            return default

    except Exception as e1:
        LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return default


# -------------------------------------------------------------------------------
def GetImportConfigFileNames():

    try:
        path = os.path.join(
            os.path.dirname(os.path.realpath(__file__)), "data", "controller"
        )
        listing = os.listdir(path)
        return ",".join(listing)
    except Exception as e1:
        LogErrorLine("Error Reading Config File (ReadSingleConfigValue): " + str(e1))
        return ""


# -------------------------------------------------------------------------------
def ReadAdvancedSettingsFromFile():

    ConfigSettings = collections.OrderedDict()
    try:
        # This option is not displayed as it will break the link between genmon and genserv
        ConfigSettings["server_port"] = [
            "int",
            "Server Port",
            5,
            ProgramDefaults.ServerPort,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "server_port",
        ]
        # this option is not displayed as this will break the modbus comms, only for debugging
        ConfigSettings["address"] = [
            "string",
            "Modbus slave address",
            6,
            "9d",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "address",
        ]
        ConfigSettings["response_address"] = [
            "string",
            "Modbus slave transmit address",
            7,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "response_address",
        ]
        ConfigSettings["additional_modbus_timeout"] = [
            "float",
            "Additional Modbus Timeout (sec)",
            8,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "additional_modbus_timeout",
        ]
        ConfigSettings["use_modbus_fc4"] = [
            "boolean",
            "Use Modbus FC4 instead of FC3",
            9,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "use_modbus_fc4",
        ]
        ConfigSettings["serial_rate"] = [
            "int",
            "Serial Data Rate",
            10,
            9600,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "serial_rate",
        ]
        ConfigSettings["serial_parity"] = [
            "list",
            "Serial Parity",
            11,
            "None",
            "",
            "None,Even,Odd",
            GENMON_CONFIG,
            GENMON_SECTION,
            "serial_parity",
        ]
        ConfigSettings["forceserialuse"] = [
            "boolean",
            "Force Use of Serial Port on Errors",
            12,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "forceserialuse",
        ]
        ConfigSettings["watchdog_addition"] = [
            "float",
            "Additional Watchdog Timeout (sec)",
            13,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "watchdog_addition",
        ]
        ConfigSettings["controllertype"] = [
            "list",
            "Controller Type",
            14,
            "generac_evo_nexus",
            "",
            "generac_evo_nexus,h_100,powerzone,custom",
            GENMON_CONFIG,
            GENMON_SECTION,
            "controllertype",
        ]

        import_config_files = GetImportConfigFileNames()
        ConfigSettings["import_config_file"] = [
            "list",
            "Custom Controller Config File",
            21,
            "Evolution_Liquid_Cooled.json",
            "",
            import_config_files,
            GENMON_CONFIG,
            GENMON_SECTION,
            "import_config_file",
        ]
        if ControllerType == "custom":
            ConfigSettings["ignore_alarms"] = [
            "string",
            "Ignore Alarms",
            22,
            "",
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "ignore_alarms",
        ]
        ConfigSettings["phase"] = [
            "int",
            "Generator Phase",
            22,
            "1",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "phase",
        ]
        ConfigSettings["loglocation"] = [
            "string",
            "Log Directory",
            23,
            ProgramDefaults.LogPath,
            "",
            "required UnixDir",
            GENMON_CONFIG,
            GENMON_SECTION,
            "loglocation",
        ]
        ConfigSettings["userdatalocation"] = [
            "string",
            "User Defined Data Directory",
            24,
            os.path.dirname(os.path.realpath(__file__)),
            "",
            "required UnixDir",
            GENMON_CONFIG,
            GENMON_SECTION,
            "userdatalocation",
        ]
        ConfigSettings["ignore_unknown"] = [
            "boolean",
            "Ignore Unknown Values",
            25,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "ignore_unknown",
        ]
        ConfigSettings["alternate_date_format"] = [
            "boolean",
            "Alternate Date Format",
            26,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "alternate_date_format",
        ]

        # These settings are not displayed as the auto-detect controller will set these
        # these are only to be used to override the auto-detect
        # ConfigSettings["liquidcooled"] = ['boolean', 'Force Controller Type (cooling)', 30, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "liquidcooled"]
        # ConfigSettings["evolutioncontroller"] = ['boolean', 'Force Controller Type (Evo/Nexus)', 31, True, "", 0, GENMON_CONFIG, GENMON_SECTION, "evolutioncontroller"]
        # remove outage log, this will always be in the same location
        # ConfigSettings["outagelog"] = ['string', 'Outage Log', 32, "/home/pi/genmon/outage.txt", "", "required UnixFile", GENMON_CONFIG, GENMON_SECTION, "outagelog"]
        ConfigSettings["serialnumberifmissing"] = [
            "string",
            "Serial Number if Missing",
            36,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "serialnumberifmissing",
        ]
        ConfigSettings["additionalrunhours"] = [
            "float",
            "Additional Run Hours",
            37,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "additionalrunhours",
        ]
        ConfigSettings["estimated_load"] = [
            "float",
            "Estimated Load",
            38,
            "0.0",
            "",
            "required range:0:1",
            GENMON_CONFIG,
            GENMON_SECTION,
            "estimated_load",
        ]
        ConfigSettings["subtractfuel"] = [
            "float",
            "Subtract Fuel",
            39,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "subtractfuel",
        ]
        if ControllerType == "generac_evo_nexus":
            ConfigSettings["unbalanced_capacity"] = [
                "float",
                "Unbalanced Load Capacity",
                46,
                "0",
                "",
                "range:0:0.50",
                GENMON_CONFIG,
                GENMON_SECTION,
                "unbalanced_capacity",
            ]
            ConfigSettings["show_hours_activation"] = [
            "boolean",
            "Time Since Activation Format",
            47,
            True,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "show_hours_activation",
            ]
        # ConfigSettings["kwlog"] = ['string', 'Power Log Name / Disable', 36, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "kwlog"]
        if ControllerType != "h_100":
            ConfigSettings["usenominallinevolts"] = [
                "boolean",
                "Use Nominal Volts Override",
                45,
                False,
                "",
                0,
                GENMON_CONFIG,
                GENMON_SECTION,
                "usenominallinevolts",
            ]
            ConfigSettings["nominallinevolts"] = [
                "int",
                "Override nominal line voltage in UI",
                46,
                "240",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "nominallinevolts",
            ]
            ConfigSettings["outage_notice_delay"] = [
                "int",
                "Outage Notice Delay",
                47,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "outage_notice_delay",
            ]
            ConfigSettings["min_outage_duration"] = [
                "int",
                "Minimum Outage Duration",
                48,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "min_outage_duration",
            ]
            ConfigSettings["outage_notice_interval"] = [
                "int",
                "Outage Recurring Notice Interval (minutes)",
                49,
                "0",
                "",
                "digits",
                GENMON_CONFIG,
                GENMON_SECTION,
                "outage_notice_interval",
            ]
            ControllerInfo = GetControllerInfo("controller").lower()
            if "nexus" in ControllerInfo:
                ConfigSettings["nexus_legacy_freq"] = [
                    "boolean",
                    "Use Nexus Legacy Frequency",
                    50,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "nexus_legacy_freq",
                ]
                # this is setup automatically for Nexus controllers
                # ConfigSettings["uselegacysetexercise"] = ['boolean', 'Use Legacy Exercise Time', 49, False, "", 0, GENMON_CONFIG, GENMON_SECTION, "uselegacysetexercise"]
        else:
            ConfigSettings["usecalculatedpower"] = [
                "boolean",
                "Use Calculated Power",
                45,
                False,
                "",
                0,
                GENMON_CONFIG,
                GENMON_SECTION,
                "usecalculatedpower",
            ]

        ConfigSettings["half_rate"] = [
            "float",
            "Fuel Rate Half Load",
            55,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "half_rate",
        ]
        ConfigSettings["full_rate"] = [
            "float",
            "Fuel Rate Full Load",
            56,
            "0.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "full_rate",
        ]
        ConfigSettings["fuel_units"] = [
            "list",
            "Fuel Units",
            57,
            "gal",
            "",
            "gal,cubic feet",
            GENMON_CONFIG,
            GENMON_SECTION,
            "fuel_units",
        ]
        ConfigSettings["enable_fuel_log"] = [
            "boolean",
            "Log Fuel Level to File",
            60,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "enable_fuel_log",
        ]
        ConfigSettings["fuel_log_freq"] = [
            "float",
            "Fuel Log Frequency",
            61,
            "15.0",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "fuel_log_freq",
        ]
        # ConfigSettings["fuel_log"] = ['string', 'Fuel Log Path and File Name', 62, "", "", 0, GENMON_CONFIG, GENMON_SECTION, "/etc/genmon/fuellog.txt"]

        ConfigSettings["kwlogmax"] = [
            "string",
            "Maximum size Power Log (MB)",
            70,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "kwlogmax",
        ]
        ConfigSettings["max_powerlog_entries"] = [
            "int",
            "Maximum Entries in Power Log",
            71,
            "8000",
            "digits",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "min_powerlog_entries",
        ]
        
        ConfigSettings["currentdivider"] = [
            "float",
            "Current Divider",
            72,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "currentdivider",
        ]
        ConfigSettings["currentoffset"] = [
            "float",
            "Current Offset",
            73,
            "",
            "",
            "number",
            GENMON_CONFIG,
            GENMON_SECTION,
            "currentoffset",
        ]
        ConfigSettings["legacy_power"] = [
            "boolean",
            "Use Legacy Power Calculation",
            74,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "legacy_power",
        ]

        ConfigSettings["disableplatformstats"] = [
            "boolean",
            "Disable Platform Stats",
            80,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "disableplatformstats",
        ]
        ConfigSettings["https_port"] = [
            "int",
            "Override HTTPS port",
            81,
            "",
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "https_port",
        ]
        ConfigSettings["user_url"] = [
            "string",
            "User URL",
            82,
            "",
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "user_url",
        ]
        ConfigSettings["extend_wait"] = [
            "int",
            "Extend email retry",
            83,
            "0",
            "",
            "digits",
            MAIL_CONFIG,
            MAIL_SECTION,
            "extend_wait",
        ]
        ConfigSettings["multi_instance"] = [
            "boolean",
            "Allow Multiple Genmon Instances",
            85,
            False,
            "",
            0,
            GENMON_CONFIG,
            GENMON_SECTION,
            "multi_instance",
        ]

        ConfigSettings["max_login_attempts"] = [
            "int",
            "Maxmum login attempts before temporary lockout",
            96,
            5,
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "max_login_attempts",
        ]
        ConfigSettings["login_lockout_seconds"] = [
            "int",
            "Login lockout duration in seconds",
            97,
            (5 * 60),
            "",
            "digits",
            GENMON_CONFIG,
            GENMON_SECTION,
            "login_lockout_seconds",
        ]

        try:
            if GStartInfo["Linux"]:
                ConfigSettings["uselinuxwifisignalgauge"] = [
                    "boolean",
                    "Show Wifi Signal Strength Gauge",
                    108,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "uselinuxwifisignalgauge",
                ]
            if GStartInfo["Linux"]:
                ConfigSettings["wifiispercent"] = [
                    "boolean",
                    "Wifi Gauge is percentage",
                    108,
                    False,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "wifiispercent",
                ]
                ConfigSettings["preferred_network_adapter"] = [
                    "string",
                    "Preferred Network Adapter",
                    108,
                    "",
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "preferred_network_adapter",
                ]
            if GStartInfo["Linux"]:
                ConfigSettings["useraspberrypicputempgauge"] = [
                    "boolean",
                    "Show CPU Temperature Gauge",
                    109,
                    True,
                    "",
                    0,
                    GENMON_CONFIG,
                    GENMON_SECTION,
                    "useraspberrypicputempgauge",
                ]
        except:
            pass

        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=GENMON_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=MAIL_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            else:
                LogError(
                    "Invaild Config File in ReadAdvancedSettingsFromFile: "
                    + str(List[6])
                )

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadAdvancedSettingsFromFile: " + str(e1))
    return ConfigSettings


# -------------------------------------------------------------------------------
def SaveAdvancedSettings(query_string):
    try:

        if query_string == None:
            LogError("Empty query string in SaveAdvancedSettings")
            return
        # e.g. {'displayunknown': ['true']}
        settings = dict(parse_qs(query_string, 1))
        if not len(settings):
            # nothing to change
            return
        CurrentConfigSettings = ReadAdvancedSettingsFromFile()
        with CriticalLock:
            for Entry in settings.keys():
                ConfigEntry = CurrentConfigSettings.get(Entry, None)
                if ConfigEntry != None:
                    ConfigFile = CurrentConfigSettings[Entry][6]
                    Value = settings[Entry][0]
                    Section = CurrentConfigSettings[Entry][7]
                else:
                    LogError("Invalid setting in SaveAdvancedSettings: " + str(Entry))
                    continue
                UpdateConfigFile(ConfigFile, Section, Entry, Value)
        Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveAdvancedSettings): " + str(e1))


# -------------------------------------------------------------------------------
def ReadSettingsFromFile():

    ### array containing information on the parameters
    ## 1st: type of attribute
    ## 2nd: Attribute title
    ## 3rd: Sort Key
    ## 4th: current value (will be populated further below)
    ## 5th: tooltip (will be populated further below)
    ## 6th: validation rule if type is string or int (see below). If type is list, this is a comma delimited list of options
    ## 7th: Config file
    ## 8th: config file section
    ## 9th: config file entry name
    ## Validation Rules:
    ##         A rule must be in this format rule:param where rule is the name of the rule and param is a rule parameter,
    ##         for example minmax:10:50 will use the minmax rule with two arguments, 10 and 50.
    ##             required: The field is required. Only works with text inputs.
    ##             digits: Only digits.
    ##             number: Must be a number.
    ##             username: Must be between 4 and 32 characters long and start with a letter. You may use letters, numbers, underscores, and one dot.
    ##             email: Must be a valid email.
    ##             pass: Must be at least 6 characters long, and contain at least one number, one uppercase and one lowercase letter.
    ##             strongpass: Must be at least 8 characters long and contain at least one uppercase and one lowercase letter and one number or special character.
    ##             phone: Must be a valid US phone number.
    ##             zip: Must be a valid US zip code
    ##             url: Must be a valid URL.
    ##             range:min:max: Must be a number between min and max. Usually combined with number or digits.
    ##             min:min: Must be at least min characters long.
    ##             max:max: Must be no more that max characters long.
    ##             minmax:min:max: Must be between min and max characters long.
    ##             minoption:min: Must have at least min checkboxes or radios selected.
    ##             maxoption:max: Must have no more than max checkboxes or radios selected.
    ##             select:default: Make a select required, where default is the value of the default option.
    ##             extension:ext: Validates file inputs. You can have as many ext as you want.
    ##             equalto:name: Must be equal to another field where name is the name of the field.
    ##             date:format: Must a valid date in any format. The default is mm/dd/yyyy but you can pass any format with any separator, ie. date:yyyy-mm-dd.
    ##             InternetAddress: url without http in front.
    ##             UnixFile: Unix file file.
    ##             UnixDir: Unix file path.
    ##             UnixDevice: Unix file path starting with /dev/.

    ConfigSettings = collections.OrderedDict()
    ConfigSettings["sitename"] = [
        "string",
        "Site Name",
        1,
        "SiteName",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "sitename",
    ]
    ConfigSettings["use_serial_tcp"] = [
        "boolean",
        "Enable Serial over TCP/IP",
        2,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "use_serial_tcp",
    ]
    ConfigSettings["port"] = [
        "string",
        "Port for Serial Communication",
        3,
        "/dev/serial0",
        "",
        "required UnixDevice",
        GENMON_CONFIG,
        GENMON_SECTION,
        "port",
    ]
    ConfigSettings["serial_tcp_address"] = [
        "string",
        "Serial Server TCP/IP Address",
        4,
        "",
        "",
        "InternetAddress",
        GENMON_CONFIG,
        GENMON_SECTION,
        "serial_tcp_address",
    ]
    ConfigSettings["serial_tcp_port"] = [
        "int",
        "Serial Server TCP/IP Port",
        5,
        "8899",
        "",
        "digits",
        GENMON_CONFIG,
        GENMON_SECTION,
        "serial_tcp_port",
    ]
    ConfigSettings["modbus_tcp"] = [
        "boolean",
        "Use Modbus TCP protocol",
        6,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "modbus_tcp",
    ]

    ConfigSettings["disableoutagecheck"] = [
        "boolean",
        "Do Not Check for Outages",
        17,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disableoutagecheck",
    ]

    if GStartInfo["SetGenTime"]:
        ConfigSettings["syncdst"] = [
            "boolean",
            "Sync Daylight Savings Time",
            22,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "syncdst",
        ]
        ConfigSettings["synctime"] = [
            "boolean",
            "Sync Time",
            23,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "synctime",
        ]
    ConfigSettings["metricweather"] = [
        "boolean",
        "Use Metric Units",
        24,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "metricweather",
    ]
    ConfigSettings["optimizeforslowercpu"] = [
        "boolean",
        "Optimize for slower CPUs",
        25,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "optimizeforslowercpu",
    ]
    ConfigSettings["disablepowerlog"] = [
        "boolean",
        "Disable Power / Current Display",
        26,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disablepowerlog",
    ]
    ConfigSettings["autofeedback"] = [
        "boolean",
        "Automated Feedback",
        29,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "autofeedback",
    ]
    ConfigSettings["update_check"] = [
        "boolean",
        "Check for Software Update",
        30,
        True,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "update_check",
    ]

    ConfigSettings["nominalfrequency"] = [
        "list",
        "Rated Frequency",
        101,
        "60",
        "",
        "50,60",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalfrequency",
    ]
    ConfigSettings["nominalrpm"] = [
        "int",
        "Nominal RPM",
        102,
        "3600",
        "",
        "required digits range:1500:4000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalrpm",
    ]
    ConfigSettings["nominalkw"] = [
        "int",
        "Maximum kW Output",
        103,
        "22",
        "",
        "required digits range:0:1000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "nominalkw",
    ]
    ConfigSettings["fueltype"] = [
        "list",
        "Fuel Type",
        104,
        "Natural Gas",
        "",
        "Natural Gas,Propane,Diesel,Gasoline",
        GENMON_CONFIG,
        GENMON_SECTION,
        "fueltype",
    ]
    ConfigSettings["tanksize"] = [
        "int",
        "Fuel Tank Size",
        105,
        "0",
        "",
        "required digits range:0:10000",
        GENMON_CONFIG,
        GENMON_SECTION,
        "tanksize",
    ]

    ControllerInfo = GetControllerInfo("controller").lower()
    if (
        "liquid cooled" in ControllerInfo
        and "evolution" in ControllerInfo
        and GetControllerInfo("fueltype").lower() == "diesel"
    ):
        ConfigSettings["usesensorforfuelgauge"] = [
            "boolean",
            "Use Sensor for Fuel Gauge",
            106,
            True,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "usesensorforfuelgauge",
        ]

    if ControllerType == "h_100" or ControllerType == "powerzone":
        Choices = "120/208,120/240,230/400,240/415,277/480,347/600"
        ConfigSettings["voltageconfiguration"] = [
            "list",
            "Line to Neutral / Line to Line",
            107,
            "277/480",
            "",
            Choices,
            GENMON_CONFIG,
            GENMON_SECTION,
            "voltageconfiguration",
        ]
        ConfigSettings["hts_transfer_switch"] = [
            "boolean",
            "HTS/MTS/STS Transfer Switch",
            109,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "hts_transfer_switch",
        ]
        ConfigSettings["usesensorforfuelgauge"] = [
            "boolean",
            "Use Sensor for Fuel Gauge",
            106,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "usesensorforfuelgauge",
        ]
    else:  # ControllerType == "generac_evo_nexus":
        ConfigSettings["enhancedexercise"] = [
            "boolean",
            "Enhanced Exercise Time",
            109,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "enhancedexercise",
        ]
    
    if ControllerType == "custom":
        ConfigSettings["nominalbattery"] = [
                "list",
                "Nominal Battery Voltage",
                108,
                "24",
                "",
                "12,24",
                GENMON_CONFIG,
                GENMON_SECTION,
                "nominalbattery",
            ]

    ConfigSettings["smart_transfer_switch"] = [
        "boolean",
        "Smart Transfer Switch",
        110,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "smart_transfer_switch",
    ]
    ConfigSettings["displayunknown"] = [
        "boolean",
        "Display Experimental Data",
        111,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "displayunknown",
    ]

    if ControllerType == "h_100":
        ConfigSettings["industrialoutagecheck"] = [
            "boolean",
            "Outage Notice on Transfer State Change",
            112,
            False,
            "",
            "",
            GENMON_CONFIG,
            GENMON_SECTION,
            "industrialoutagecheck",
        ]

    # These do not appear to work on reload, some issue with Flask
    ConfigSettings["usehttps"] = [
        "boolean",
        "Use Secure Web Server",
        200,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "usehttps",
    ]
    ConfigSettings["cert_mode"] = [
        "list",
        "Certificate Mode",
        203,
        "selfsigned",
        "",
        "selfsigned,localca,custom",
        GENMON_CONFIG,
        GENMON_SECTION,
        "cert_mode",
    ]
    ConfigSettings["keyfile"] = [
        "string",
        "https Key File",
        204,
        "",
        "",
        "UnixFile",
        GENMON_CONFIG,
        GENMON_SECTION,
        "keyfile",
    ]
    ConfigSettings["certfile"] = [
        "string",
        "https Certificate File",
        205,
        "",
        "",
        "UnixFile",
        GENMON_CONFIG,
        GENMON_SECTION,
        "certfile",
    ]
    ConfigSettings["http_user"] = [
        "string",
        "Web Username",
        206,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_user",
    ]
    ConfigSettings["http_pass"] = [
        "password",
        "Web Password",
        207,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_pass",
    ]
    ConfigSettings["http_user_ro"] = [
        "string",
        "Limited Rights User Username",
        208,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_user_ro",
    ]
    ConfigSettings["http_pass_ro"] = [
        "password",
        "Limited Rights User Password",
        209,
        "",
        "",
        "minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_pass_ro",
    ]
    ConfigSettings["http_port"] = [
        "int",
        "Port of WebServer",
        215,
        8000,
        "",
        "required digits",
        GENMON_CONFIG,
        GENMON_SECTION,
        "http_port",
    ]
    ConfigSettings["favicon"] = [
        "string",
        "FavIcon",
        220,
        "",
        "",
        "minmax:8:255",
        GENMON_CONFIG,
        GENMON_SECTION,
        "favicon",
    ]
    ConfigSettings["usemfa"] = [
        "boolean",
        "Use Multi-Factor Authentication",
        210,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "usemfa",
    ]
    # this value is for display only, it can not be changed by the web app
    # Only expose the provisioning URL when running over HTTPS so the
    # base32 secret is never transmitted in cleartext.
    # When MFA is already enrolled, suppress the provisioning URL so the
    # secret key is never re-exposed after initial setup.
    mfa_url_value = None
    if bUseSecureHTTP and not bMfaEnrolled:
        mfa_url_value = MFA_URL
        if not mfa_url_value and SecretMFAKey:
            try:
                mfa_url_value = pyotp.totp.TOTP(SecretMFAKey).provisioning_uri(
                    "genmon", issuer_name="Genmon"
                )
            except Exception:
                pass
    ConfigSettings["mfa_url"] = [
        "qrcode",
        "MFA QRCode",
        212,
        mfa_url_value,
        "",
        "",
        None,
        None,
        "mfa_url",
    ]
    ConfigSettings["mfa_enrolled"] = [
        "boolean",
        "MFA Enrolled",
        212.5,
        bMfaEnrolled,
        "",
        "",
        None,
        None,
        "mfa_enrolled",
    ]
    # Info-only flag so the JS settings UI can show whether email OTP is available
    email_ok = (mail is not None and not getattr(mail, 'DisableEmail', True)
                and not getattr(mail, 'DisableSMTP', True))
    ConfigSettings["email_configured"] = [
        "boolean",
        "Email Configured",
        212.6,
        email_ok,
        "",
        "",
        None,
        None,
        "email_configured",
    ]
    # Info-only cert status for the UI cert wizard
    ConfigSettings["cert_info"] = [
        "string",
        "Certificate Info",
        203.5,
        _get_cert_info(),
        "",
        "",
        None,
        None,
        "cert_info",
    ]
    ConfigSettings["remember_me_days"] = [
        "int",
        "Remember Me (days, 0 = browser session only)",
        215,
        0,
        "",
        "minmax:0:365",
        GENMON_CONFIG,
        GENMON_SECTION,
        "remember_me_days",
    ]
    ConfigSettings["mfa_trust_extend"] = [
        "boolean",
        "Remember this browser & don't ask for MFA again",
        216,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "mfa_trust_extend",
    ]
    ConfigSettings["mfa_trust_days"] = [
        "int",
        "Days to remember (never use on shared computers)",
        217,
        90,
        "",
        "minmax:1:365",
        GENMON_CONFIG,
        GENMON_SECTION,
        "mfa_trust_days",
    ]


    #
    # ConfigSettings["disableemail"] = ['boolean', 'Disable Email Usage', 300, True, "", "", MAIL_CONFIG, MAIL_SECTION, "disableemail"]
    ConfigSettings["disablesmtp"] = [
        "boolean",
        "Disable Sending Email",
        300,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "disablesmtp",
    ]
    ConfigSettings["email_account"] = [
        "string",
        "Email Account",
        301,
        "myemail@gmail.com",
        "",
        "minmax:3:50",
        MAIL_CONFIG,
        MAIL_SECTION,
        "email_account",
    ]
    ConfigSettings["email_pw"] = [
        "password",
        "Email Password",
        302,
        "password",
        "",
        "max:70",
        MAIL_CONFIG,
        MAIL_SECTION,
        "email_pw",
    ]
    ConfigSettings["sender_account"] = [
        "string",
        "Sender Address",
        303,
        "no-reply@gmail.com",
        "",
        "email",
        MAIL_CONFIG,
        MAIL_SECTION,
        "sender_account",
    ]
    ConfigSettings["sender_name"] = [
        "string",
        "Sender Name",
        304,
        "",
        "",
        "max:50",
        MAIL_CONFIG,
        MAIL_SECTION,
        "sender_name",
    ]
    # email_recipient setting will be handled on the notification screen
    ConfigSettings["smtp_server"] = [
        "string",
        "SMTP Server",
        305,
        "smtp.gmail.com",
        "",
        "InternetAddress",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtp_server",
    ]
    ConfigSettings["smtp_port"] = [
        "int",
        "SMTP Server Port",
        307,
        587,
        "",
        "digits",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtp_port",
    ]
    ConfigSettings["ssl_enabled"] = [
        "boolean",
        "Use SSL Encryption",
        308,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "ssl_enabled",
    ]
    ConfigSettings["tls_disable"] = [
        "boolean",
        "Disable TLS Encryption",
        309,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "tls_disable",
    ]
    ConfigSettings["smtpauth_disable"] = [
        "boolean",
        "Disable SMTP Auth",
        309,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "smtpauth_disable",
    ]

    ConfigSettings["disableimap"] = [
        "boolean",
        "Disable Receiving Email",
        400,
        False,
        "",
        "",
        MAIL_CONFIG,
        MAIL_SECTION,
        "disableimap",
    ]
    ConfigSettings["imap_server"] = [
        "string",
        "IMAP Server",
        401,
        "imap.gmail.com",
        "",
        "InternetAddress",
        MAIL_CONFIG,
        MAIL_SECTION,
        "imap_server",
    ]
    ConfigSettings["readonlyemailcommands"] = [
        "boolean",
        "Disable Email Write Commands",
        402,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "readonlyemailcommands",
    ]
    ConfigSettings["incoming_mail_folder"] = [
        "string",
        "Incoming Mail Folder",
        403,
        "Generator",
        "",
        "minmax:1:1500",
        GENMON_CONFIG,
        GENMON_SECTION,
        "incoming_mail_folder",
    ]
    ConfigSettings["processed_mail_folder"] = [
        "string",
        "Mail Processed Folder",
        404,
        "Generator/Processed",
        "",
        "minmax:1:255",
        GENMON_CONFIG,
        GENMON_SECTION,
        "processed_mail_folder",
    ]

    ConfigSettings["disableweather"] = [
        "boolean",
        "Disable Weather Functionality",
        500,
        False,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "disableweather",
    ]
    ConfigSettings["weatherkey"] = [
        "string",
        "Openweathermap.org API key",
        501,
        "",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "weatherkey",
    ]
    ConfigSettings["weatherlocation"] = [
        "string",
        "Location to report weather",
        502,
        "",
        "",
        "required minmax:4:50",
        GENMON_CONFIG,
        GENMON_SECTION,
        "weatherlocation",
    ]
    ConfigSettings["minimumweatherinfo"] = [
        "boolean",
        "Display Minimum Weather Info",
        504,
        True,
        "",
        "",
        GENMON_CONFIG,
        GENMON_SECTION,
        "minimumweatherinfo",
    ]

    try:
        # Get all the config values
        for entry, List in ConfigSettings.items():
            if List[6] == GENMON_CONFIG:
                # filename, section = None, type = "string", entry, default = "", bounds = None):
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=GENMON_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                    bounds=List[5],
                )
            elif List[6] == MAIL_CONFIG:
                (ConfigSettings[entry])[3] = ReadSingleConfigValue(
                    entry=List[8],
                    filename=MAIL_CONFIG,
                    section=List[7],
                    type=List[0],
                    default=List[3],
                )
            elif List[6] == None:
                # info-only fields: refresh runtime-computed values
                if entry == "cert_info":
                    (ConfigSettings[entry])[3] = _get_cert_info()
            else:
                LogError("Invaild Config File in ReadSettingsFromFile: " + str(List[6]))

        GetToolTips(ConfigSettings)
    except Exception as e1:
        LogErrorLine("Error in ReadSettingsFromFile: " + entry + ": " + str(e1))

    return ConfigSettings


# -------------------------------------------------------------------------------
def GetAllConfigValues(FileName, section):

    ReturnDict = {}
    try:
        config = MyConfig(filename=FileName, section=section, log=log)

        if config == None:
            return ReturnDict
        for (key, value) in config.GetList():
            ReturnDict[key.lower()] = value
    except Exception as e1:
        LogErrorLine(
            "Error GetAllConfigValues: " + FileName + ": " + section + ": " + str(e1)
        )

    return ReturnDict


# -------------------------------------------------------------------------------
def GetControllerInfo(request=None):

    ReturnValue = "Evolution, Air Cooled"
    try:
        if request.lower() == "controller":
            ReturnValue = "Evolution, Air Cooled"
        if request.lower() == "fueltype":
            ReturnValue = "Propane"

        if not len(GStartInfo):
            return ReturnValue

        if request.lower() == "controller":
            return GStartInfo["Controller"]
        if request.lower() == "fueltype":
            return GStartInfo["fueltype"]
    except Exception as e1:
        LogErrorLine("Error in GetControllerInfo: " + str(e1))
        pass

    return ReturnValue


# -------------------------------------------------------------------------------
def CacheToolTips():

    global CachedToolTips
    global ControllerType
    global CachedRegisterDescriptions

    try:

        foundRegText = False
        config_section = "generac_evo_nexus"
        pathtofile = os.path.dirname(os.path.realpath(__file__))
        try:
            data = MyClientInterface.ProcessMonitorCommand("generator: getreglabels_json")
            regdata = json.loads(data)
            if len(regdata):
                CachedRegisterDescriptions = regdata
                foundRegText = True
        except Exception as e1:
            LogErrorLine("Error in CacheToolTips reading reg data")

        # get controller used
        if ConfigFiles[GENMON_CONFIG].HasOption("controllertype"):
            config_section = ConfigFiles[GENMON_CONFIG].ReadValue("controllertype")
        else:
            config_section = "generac_evo_nexus"

        if not len(config_section):
            config_section = "generac_evo_nexus"

        # H_100
        ControllerType = config_section

        if ControllerType == "h_100":
            try:
                if (
                    len(GStartInfo["Controller"])
                    and not "H-100" in GStartInfo["Controller"]
                ):
                    # Controller is G-Panel
                    config_section = "g_panel"

            except Exception as e1:
                LogError("Error reading Controller Type for H-100: " + str(e1))
        if not foundRegText:
            CachedRegisterDescriptions = {"Holding":GetAllConfigValues(
                os.path.join(pathtofile, "data", "tooltips.txt"), config_section
            )}

        CachedToolTips = GetAllConfigValues(
            os.path.join(pathtofile, "data", "tooltips.txt"), "ToolTips"
        )

    except Exception as e1:
        LogErrorLine("Error reading tooltips.txt " + str(e1))


# -------------------------------------------------------------------------------
def GetToolTips(ConfigSettings):

    try:

        for entry, List in ConfigSettings.items():
            try:
                (ConfigSettings[entry])[4] = CachedToolTips[entry.lower()]
            except:
                # self.LogError("Error in GetToolTips: " + entry)
                pass  # TODO

    except Exception as e1:
        LogErrorLine("Error in GetToolTips: " + str(e1))


# -------------------------------------------------------------------------------
def SaveSettings(query_string):

    try:

        # e.g. {'displayunknown': ['true']}
        settings = dict(parse_qs(query_string, 1))
        if not len(settings):
            # nothing to change
            return
        CurrentConfigSettings = ReadSettingsFromFile()

        # --- Auth cascading rules ---
        # If username is removed, also clear password and disable MFA
        http_user = settings.get("http_user", [None])[0]
        if http_user is not None and http_user.strip() == "":
            settings["http_pass"] = [""]
            settings["usemfa"] = ["false"]
        # If password is missing but username is set, don't allow
        http_pass = settings.get("http_pass", [None])[0]
        if http_user is not None and http_user.strip() != "" and http_pass is not None and http_pass.strip() == "":
            LogError("SaveSettings: username set without password, clearing both")
            settings["http_user"] = [""]
            settings["http_pass"] = [""]
            settings["usemfa"] = ["false"]
        # Same for read-only account
        http_user_ro = settings.get("http_user_ro", [None])[0]
        if http_user_ro is not None and http_user_ro.strip() == "":
            settings["http_pass_ro"] = [""]

        changed = False
        with CriticalLock:
            for Entry in settings.keys():
                ConfigEntry = CurrentConfigSettings.get(Entry, None)
                if ConfigEntry != None:
                    ConfigFile = CurrentConfigSettings[Entry][6]
                    Value = settings[Entry][0]
                    Section = CurrentConfigSettings[Entry][7]
                    # CurrentConfigSettings[Entry][3] is the current value
                    CurrentValue = str(CurrentConfigSettings[Entry][3]) if CurrentConfigSettings[Entry][3] is not None else ""
                    # Normalize for comparison: JS sends 'true'/'false' lowercase,
                    # Python str(True) gives 'True' — case-insensitive compare
                    if Value.strip().lower() == CurrentValue.strip().lower():
                        continue  # skip unchanged settings to reduce SD card writes
                else:
                    LogError("Invalid setting: " + str(Entry))
                    continue
                UpdateConfigFile(ConfigFile, Section, Entry, Value)
                changed = True
        if changed:
            Restart()
    except Exception as e1:
        LogErrorLine("Error Update Config File (SaveSettings): " + str(e1))


# ---------------------MySupport::UpdateConfigFile-------------------------------
# Add or update config item
def UpdateConfigFile(FileName, section, Entry, Value):

    try:

        if FileName == None or section == None or Entry == None or Value == None:
            return False
        if FileName == "" or section == "" or Entry == "":
            return False
        try:
            config = ConfigFiles[FileName]
        except Exception as e1:
            LogErrorLine(
                "Unknow file in UpdateConfigFile: " + FileName + ": " + str(e1)
            )
            return False

        config.SetSection(section)
        return config.WriteValue(Entry, Value)

    except Exception as e1:
        LogErrorLine("Error Update Config File (UpdateConfigFile): " + str(e1))
        return False


# -------------------------------------------------------------------------------
# This will reboot the pi
def Reboot():

    subprocess.run(["sudo", "reboot"])


# -------------------------------------------------------------------------------
# This will shutdown the pi
def Shutdown():

    subprocess.run(["sudo", "shutdown", "-h"])



# -------------------------------------------------------------------------------
# This will restart the Flask App
def Restart():

    global Restarting

    try:
        Restarting = True
        threading.Thread(target=_do_restart, daemon=True).start()
    except Exception as e1:
        LogErrorLine("Error in Restart: " + str(e1))

# -------------------------------------------------------------------------------
# Separate thread to restart so the flask request will return
def _do_restart():
    time.sleep(2)
    if not RunBashScript("startgenmon.sh restart -c " + ConfigFilePath):
        LogError("Error in Restart")

# -------------------------------------------------------------------------------
def Update():
    # update
    try:
        if not RunBashScript("genmonmaint.sh -u -n", log = True):
            LogError("Error in Update")
        # now restart
        Restart()
    except Exception as e1:
        LogErrorLine("Error in Update: " + str(e1))


# -------------------------------------------------------------------------------
def GetLogs():
    # update
    if not RunBashScript("genmonmaint.sh -l " + loglocation):  # archive logs
        LogError("Error in GetLogs")


# -------------------------------------------------------------------------------
def Backup():
    # update
    if not RunBashScript("genmonmaint.sh -b -c " + ConfigFilePath):  # backup
        LogError("Error in Backup")


# -------------------------------------------------------------------------------
def RestoreBackup(ArchivePath):
    return RunBashScript("genmonmaint.sh -t " + ArchivePath + " -c " + ConfigFilePath)


# -------------------------------------------------------------------------------
def RunBashScript(ScriptName, log = False):
    
    global OperatingSystem

    try:
        
        if OperatingSystem == "windows":
            ScriptName = ScriptName.replace(".sh", ".bat")
            pathtoscript = os.path.dirname(os.path.realpath(__file__))
            command = os.path.join(pathtoscript, "OtherApps", "win",ScriptName)
        else:
            pathtoscript = os.path.dirname(os.path.realpath(__file__))
            script = os.path.join(pathtoscript, ScriptName)
            command = "/bin/bash "
            command = command + script
        LogError("Script: " + command)
        if log == False:
            subprocess.call(command, shell=True)
        else:
            try:
                output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as e:
                output = e.output.decode()

            if sys.version_info >= (3, 0):
                output = output.decode()
            LogError(command + ": \n" +  output)
        return True

    except Exception as e1:
        LogErrorLine("Error in RunBashScript: (" + ScriptName + ") : " + str(e1))
        return False


# -------------------------------------------------------------------------------
# return False if File not present
def CheckCertFiles(CertFile, KeyFile):

    try:
        if not os.path.isfile(CertFile):
            LogConsole("Missing cert file : " + CertFile)
            LogError("Missing cert file : " + CertFile)
            return False
        if not os.path.isfile(KeyFile):
            LogConsole("Missing key file : " + KeyFile)
            LogError("Missing key file : " + KeyFile)
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
def generate_local_ca(config_path):
    """Generate (or load existing) a local CA key + self-signed CA certificate.

    Files: {config_path}/ca.key, {config_path}/ca.crt
    Returns (ca_cert, ca_key) as OpenSSL objects.
    """
    from OpenSSL import crypto

    ca_key_path = os.path.join(config_path, "ca.key")
    ca_crt_path = os.path.join(config_path, "ca.crt")

    if os.path.isfile(ca_key_path) and os.path.isfile(ca_crt_path):
        with open(ca_key_path, "rb") as f:
            ca_key = crypto.load_privatekey(crypto.FILETYPE_PEM, f.read())
        with open(ca_crt_path, "rb") as f:
            ca_cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
        LogDebug("Local CA loaded from " + ca_crt_path)
        return ca_cert, ca_key

    # Generate new CA
    ca_key = crypto.PKey()
    ca_key.generate_key(crypto.TYPE_RSA, 2048)

    ca_cert = crypto.X509()
    ca_cert.set_version(2)  # X509v3
    ca_cert.set_serial_number(int.from_bytes(os.urandom(16), "big"))
    ca_cert.gmtime_adj_notBefore(0)
    ca_cert.gmtime_adj_notAfter(10 * 365 * 24 * 60 * 60)  # 10 years

    subj = ca_cert.get_subject()
    subj.CN = "Genmon Local CA"
    subj.O = "Genmon"
    ca_cert.set_issuer(subj)
    ca_cert.set_pubkey(ca_key)

    ca_cert.add_extensions(
        [
            crypto.X509Extension(b"basicConstraints", True, b"CA:TRUE, pathlen:0"),
            crypto.X509Extension(b"keyUsage", True, b"keyCertSign, cRLSign"),
            crypto.X509Extension(
                b"subjectKeyIdentifier", False, b"hash", subject=ca_cert
            ),
        ]
    )

    ca_cert.sign(ca_key, "sha256")

    with open(ca_key_path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, ca_key))
    os.chmod(ca_key_path, 0o600)
    with open(ca_crt_path, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, ca_cert))

    LogDebug("Local CA created: " + ca_crt_path)
    return ca_cert, ca_key


# -------------------------------------------------------------------------------
def _get_all_local_ips():
    """Return a set of all non-loopback IPv4 addresses on this machine.

    Tries multiple discovery methods so the server certificate SAN covers
    every address a browser might use to connect, even when the Pi has no
    internet access at startup.
    """
    import socket
    import subprocess

    ips = set()

    # Method 1: hostname -I  (Linux, most reliable on Raspberry Pi)
    try:
        out = subprocess.check_output(["hostname", "-I"], timeout=5,
                                      stderr=subprocess.DEVNULL).decode()
        for token in out.split():
            if ":" not in token:          # skip IPv6
                ips.add(token.strip())
    except Exception:
        pass

    # Method 2: getaddrinfo on the local hostname
    try:
        hn = socket.gethostname()
        for info in socket.getaddrinfo(hn, None):
            addr = info[4][0]
            if addr and not addr.startswith("127.") and ":" not in addr:
                ips.add(addr)
    except Exception:
        pass

    # Method 3: UDP connect trick (finds default-route LAN IP)
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    ips.discard("127.0.0.1")
    return ips


# -------------------------------------------------------------------------------
def generate_server_cert(ca_cert, ca_key, config_path):
    """Generate (or reuse) a server certificate signed by the local CA.

    Files: {config_path}/server.key, {config_path}/server.crt
    Auto-regenerates if missing or expiring within 30 days.
    Returns (server_crt_path, server_key_path) file paths.
    """
    import datetime
    import socket

    from OpenSSL import crypto

    srv_key_path = os.path.join(config_path, "server.key")
    srv_crt_path = os.path.join(config_path, "server.crt")

    regen = False
    if not os.path.isfile(srv_key_path) or not os.path.isfile(srv_crt_path):
        regen = True
    else:
        # Check expiry and required extensions
        try:
            with open(srv_crt_path, "rb") as f:
                existing = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
            expiry_str = existing.get_notAfter()
            if expiry_str is not None:
                expiry = datetime.datetime.strptime(
                    expiry_str.decode("ascii"), "%Y%m%d%H%M%SZ"
                )
                if expiry - datetime.datetime.utcnow() < datetime.timedelta(days=30):
                    LogDebug("Server cert expiring soon, regenerating.")
                    regen = True
            # Check for required extensions (added in v2)
            has_eku = False
            has_san = False
            existing_san = ""
            for i in range(existing.get_extension_count()):
                ext = existing.get_extension(i)
                sn = ext.get_short_name()
                if sn == b"extendedKeyUsage":
                    has_eku = True
                if sn == b"subjectAltName":
                    has_san = True
                    existing_san = str(ext)
            if not has_eku:
                LogDebug("Server cert missing extendedKeyUsage, regenerating.")
                regen = True
            elif not has_san:
                LogDebug("Server cert missing subjectAltName, regenerating.")
                regen = True
            else:
                # Log any IPs not covered by the SAN but do NOT
                # regenerate — that would invalidate every browser
                # that already trusts the current cert and leave the
                # user stuck on a spinner after a settings-save restart.
                local_ips = _get_all_local_ips()
                missing = [a for a in local_ips if a not in existing_san]
                if missing:
                    LogDebug(
                        "Note: IP(s) " + ", ".join(sorted(missing))
                        + " not in server cert SAN.  Cert kept to preserve"
                        + " browser trust.  Re-enable HTTPS in settings to"
                        + " force a new certificate."
                    )
        except Exception:
            regen = True

    if not regen:
        LogDebug("Server cert reused: " + srv_crt_path)
        return srv_crt_path, srv_key_path

    # Build SAN list
    san_entries = set()
    san_entries.add("DNS:localhost")
    try:
        hn = socket.gethostname()
        if hn:
            san_entries.add("DNS:" + hn)
            san_entries.add("DNS:" + hn + ".local")   # mDNS / Avahi
        try:
            fqdn = socket.getfqdn()
            if fqdn and fqdn != hn:
                san_entries.add("DNS:" + fqdn)
        except Exception:
            pass
    except Exception:
        pass
    for addr in _get_all_local_ips():
        san_entries.add("IP:" + addr)
    san_entries.add("IP:127.0.0.1")
    san_string = ", ".join(sorted(san_entries))

    srv_key = crypto.PKey()
    srv_key.generate_key(crypto.TYPE_RSA, 2048)

    srv_cert = crypto.X509()
    srv_cert.set_version(2)
    srv_cert.set_serial_number(int.from_bytes(os.urandom(16), "big"))
    srv_cert.gmtime_adj_notBefore(0)
    srv_cert.gmtime_adj_notAfter(365 * 24 * 60 * 60)  # 1 year

    subj = srv_cert.get_subject()
    subj.CN = socket.gethostname() if socket.gethostname() else "genmon"
    subj.O = "Genmon"
    srv_cert.set_issuer(ca_cert.get_subject())
    srv_cert.set_pubkey(srv_key)

    srv_cert.add_extensions(
        [
            crypto.X509Extension(b"basicConstraints", False, b"CA:FALSE"),
            crypto.X509Extension(
                b"keyUsage", True, b"digitalSignature, keyEncipherment"
            ),
            crypto.X509Extension(
                b"extendedKeyUsage", False, b"serverAuth"
            ),
            crypto.X509Extension(
                b"subjectAltName", False, san_string.encode("ascii")
            ),
            crypto.X509Extension(
                b"authorityKeyIdentifier", False, b"keyid:always",
                issuer=ca_cert,
            ),
        ]
    )

    srv_cert.sign(ca_key, "sha256")

    with open(srv_key_path, "wb") as f:
        f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, srv_key))
    os.chmod(srv_key_path, 0o600)
    with open(srv_crt_path, "wb") as f:
        f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, srv_cert))

    LogDebug("Server cert generated: " + srv_crt_path + " SAN=" + san_string)
    return srv_crt_path, srv_key_path


# -------------------------------------------------------------------------------
def _get_cert_info():
    """Return a JSON string with certificate status info for the UI."""
    import json as _json

    info = {"mode": CertMode}
    try:
        if CertMode == "selfsigned":
            info["detail"] = "Ephemeral \u2014 regenerated on each restart"
        elif CertMode == "localca":
            ca_path = os.path.join(ConfigFilePath, "ca.crt")
            srv_path = os.path.join(ConfigFilePath, "server.crt")
            if os.path.isfile(ca_path):
                from OpenSSL import crypto
                import datetime

                with open(ca_path, "rb") as f:
                    ca = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
                info["ca_cn"] = ca.get_subject().CN or ""
                nb = ca.get_notBefore()
                if nb:
                    info["ca_created"] = datetime.datetime.strptime(
                        nb.decode("ascii"), "%Y%m%d%H%M%SZ"
                    ).strftime("%Y-%m-%d")
            if os.path.isfile(srv_path):
                from OpenSSL import crypto
                import datetime

                with open(srv_path, "rb") as f:
                    srv = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
                na = srv.get_notAfter()
                if na:
                    info["srv_expiry"] = datetime.datetime.strptime(
                        na.decode("ascii"), "%Y%m%d%H%M%SZ"
                    ).strftime("%Y-%m-%d")
                # Extract SAN
                for i in range(srv.get_extension_count()):
                    ext = srv.get_extension(i)
                    if ext.get_short_name() == b"subjectAltName":
                        info["san"] = str(ext)
                        break
        elif CertMode == "custom":
            cert_file = ConfigFiles[GENMON_CONFIG].ReadValue("certfile") if GENMON_CONFIG in ConfigFiles else ""
            key_file = ConfigFiles[GENMON_CONFIG].ReadValue("keyfile") if GENMON_CONFIG in ConfigFiles else ""
            info["certfile"] = cert_file or ""
            info["keyfile"] = key_file or ""
            if cert_file and os.path.isfile(cert_file):
                from OpenSSL import crypto
                import datetime

                with open(cert_file, "rb") as f:
                    c = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
                na = c.get_notAfter()
                if na:
                    info["expiry"] = datetime.datetime.strptime(
                        na.decode("ascii"), "%Y%m%d%H%M%SZ"
                    ).strftime("%Y-%m-%d")
    except Exception as e1:
        info["error"] = str(e1)
    return _json.dumps(info)


# -------------------------------------------------------------------------------
def generate_adhoc_ssl_context():
    # Generates an adhoc SSL context for the web server.
    try:
        import ssl

        try:
            from werkzeug.serving import generate_adhoc_ssl_context as _wz_ctx
            return _wz_ctx()
        except Exception as e1:
            LogErrorLine("generate_adhoc_ssl_context: " + str(e1))

        # Fallback: try pyOpenSSL-based generation
        import atexit
        import tempfile
        from random import random

        from OpenSSL import crypto

        cert = crypto.X509()
        cert.set_serial_number(int(random() * sys.maxsize))
        cert.gmtime_adj_notBefore(0)
        cert.gmtime_adj_notAfter(60 * 60 * 24 * 365)

        subject = cert.get_subject()
        subject.CN = "*"
        subject.O = "Dummy Certificate"

        issuer = cert.get_issuer()
        issuer.CN = "Untrusted Authority"
        issuer.O = "Self-Signed"

        pkey = crypto.PKey()
        pkey.generate_key(crypto.TYPE_RSA, 2048)
        cert.set_pubkey(pkey)
        cert.sign(pkey, "sha256")

        cert_handle, cert_file = tempfile.mkstemp()
        pkey_handle, pkey_file = tempfile.mkstemp()
        atexit.register(os.remove, pkey_file)
        atexit.register(os.remove, cert_file)

        os.write(cert_handle, crypto.dump_certificate(crypto.FILETYPE_PEM, cert))
        os.write(pkey_handle, crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
        os.close(cert_handle)
        os.close(pkey_handle)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.load_cert_chain(cert_file, pkey_file)
        return ctx
    except Exception as e1:
        LogError("Error in generate_adhoc_ssl_context: " + str(e1))
        return None


# -------------------------------------------------------------------------------
def generate_persistent_selfsigned(config_path):
    """Generate (or load existing) a persistent self-signed certificate.

    Files: {config_path}/selfsigned.key, {config_path}/selfsigned.crt
    Returns an ssl.SSLContext, or None on failure.
    """
    import ssl

    from OpenSSL import crypto

    key_path = os.path.join(config_path, "selfsigned.key")
    crt_path = os.path.join(config_path, "selfsigned.crt")

    need_generate = False
    if os.path.isfile(key_path) and os.path.isfile(crt_path):
        try:
            with open(crt_path, "rb") as f:
                cert = crypto.load_certificate(crypto.FILETYPE_PEM, f.read())
            if cert.has_expired():
                LogError("Self-signed certificate expired, regenerating.")
                need_generate = True
            else:
                LogDebug("Persistent self-signed cert loaded from " + crt_path)
        except Exception as e1:
            LogErrorLine("Error loading self-signed cert, regenerating: " + str(e1))
            need_generate = True
    else:
        need_generate = True

    if need_generate:
        try:
            pkey = crypto.PKey()
            pkey.generate_key(crypto.TYPE_RSA, 2048)

            cert = crypto.X509()
            cert.set_serial_number(int.from_bytes(os.urandom(16), "big"))
            cert.gmtime_adj_notBefore(0)
            cert.gmtime_adj_notAfter(60 * 60 * 24 * 365)  # 1 year

            subject = cert.get_subject()
            subject.CN = "*"
            subject.O = "Genmon Self-Signed"

            cert.set_issuer(subject)
            cert.set_pubkey(pkey)
            cert.sign(pkey, "sha256")

            with open(key_path, "wb") as f:
                f.write(crypto.dump_privatekey(crypto.FILETYPE_PEM, pkey))
            os.chmod(key_path, 0o600)
            with open(crt_path, "wb") as f:
                f.write(crypto.dump_certificate(crypto.FILETYPE_PEM, cert))

            LogDebug("Persistent self-signed cert created: " + crt_path)
        except Exception as e1:
            LogError("Error generating persistent self-signed cert: " + str(e1))
            return None

    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        ctx.load_cert_chain(crt_path, key_path)
        return ctx
    except Exception as e1:
        LogError("Error loading persistent self-signed cert into SSLContext: " + str(e1))
        return None


# -------------------------------------------------------------------------------
def LoadConfig():

    global log
    global clientport
    global loglocation
    global bUseMFA
    global bMfaEnrolled
    global SecretMFAKey
    global bUseSecureHTTP
    global LdapServer
    global LdapBase
    global DomainNetbios
    global LdapAdminGroup
    global LdapReadOnlyGroup

    global ListenIPAddress
    global HTTPPort
    global OldHTTPPort
    global HTTPAuthUser
    global HTTPAuthPass
    global HTTPAuthUser_RO
    global HTTPAuthPass_RO
    global SSLContext
    global favicon
    global MaxLoginAttempts
    global LockOutDuration
    global RememberMeDays
    global MfaTrustDays
    global bMfaTrustExtend
    global debug

    HTTPAuthPass = None
    HTTPAuthUser = None
    SSLContext = None
    LdapServer = None
    LdapBase = None
    DomainNetbios = None
    LdapAdminGroup = None
    LdapReadOnlyGroup = None

    try:

        debug = ConfigFiles[GENMON_CONFIG].ReadValue(
            "debug", return_type=bool, default=False
        )
        # heartbeat server port, must match value in check_generator_system.py and any calling client apps
        if ConfigFiles[GENMON_CONFIG].HasOption("server_port"):
            clientport = ConfigFiles[GENMON_CONFIG].ReadValue(
                "server_port", return_type=int, default=ProgramDefaults.ServerPort
            )

        bUseMFA = ConfigFiles[GENMON_CONFIG].ReadValue(
            "usemfa", return_type=bool, default=False
        )
        bMfaEnrolled = ConfigFiles[GENMON_CONFIG].ReadValue(
            "mfa_enrolled", return_type=bool, default=False
        )
        # Migration: if MFA was already enabled before the enrolled flag
        # existed, mark it as enrolled so the QR code stays hidden.
        if bUseMFA and not bMfaEnrolled:
            bMfaEnrolled = True
            ConfigFiles[GENMON_CONFIG].WriteValue("mfa_enrolled", "True")
        # If MFA was disabled, clear enrollment and rotate the secret so
        # re-enabling MFA forces a fresh QR scan.
        if not bUseMFA and bMfaEnrolled:
            bMfaEnrolled = False
            ConfigFiles[GENMON_CONFIG].WriteValue("mfa_enrolled", "False")
            SecretMFAKey = str(pyotp.random_base32())
            ConfigFiles[GENMON_CONFIG].WriteValue("secretmfa", str(SecretMFAKey))
        # Always read/generate the secret key and build the provisioning
        # URL so the QR code is ready to display in settings even before
        # the user enables MFA.
        if SecretMFAKey is None:
            SecretMFAKey = ConfigFiles[GENMON_CONFIG].ReadValue("secretmfa", default=None)

        if SecretMFAKey == None or SecretMFAKey == "":
            SecretMFAKey = str(pyotp.random_base32())
            ConfigFiles[GENMON_CONFIG].WriteValue("secretmfa", str(SecretMFAKey))

        SetupMFA()

        if ConfigFiles[GENMON_CONFIG].HasOption("usehttps"):
            bUseSecureHTTP = ConfigFiles[GENMON_CONFIG].ReadValue(
                "usehttps", return_type=bool
            )
        if not bUseSecureHTTP:
            # dont use MFA unless HTTPS is enabled
            bUseMFA = False

        ListenIPAddress = ConfigFiles[GENMON_CONFIG].ReadValue("flask_listen_ip_address", default="0.0.0.0")
        
        if ConfigFiles[GENMON_CONFIG].HasOption("http_port"):
            HTTPPort = ConfigFiles[GENMON_CONFIG].ReadValue(
                "http_port", return_type=int, default=8000
            )

        if ConfigFiles[GENMON_CONFIG].HasOption("favicon"):
            favicon = ConfigFiles[GENMON_CONFIG].ReadValue("favicon")

        MaxLoginAttempts = ConfigFiles[GENMON_CONFIG].ReadValue(
            "max_login_attempts", return_type=int, default=5
        )
        LockOutDuration = ConfigFiles[GENMON_CONFIG].ReadValue(
            "login_lockout_seconds", return_type=int, default=(5 * 60)
        )

        # user name and password require usehttps = True
        if bUseSecureHTTP:
            if ConfigFiles[GENMON_CONFIG].HasOption("ldap_server"):
                LdapServer = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "ldap_server", default=""
                )
                LdapServer = LdapServer.strip()
                if LdapServer == "":
                    LdapServer = None
                else:
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_base"):
                        LdapBase = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_base", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("domain_netbios"):
                        DomainNetbios = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "domain_netbios", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_admingroup"):
                        LdapAdminGroup = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_admingroup", default=""
                        )
                    if ConfigFiles[GENMON_CONFIG].HasOption("ldap_readonlygroup"):
                        LdapReadOnlyGroup = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "ldap_readonlygroup", default=""
                        )
                    if LdapBase == "":
                        LdapBase = None
                    if DomainNetbios == "":
                        DomainNetbios = None
                    if LdapAdminGroup == "":
                        LdapAdminGroup = None
                    if LdapReadOnlyGroup == "":
                        LdapReadOnlyGroup = None
                    if (
                        LdapReadOnlyGroup == None
                        and LdapAdminGroup == None
                        or LdapBase == None
                        or DomainNetbios == None
                    ):
                        LdapServer = None

            if ConfigFiles[GENMON_CONFIG].HasOption("http_user"):
                HTTPAuthUser = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "http_user", default=""
                )
                HTTPAuthUser = HTTPAuthUser.strip()
                # No user name or pass specified, disable
                if HTTPAuthUser == "":
                    HTTPAuthUser = None
                    HTTPAuthPass = None
                elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass"):
                    HTTPAuthPass = ConfigFiles[GENMON_CONFIG].ReadValue(
                        "http_pass", default=""
                    )
                    HTTPAuthPass = HTTPAuthPass.strip()
                if HTTPAuthUser != None and HTTPAuthPass != None:
                    if ConfigFiles[GENMON_CONFIG].HasOption("http_user_ro"):
                        HTTPAuthUser_RO = ConfigFiles[GENMON_CONFIG].ReadValue(
                            "http_user_ro", default=""
                        )
                        HTTPAuthUser_RO = HTTPAuthUser_RO.strip()
                        if HTTPAuthUser_RO == "":
                            HTTPAuthUser_RO = None
                            HTTPAuthPass_RO = None
                        elif ConfigFiles[GENMON_CONFIG].HasOption("http_pass_ro"):
                            HTTPAuthPass_RO = ConfigFiles[GENMON_CONFIG].ReadValue(
                                "http_pass_ro", default=""
                            )
                            HTTPAuthPass_RO = HTTPAuthPass_RO.strip()

            HTTPSPort = ConfigFiles[GENMON_CONFIG].ReadValue(
                "https_port", return_type=int, default=443
            )

        # --- persistent secret key (survives restarts) ---
        # Rotate the key when the auth mode changes (e.g. HTTP→HTTPS)
        # so stale session cookies from a previous mode are invalidated.
        stored_key = ConfigFiles[GENMON_CONFIG].ReadValue("secret_key", default="")
        current_auth_mode = "auth" if (bUseSecureHTTP and LoginActive()) else "open"
        stored_auth_mode = ConfigFiles[GENMON_CONFIG].ReadValue("secret_key_auth_mode", default="")
        if not stored_key or stored_auth_mode != current_auth_mode:
            stored_key = secrets.token_hex(24)
            ConfigFiles[GENMON_CONFIG].WriteValue("secret_key", stored_key)
            ConfigFiles[GENMON_CONFIG].WriteValue("secret_key_auth_mode", current_auth_mode)
        app.secret_key = bytes.fromhex(stored_key)

        # --- session cookie hardening ---
        app.config["SESSION_COOKIE_SECURE"] = True  # always set; harmless if not HTTPS
        app.config["SESSION_COOKIE_HTTPONLY"] = True
        app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

        # --- remember-me / session lifetime ---
        # Seed defaults for new settings so existing installs get them in the config
        if not ConfigFiles[GENMON_CONFIG].HasOption("remember_me_days"):
            ConfigFiles[GENMON_CONFIG].WriteValue("remember_me_days", "0")
        if not ConfigFiles[GENMON_CONFIG].HasOption("mfa_trust_extend"):
            ConfigFiles[GENMON_CONFIG].WriteValue("mfa_trust_extend", "False")
        if not ConfigFiles[GENMON_CONFIG].HasOption("mfa_trust_days"):
            ConfigFiles[GENMON_CONFIG].WriteValue("mfa_trust_days", "90")

        RememberMeDays = ConfigFiles[GENMON_CONFIG].ReadValue(
            "remember_me_days", return_type=int, default=0
        )
        if RememberMeDays > 0:
            app.permanent_session_lifetime = datetime.timedelta(days=RememberMeDays)

        # --- MFA trust browser ---
        MfaTrustDays = ConfigFiles[GENMON_CONFIG].ReadValue(
            "mfa_trust_days", return_type=int, default=90
        )
        bMfaTrustExtend = ConfigFiles[GENMON_CONFIG].ReadValue(
            "mfa_trust_extend", return_type=bool, default=False
        )

        if bUseSecureHTTP:
            OldHTTPPort = HTTPPort
            HTTPPort = HTTPSPort
            LogDebug("HTTPS enabled: will redirect HTTP port " + str(OldHTTPPort) + " -> HTTPS port " + str(HTTPPort))

            # --- cert_mode migration (backward compat) ---
            # DEPRECATED: "useselfsignedcert" (bool) was replaced by "cert_mode"
            # (selfsigned | localca | custom) in March 2026.  This block converts
            # the old setting on first run so existing installs upgrade seamlessly.
            # After the first start cert_mode is written to the config and this
            # migration path is never taken again.  The UI now exposes cert_mode
            # only — do NOT remove this block while any user might still have
            # useselfsignedcert in their genmon.conf.
            if not ConfigFiles[GENMON_CONFIG].HasOption("cert_mode"):
                if ConfigFiles[GENMON_CONFIG].HasOption("useselfsignedcert"):
                    old = ConfigFiles[GENMON_CONFIG].ReadValue(
                        "useselfsignedcert", return_type=bool
                    )
                    CertMode = "selfsigned" if old else "custom"
                else:
                    CertMode = "selfsigned"
                ConfigFiles[GENMON_CONFIG].WriteValue("cert_mode", CertMode)
            else:
                CertMode = ConfigFiles[GENMON_CONFIG].ReadValue(
                    "cert_mode", default="selfsigned"
                )
                if CertMode not in ("selfsigned", "localca", "custom"):
                    CertMode = "selfsigned"

            if CertMode == "selfsigned":
                SSLContext = generate_persistent_selfsigned(ConfigFilePath)
                if SSLContext is None:
                    SSLContext = generate_adhoc_ssl_context()
                    if SSLContext is None:
                        SSLContext = "adhoc"
            elif CertMode == "localca":
                try:
                    ca_cert, ca_key = generate_local_ca(ConfigFilePath)
                    srv_crt, srv_key = generate_server_cert(
                        ca_cert, ca_key, ConfigFilePath
                    )
                    SSLContext = (srv_crt, srv_key)
                except Exception as e1:
                    LogErrorLine("Error setting up Local CA cert: " + str(e1))
                    SSLContext = generate_adhoc_ssl_context()
                    if SSLContext is None:
                        SSLContext = "adhoc"
            elif CertMode == "custom":
                if ConfigFiles[GENMON_CONFIG].HasOption("certfile") and ConfigFiles[
                    GENMON_CONFIG
                ].HasOption("keyfile"):
                    CertFile = ConfigFiles[GENMON_CONFIG].ReadValue("certfile")
                    KeyFile = ConfigFiles[GENMON_CONFIG].ReadValue("keyfile")
                    if CheckCertFiles(CertFile, KeyFile):
                        SSLContext = (CertFile, KeyFile)
                    else:
                        LogError("Missing key / cert files: reverting to self signed cert.")
                        SSLContext = generate_adhoc_ssl_context()
                        if SSLContext is None:
                            SSLContext = "adhoc"
                else:
                    LogError("Custom cert files not configured, falling back to self-signed")
                    SSLContext = generate_adhoc_ssl_context()
                    if SSLContext is None:
                        SSLContext = "adhoc"

        return True
    except Exception as e1:
        LogError("Missing config file or config file entries: " + str(e1))
        return False


# ---------------------ValidateOTP-----------------------------------------------
def ValidateOTP(password):

    if bUseMFA:
        try:
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30)
            # valid_window=2 accepts codes from ±2 time steps (covers ~2 min)
            # so email-delivered codes remain valid while the user reads & types.
            return TimeOTP.verify(password, valid_window=2)
        except Exception as e1:
            LogErrorLine("Error in ValidateOTP: " + str(e1))
    return False


# ---------------------GetOTP----------------------------------------------------
def GetOTP():
    try:
        if bUseMFA:
            TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30)
            OTP = TimeOTP.now()
            msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
            mail.sendEmail("Generator Monitor login one time password", msgbody)
            return OTP
    except Exception as e1:
        LogErrorLine("Error in GetOTP: " + str(e1))


# ---------------------MFA setup verify & reset----------------------------------
@app.route("/mfa/verify_setup", methods=["POST"])
def mfa_verify_setup():
    """Verify a TOTP code during initial enrollment and mark MFA as enrolled."""
    global bMfaEnrolled
    try:
        if not session.get("logged_in") or not session.get("write_access"):
            return jsonify(status="error", msg="Unauthorized"), 403
        code = (request.json or {}).get("code", "").strip()
        if not code or len(code) != 6 or not code.isdigit():
            return jsonify(status="error", msg="Enter a 6-digit code"), 400
        totp = pyotp.TOTP(SecretMFAKey, interval=30)
        if totp.verify(code, valid_window=1):
            bMfaEnrolled = True
            ConfigFiles[GENMON_CONFIG].WriteValue("mfa_enrolled", "True")
            return jsonify(status="ok")
        return jsonify(status="error", msg="Code incorrect. Check your authenticator and try again.")
    except Exception as e1:
        LogErrorLine("Error in mfa_verify_setup: " + str(e1))
        return jsonify(status="error", msg="Verification failed"), 500


# ---------------------send_otp route--------------------------------------------
@app.route("/send_otp", methods=["POST"])
def send_otp():
    global LastOTPSendTime
    try:
        if not session.get("logged_in"):
            return jsonify(status="error", msg="Not authorized"), 403
        if mail is None:
            return jsonify(status="error", msg="Email is not configured"), 500
        if mail.DisableEmail or mail.DisableSMTP:
            return jsonify(status="error", msg="Email sending is disabled in config"), 500
        with CriticalLock:  # thread-safe rate limiting to prevent concurrent bypass
            now = time.time()
            if LastOTPSendTime and (now - LastOTPSendTime) < 60:
                return jsonify(status="error", msg="Please wait before requesting another code")
            LastOTPSendTime = now
        if not bUseMFA:
            return jsonify(status="error", msg="MFA is not enabled"), 400
        TimeOTP = pyotp.TOTP(SecretMFAKey, interval=30)
        OTP = TimeOTP.now()
        msgbody = "\nThis password will expire in 30 seconds: " + str(OTP)
        # Send synchronously so SMTP errors are reported to the user
        sent = mail.sendEmailDirectMIME(
            "error",
            "Generator Monitor login one time password",
            msgbody,
        )
        if not sent:
            return jsonify(status="error", msg="SMTP send failed — check email settings and server logs")
        return jsonify(status="ok")
    except Exception as e1:
        LogErrorLine("Error in send_otp: " + str(e1))
        return jsonify(status="error", msg="Failed to send code"), 500  # generic; details logged server-side only


# ---------------------Backup Codes----------------------------------------------
def _backup_codes_path():
    return os.path.join(ConfigFilePath, "backup_codes.json")


def _load_backup_codes():
    path = _backup_codes_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_backup_codes(data):
    path = _backup_codes_path()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(path, 0o600)  # owner-only; contains hashed backup codes
    except OSError:
        pass  # Windows doesn't support POSIX permissions


def _hash_code(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def GenerateBackupCodes(username):
    codes = [secrets.token_hex(4) for _ in range(10)]
    hashed = [_hash_code(c) for c in codes]
    data = _load_backup_codes()
    data[username.lower()] = hashed
    _save_backup_codes(data)
    return codes


def _validate_backup_code(username, code):
    data = _load_backup_codes()
    user = username.lower()
    user_codes = data.get(user, [])
    h = _hash_code(code.lower())
    if h in user_codes:
        user_codes.remove(h)
        data[user] = user_codes
        _save_backup_codes(data)
        return True
    return False


@app.route("/backup_codes/generate", methods=["POST"])
def generate_backup_codes():
    try:
        if not session.get("logged_in") or not session.get("write_access"):
            return jsonify(status="error", msg="Unauthorized"), 403
        username = session.get("username", "")
        codes = GenerateBackupCodes(username)
        return jsonify(status="ok", codes=codes)
    except Exception as e1:
        LogErrorLine("Error in generate_backup_codes: " + str(e1))
        return jsonify(status="error", msg="Failed to generate codes"), 500


@app.route("/backup_codes/count", methods=["GET"])
def backup_codes_count():
    try:
        if not session.get("logged_in"):
            return jsonify(status="error", msg="Unauthorized"), 403
        username = session.get("username", "")
        data = _load_backup_codes()
        remaining = len(data.get(username.lower(), []))
        return jsonify(status="ok", count=remaining)
    except Exception as e1:
        LogErrorLine("Error in backup_codes_count: " + str(e1))
        return jsonify(status="error", msg="Error"), 500


# ---------------------Passkey WebAuthn------------------------------------------
PASSKEYS_PATH = None

def _passkeys_path():
    global PASSKEYS_PATH
    if PASSKEYS_PATH is None:
        PASSKEYS_PATH = os.path.join(ConfigFilePath, "passkeys.json")
    return PASSKEYS_PATH


def _load_passkeys():
    path = _passkeys_path()
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_passkeys(data):
    path = _passkeys_path()
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    try:
        os.chmod(path, 0o600)  # owner-only; contains passkey public keys
    except OSError:
        pass  # Windows doesn't support POSIX permissions


@app.route("/passkey/register/begin", methods=["POST"])
def passkey_register_begin():
    try:
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        if not session.get("logged_in") or not session.get("write_access"):
            return jsonify(error="Unauthorized"), 403
        from webauthn import generate_registration_options, options_to_json
        from webauthn.helpers.structs import (
            AuthenticatorSelectionCriteria,
            ResidentKeyRequirement,
            UserVerificationRequirement,
        )
        import base64
        username = session.get("username", "admin")
        user_id = hashlib.sha256(username.encode()).digest()
        rp_id = request.host.split(":")[0]
        existing = _load_passkeys().get(username.lower(), [])
        exclude_creds = []
        for pk in existing:
            from webauthn.helpers.structs import PublicKeyCredentialDescriptor
            exclude_creds.append(PublicKeyCredentialDescriptor(id=base64.urlsafe_b64decode(pk["credential_id"] + "==")))
        options = generate_registration_options(
            rp_id=rp_id,
            rp_name="Genmon",
            user_id=user_id,
            user_name=username,
            user_display_name=username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=exclude_creds,
        )
        session["webauthn_reg_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
        return app.response_class(options_to_json(options), mimetype="application/json")
    except Exception as e1:
        LogErrorLine("Error in passkey_register_begin: " + str(e1))
        return jsonify(error="Registration failed"), 500


@app.route("/passkey/register/complete", methods=["POST"])
def passkey_register_complete():
    try:
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        if not session.get("logged_in") or not session.get("write_access"):
            return jsonify(error="Unauthorized"), 403
        from webauthn import verify_registration_response
        import base64
        username = session.get("username", "admin")
        rp_id = request.host.split(":")[0]
        challenge_b64 = session.pop("webauthn_reg_challenge", None)
        if not challenge_b64:
            return jsonify(error="No pending registration"), 400
        # Restore padding
        challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
        expected_challenge = base64.urlsafe_b64decode(challenge_b64)
        body = request.get_json()
        verification = verify_registration_response(
            credential=body,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=request.host_url.rstrip("/"),
        )
        cred_id_b64 = base64.urlsafe_b64encode(verification.credential_id).decode().rstrip("=")
        public_key_b64 = base64.urlsafe_b64encode(verification.credential_public_key).decode().rstrip("=")
        data = _load_passkeys()
        user_keys = data.get(username.lower(), [])
        passkey_name = body.get("name", "Passkey " + str(len(user_keys) + 1))
        user_keys.append({
            "credential_id": cred_id_b64,
            "public_key": public_key_b64,
            "sign_count": verification.sign_count,
            "name": passkey_name,
        })
        data[username.lower()] = user_keys
        _save_passkeys(data)
        return jsonify(status="ok", name=passkey_name)
    except Exception as e1:
        LogErrorLine("Error in passkey_register_complete: " + str(e1))
        return jsonify(error="Registration verification failed"), 500


@app.route("/passkey/auth/begin", methods=["POST"])
def passkey_auth_begin():
    try:
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
        import base64
        username = session.get("username", "")
        data = _load_passkeys()
        user_keys = data.get(username.lower(), [])
        if not user_keys:
            return jsonify(error="No passkeys registered"), 400
        allow_creds = []
        for pk in user_keys:
            allow_creds.append(PublicKeyCredentialDescriptor(
                id=base64.urlsafe_b64decode(pk["credential_id"] + "==")
            ))
        rp_id = request.host.split(":")[0]
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=allow_creds,
        )
        session["webauthn_auth_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
        return app.response_class(options_to_json(options), mimetype="application/json")
    except Exception as e1:
        LogErrorLine("Error in passkey_auth_begin: " + str(e1))
        return jsonify(error="Authentication failed"), 500


@app.route("/passkey/auth/complete", methods=["POST"])
def passkey_auth_complete():
    try:
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        from webauthn import verify_authentication_response
        import base64
        username = session.get("username", "")
        rp_id = request.host.split(":")[0]
        challenge_b64 = session.pop("webauthn_auth_challenge", None)
        if not challenge_b64:
            return jsonify(error="No pending authentication"), 400
        challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
        expected_challenge = base64.urlsafe_b64decode(challenge_b64)
        body = request.get_json()
        cred_id_raw = base64.urlsafe_b64decode(body.get("rawId", "") + "==")
        data = _load_passkeys()
        user_keys = data.get(username.lower(), [])
        matched_key = None
        for pk in user_keys:
            pk_id = base64.urlsafe_b64decode(pk["credential_id"] + "==")
            if pk_id == cred_id_raw:
                matched_key = pk
                break
        if not matched_key:
            return jsonify(error="Verification failed"), 400  # generic error to prevent credential enumeration
        public_key = base64.urlsafe_b64decode(matched_key["public_key"] + "==")
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=request.host_url.rstrip("/"),
            credential_public_key=public_key,
            credential_current_sign_count=matched_key.get("sign_count", 0),
        )
        matched_key["sign_count"] = verification.new_sign_count
        _save_passkeys(data)
        session["mfa_ok"] = True
        return jsonify(status="ok")
    except Exception as e1:
        LogErrorLine("Error in passkey_auth_complete: " + str(e1))
        return jsonify(error="Passkey verification failed"), 500


@app.route("/passkey/list", methods=["GET"])
def passkey_list():
    try:
        if not session.get("logged_in"):
            return jsonify(error="Unauthorized"), 403
        username = session.get("username", "")
        data = _load_passkeys()
        user_keys = data.get(username.lower(), [])
        result = [{"name": pk.get("name", "Passkey"), "credential_id": pk["credential_id"]} for pk in user_keys]
        return jsonify(status="ok", passkeys=result)
    except Exception as e1:
        LogErrorLine("Error in passkey_list: " + str(e1))
        return jsonify(error="Error"), 500


@app.route("/passkey/delete", methods=["POST"])
def passkey_delete():
    try:
        if not session.get("logged_in") or not session.get("write_access"):
            return jsonify(error="Unauthorized"), 403
        username = session.get("username", "")
        cred_id = request.get_json().get("credential_id", "")
        data = _load_passkeys()
        user_keys = data.get(username.lower(), [])
        data[username.lower()] = [pk for pk in user_keys if pk["credential_id"] != cred_id]
        _save_passkeys(data)
        return jsonify(status="ok")
    except Exception as e1:
        LogErrorLine("Error in passkey_delete: " + str(e1))
        return jsonify(error="Error"), 500


# ---------------------Passkey Login (passwordless from login page)--------------
def _find_user_by_credential(cred_id_raw):
    """Reverse-lookup: find username and passkey entry by raw credential ID."""
    import base64
    data = _load_passkeys()
    for username, keys in data.items():
        for pk in keys:
            pk_id = base64.urlsafe_b64decode(pk["credential_id"] + "==")
            if pk_id == cred_id_raw:
                return username, pk, data
    return None, None, data


@app.route("/passkey/login/begin", methods=["POST"])
def passkey_login_begin():
    try:
        if WebUILocked:  # shared lockout with password login
            return jsonify(error="Too many failed attempts, try again later"), 429
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor
        import base64
        # Gather ALL passkeys across all users for discoverable credential flow
        data = _load_passkeys()
        allow_creds = []
        for username, keys in data.items():
            for pk in keys:
                allow_creds.append(PublicKeyCredentialDescriptor(
                    id=base64.urlsafe_b64decode(pk["credential_id"] + "==")
                ))
        if not allow_creds:
            return jsonify(error="No passkeys registered"), 400
        rp_id = request.host.split(":")[0]
        options = generate_authentication_options(
            rp_id=rp_id,
            allow_credentials=allow_creds,
        )
        session["webauthn_login_challenge"] = base64.urlsafe_b64encode(options.challenge).decode().rstrip("=")
        return app.response_class(options_to_json(options), mimetype="application/json")
    except Exception as e1:
        LogErrorLine("Error in passkey_login_begin: " + str(e1))
        return jsonify(error="Authentication failed"), 500


@app.route("/passkey/login/complete", methods=["POST"])
def passkey_login_complete():
    try:
        if WebUILocked:  # shared lockout with password login
            return jsonify(error="Too many failed attempts, try again later"), 429
        CheckLockOutDuration()
        if not (bUseMFA and bUseSecureHTTP):
            return jsonify(error="Passkeys require MFA and HTTPS"), 400
        from webauthn import verify_authentication_response
        import base64
        rp_id = request.host.split(":")[0]
        challenge_b64 = session.pop("webauthn_login_challenge", None)
        if not challenge_b64:
            return jsonify(error="No pending authentication"), 400
        challenge_b64 += "=" * (4 - len(challenge_b64) % 4)
        expected_challenge = base64.urlsafe_b64decode(challenge_b64)
        body = request.get_json()
        cred_id_raw = base64.urlsafe_b64decode(body.get("rawId", "") + "==")
        username, matched_key, data = _find_user_by_credential(cred_id_raw)
        if not matched_key:
            return jsonify(error="Verification failed"), 400  # generic error to prevent credential enumeration
        public_key = base64.urlsafe_b64decode(matched_key["public_key"] + "==")
        verification = verify_authentication_response(
            credential=body,
            expected_challenge=expected_challenge,
            expected_rp_id=rp_id,
            expected_origin=request.host_url.rstrip("/"),
            credential_public_key=public_key,
            credential_current_sign_count=matched_key.get("sign_count", 0),
        )
        matched_key["sign_count"] = verification.new_sign_count
        _save_passkeys(data)
        # Determine access level from username
        write = username.lower() == HTTPAuthUser.lower() if HTTPAuthUser else False
        # Regenerate session to prevent session fixation
        session.clear()
        session["logged_in"] = True
        session["write_access"] = write
        session["mfa_ok"] = True
        session["username"] = username
        LogError("Passkey Login: " + username)
        return jsonify(status="ok")
    except Exception as e1:
        LogErrorLine("Error in passkey_login_complete: " + str(e1))
        CheckFailedLogin()
        return jsonify(error="Passkey verification failed"), 500


# ---------------------SetupMFA--------------------------------------------------
def SetupMFA():

    global MFA_URL
    global mail

    try:
        mail = MyMail(ConfigFilePath=ConfigFilePath, loglocation=loglocation)
        account = mail.SenderAccount
    except Exception as e1:
        LogErrorLine("Error setting up mail for 2FA (ConfigFilePath=" + str(ConfigFilePath) + "): " + str(e1))
        account = "genmon"
    try:
        MFA_URL = pyotp.totp.TOTP(SecretMFAKey).provisioning_uri(
            account, issuer_name="Genmon"
        )
    except Exception as e1:
        LogErrorLine("Error setting up 2FA: " + str(e1))


# ---------------------LogConsole------------------------------------------------
def LogConsole(Message):
    if not console == None:
        console.error(Message)


# ---------------------LogDebug-------------------------------------------------
def LogDebug(Message):
    global debug

    if debug == False:
        return
    if not log == None:
        log.error(Message)

# ---------------------LogError-------------------------------------------------
def LogError(Message):
    if not log == None:
        log.error(Message)


# ---------------------FatalError------------------------------------------------
def FatalError(Message):
    if not log == None:
        log.error(Message)
    raise Exception(Message)


# ---------------------LogErrorLine----------------------------------------------
def LogErrorLine(Message):
    if not log == None:
        LogError(Message + " : " + GetErrorLine())


# ---------------------GetErrorLine----------------------------------------------
def GetErrorLine():
    exc_type, exc_obj, exc_tb = sys.exc_info()
    fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    lineno = exc_tb.tb_lineno
    return fname + ":" + str(lineno)


# -------------------------------------------------------------------------------
def SignalClose(signum, frame):

    Close()


# -------------------------------------------------------------------------------
def Close():

    global Closing

    if Closing:
        return
    Closing = True
    try:
        if RedirectServer is not None:
            RedirectServer.shutdown()
    except Exception:
        pass
    try:
        MyClientInterface.Close()
    except Exception as e1:
        LogErrorLine("Error in close: " + str(e1))

    sys.exit(0)


# -------------------------------------------------------------------------------
if __name__ == "__main__":

    (
        console,
        ConfigFilePath,
        address,
        port,
        loglocation,
        log,
    ) = MySupport.SetupAddOnProgram("genserv")

    signal.signal(signal.SIGTERM, SignalClose)
    signal.signal(signal.SIGINT, SignalClose)

    MAIL_CONFIG = os.path.join(ConfigFilePath, "mymail.conf")
    GENMON_CONFIG = os.path.join(ConfigFilePath, "genmon.conf")
    GENLOADER_CONFIG = os.path.join(ConfigFilePath, "genloader.conf")
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
    GENHOMEASSISTANT_CONFIG = os.path.join(ConfigFilePath, "genhomeassistant.conf")
    GENHALINK_CONFIG = os.path.join(ConfigFilePath, "genhalink.conf")

    ConfigFileList = [
        GENMON_CONFIG,
        MAIL_CONFIG,
        GENLOADER_CONFIG,
        GENSMS_CONFIG,
        MYMODEM_CONFIG,
        GENPUSHOVER_CONFIG,
        GENMQTT_CONFIG,
        GENMQTTIN_CONFIG,
        GENSLACK_CONFIG,
        GENCALLMEBOT_CONFIG,
        GENGPIOIN_CONFIG,
        GENGPIOLEDBLINK_CONFIG,
        GENEXERCISE_CONFIG,
        GENEMAIL2SMS_CONFIG,
        GENTANKUTIL_CONFIG,
        GENCENTRICONNECT_CONFIG,
        GENTANKDIY_CONFIG,
        GENALEXA_CONFIG,
        GENSNMP_CONFIG,
        GENTEMP_CONFIG,
        GENCTHAT_CONFIG,
        GENMOPEKA_CONFIG,
        GENSMS_VOIP_CONFIG,
        GENHOMEASSISTANT_CONFIG,
        GENHALINK_CONFIG,
    ]

    for ConfigFile in ConfigFileList:
        if not os.path.isfile(ConfigFile):
            LogConsole("Missing config file : " + ConfigFile)
            sys.exit(1)

    ConfigFiles = {}
    for ConfigFile in ConfigFileList:
        if log == None:
            configlog = console
        else:
            configlog = log
        ConfigFiles[ConfigFile] = MyConfig(filename=ConfigFile, log=configlog)

    AppPath = sys.argv[0]
    if not LoadConfig():
        LogConsole("Error reading configuraiton file.")
        LogDebug("Error reading configuraiton file.")
        sys.exit(1)

    for ConfigFile in ConfigFileList:
        ConfigFiles[ConfigFile].log = log

    if MyPlatform.IsOSLinux():
        OperatingSystem = "linux"
    elif MyPlatform.IsOSWindows():
        OperatingSystem = "windows"
    else:
        OperatingSystem = "unknown"
        import platform
        LogError("Operating System: " +str(platform.system()))

    LogError(
        "Starting "
        + AppPath
        + ", Port:"
        + str(HTTPPort)
        + ", Secure HTTP: "
        + str(bUseSecureHTTP)
        + ", SelfSignedCert: "
        + str(CertMode)
        + ", UseMFA:"
        + str(bUseMFA)
        + ", OS:"
        + str(OperatingSystem)
        + ", Config:"
        + str(ConfigFilePath)
    )
    # validate needed files are present
    filename = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "startgenmon.sh"
    )
    if not os.path.isfile(filename):
        LogError("Required file missing : startgenmon.sh")
        sys.exit(1)

    filename = os.path.join(
        os.path.dirname(os.path.realpath(__file__)), "genmonmaint.sh"
    )
    if not os.path.isfile(filename):
        LogError("Required file missing : genmonmaint.sh")
        sys.exit(1)

    MyClientInterface = ClientInterface(host=address, port=clientport, log=log)

    Start = datetime.datetime.now()

    while (datetime.datetime.now() - Start).total_seconds() < 10:
        data = MyClientInterface.ProcessMonitorCommand("generator: gethealth")
        if "OK" in data:
            LogConsole(" OK - Init complete.")
            break

    try:
        data = MyClientInterface.ProcessMonitorCommand("generator: start_info_json")
        GStartInfo = json.loads(data)
    except Exception as e1:
        LogError("Error getting start info : " + str(e1))
        LogError("Data returned from start_info_json: " + data)
        sys.exit(1)

    CacheToolTips()

    if bUseSecureHTTP and OldHTTPPort is not None and OldHTTPPort != HTTPPort:
        t = threading.Thread(target=StartHTTPRedirectServer, daemon=True)
        t.start()

    try:
        app.run(
            host=ListenIPAddress,
            port=HTTPPort,
            threaded=True,
            ssl_context=SSLContext,
            use_reloader=False,
            debug=False,
        )

    except Exception as e1:
        LogErrorLine("Error in app.run: " + str(e1))
        # Errno 98
        if e1.errno != errno.EADDRINUSE:  # and e1.errno != errno.EIO:
            sys.exit(1)
        # retry once
        try:
            LogError("Retrying app.run()")
            time.sleep(2)
            app.run(
                host=ListenIPAddress,
                port=HTTPPort,
                threaded=True,
                ssl_context=SSLContext,
                use_reloader=False,
                debug=False,
            )
        except Exception as e2:
            LogErrorLine("Error in app.run (2): " + str(e2))
        sys.exit(0)
