#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_tls.py
# PURPOSE: Tests for genmonlib/mytls.py, the TLS settings used by the add-ons
#          that connect to an MQTT broker (genmqtt.py, genmqttin.py,
#          genhomeassistant.py).
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_tls
#
# -------------------------------------------------------------------------------

import os
import ssl
import sys
import unittest
import warnings
from unittest import mock

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_DIR)

from genmonlib.mytls import TLS_VERSION_CHOICES, TLSClientContext  # noqa: E402


class TLSContextTests(unittest.TestCase):

    def context(self, **kwargs):
        # the files are only read by the ssl library
        with mock.patch.object(ssl.SSLContext, "load_verify_locations") as self.load_ca, \
                mock.patch.object(ssl.SSLContext, "load_cert_chain") as self.load_cert:
            return TLSClientContext("/etc/genmon/ca.crt", **kwargs)

    def test_defaults(self):
        # Auto, Required: TLS 1.2 or newer, the certificate and host name checked
        context = self.context()
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        # no maximum: as new as this ssl library allows
        self.assertEqual(context.maximum_version,
                         ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).maximum_version)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.load_ca.assert_called_once_with("/etc/genmon/ca.crt")
        self.load_cert.assert_not_called()

    def test_one_version(self):
        for setting, version in [("1.3", ssl.TLSVersion.TLSv1_3), ("1.2", ssl.TLSVersion.TLSv1_2),
                                 ("1.1", ssl.TLSVersion.TLSv1_1), ("1.0", ssl.TLSVersion.TLSv1),
                                 ("1", ssl.TLSVersion.TLSv1), (" auto ", None)]:
            if version == ssl.TLSVersion.TLSv1_3 and not ssl.HAS_TLSv1_3:
                continue  # e.g. macOS's LibreSSL 2.8, see test_version_not_supported
            with self.subTest(tls_version=setting):
                with warnings.catch_warnings():  # 1.0 and 1.1 are deprecated
                    warnings.simplefilter("ignore", DeprecationWarning)
                    context = self.context(tls_version=setting)
                if version is None:
                    self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
                else:
                    self.assertEqual((context.minimum_version, context.maximum_version),
                                     (version, version))

    def test_version_not_supported(self):
        # a version this ssl library can not use: logged, and Auto used
        log = mock.Mock()
        with mock.patch.object(ssl.SSLContext, "maximum_version",
                               new_callable=mock.PropertyMock,
                               side_effect=[ValueError("not supported"), None]):
            context = self.context(tls_version="1.2", log=log)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(len(log.error.call_args_list), 1)

    def test_certificate_requirements(self):
        context = self.context(cert_reqs="Optional")
        self.assertEqual(context.verify_mode, ssl.CERT_OPTIONAL)
        self.assertTrue(context.check_hostname)
        context = self.context(cert_reqs="none")
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    def test_invalid_settings_logged(self):
        log = mock.Mock()
        context = self.context(tls_version="2.0", cert_reqs="Sometimes", log=log)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertEqual(len(log.error.call_args_list), 2)

    def test_client_certificate(self):
        self.context(cert_file="/etc/genmon/client.crt", key_file="/etc/genmon/client.key")
        self.load_cert.assert_called_once_with("/etc/genmon/client.crt", "/etc/genmon/client.key")

    def test_choices(self):
        # every choice on the Add-Ons page is a valid setting
        for choice in TLS_VERSION_CHOICES.split(","):
            if choice == "1.3" and not ssl.HAS_TLSv1_3:
                continue
            with self.subTest(choice=choice):
                log = mock.Mock()
                with warnings.catch_warnings():  # 1.0 and 1.1 are deprecated
                    warnings.simplefilter("ignore", DeprecationWarning)
                    self.context(tls_version=choice, log=log)
                log.error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
