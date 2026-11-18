#!/usr/bin/env python
# -------------------------------------------------------------------------------
#    FILE: mytls.py
# PURPOSE: TLS (SSL) settings for add-ons that connect to a server, e.g. an MQTT
#          broker (genmqtt.py, genmqttin.py, genhomeassistant.py)
#
#  AUTHOR: Jason G Yates
#    DATE: 17-Nov-2026
#
# MODIFICATIONS:
# -------------------------------------------------------------------------------

import ssl

# tls_version setting: "Auto" uses TLS 1.2 or newer, whatever both sides support;
# a version number uses only that version
TLS_VERSIONS = {
    "auto": None,
    "1.3": ssl.TLSVersion.TLSv1_3,
    "1.2": ssl.TLSVersion.TLSv1_2,
    "1.1": ssl.TLSVersion.TLSv1_1,
    "1.0": ssl.TLSVersion.TLSv1,
    "1": ssl.TLSVersion.TLSv1,
}
TLS_VERSION_CHOICES = "Auto,1.3,1.2,1.1,1.0"

# cert_reqs setting: what is checked about the server's certificate
CERT_REQS = {"required": ssl.CERT_REQUIRED, "optional": ssl.CERT_OPTIONAL, "none": ssl.CERT_NONE}


def _log_error(log, message):
    if log is not None:
        log.error(message)


# -------------------------------------------------------------------------------
def TLSClientContext(ca_file, cert_file=None, key_file=None, cert_reqs="Required",
                     tls_version="Auto", log=None):
    """An ssl.SSLContext for connecting to a server.

    ca_file    the Certificate Authority file the server's certificate is checked with
    cert_file, key_file
               optional client certificate and key, if the server asks for one
    cert_reqs  "Required" (default), "Optional" or "None". With Required and
               Optional the server's certificate and host name are checked (if the
               server sends a certificate); None checks neither.
    tls_version
               "Auto" (default), "1.3", "1.2", "1.1" or "1.0"

    A setting that is not valid is logged and the default used. Errors reading
    the files are raised (ssl.SSLError, OSError).

    (This replaces ssl.PROTOCOL_TLSv1... and paho's tls_set(tls_version=...);
    Python 3.14 removed those constants.)
    """
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    version = str(tls_version if tls_version is not None else "auto").strip().lower()
    if version not in TLS_VERSIONS:
        _log_error(log, "Invalid TLS version %r, using Auto" % tls_version)
        version = "auto"
    try:
        if version == "auto":
            context.minimum_version = ssl.TLSVersion.TLSv1_2
        else:
            context.minimum_version = TLS_VERSIONS[version]
            context.maximum_version = TLS_VERSIONS[version]
    except ValueError as e1:
        # this OpenSSL does not allow the version
        _log_error(log, "TLS version %s is not supported here (%s), using Auto" % (tls_version, e1))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.MAXIMUM_SUPPORTED

    reqs = str(cert_reqs if cert_reqs is not None else "required").strip().lower()
    if reqs not in CERT_REQS:
        _log_error(log, "Invalid certificate requirement %r, using Required" % cert_reqs)
        reqs = "required"
    if reqs == "none":
        # the host name can only be checked with a certificate
        context.check_hostname = False
    context.verify_mode = CERT_REQS[reqs]

    context.load_verify_locations(ca_file)
    if cert_file:
        context.load_cert_chain(cert_file, key_file or None)
    return context
