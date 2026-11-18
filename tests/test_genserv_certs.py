#!/usr/bin/env python3
# -------------------------------------------------------------------------------
#    FILE: test_genserv_certs.py
# PURPOSE: Tests for genserv.py's self-signed certificates (made with the
#          cryptography library): the persistent certificate for HTTPS
#          (selfsigned.crt / selfsigned.key: made once, kept, made again when
#          expired, key readable only by its owner), the fallback ad hoc
#          certificate, and the Local CA certificate in DER format for
#          browsers.
#
#   USAGE: from the root of the repository:
#              python3 -m unittest discover -s tests
#          or only these tests:
#              python3 -m unittest tests.test_genserv_certs
#
# -------------------------------------------------------------------------------

import datetime
import os
import shutil
import ssl
import sys
import tempfile
import unittest
import warnings
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genserv_fixture import GenServFixture  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402


def load(path):
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def not_after(cert):
    try:
        return cert.not_valid_after_utc
    except AttributeError:
        return cert.not_valid_after.replace(tzinfo=datetime.timezone.utc)


class CertificateTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # "auth" mode: HTTPS with cert_mode = selfsigned
        cls.fixture = GenServFixture("auth").start()
        cls.genserv = cls.fixture.instance

    @classmethod
    def tearDownClass(cls):
        cls.fixture.stop()

    def setUp(self):
        self.folder = tempfile.mkdtemp(prefix="genserv_certs_")
        self.addCleanup(shutil.rmtree, self.folder)
        self.crt = os.path.join(self.folder, "selfsigned.crt")
        self.key = os.path.join(self.folder, "selfsigned.key")

    def test_made_at_start(self):
        self.assertTrue(os.path.isfile(self.fixture.conf_path("selfsigned.crt")))

    def test_persistent_certificate(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            context = self.genserv.generate_persistent_selfsigned(self.folder)
        self.assertIsInstance(context, ssl.SSLContext)
        # no pyOpenSSL deprecation warnings (it used crypto.X509 / PKey)
        self.assertEqual([str(w.message) for w in caught if "deprecated" in str(w.message)], [])
        cert = load(self.crt)
        self.assertEqual(cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value, "*")
        self.assertEqual(cert.subject.get_attributes_for_oid(NameOID.ORGANIZATION_NAME)[0].value,
                         "Genmon Self-Signed")
        self.assertEqual(cert.issuer, cert.subject)
        days = (not_after(cert) - datetime.datetime.now(datetime.timezone.utc)).days
        self.assertIn(days, (364, 365))
        self.assertEqual(os.stat(self.key).st_mode & 0o777, 0o600)
        # the key is the certificate's key
        with open(self.key, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
        self.assertEqual(key.public_key().public_numbers(), cert.public_key().public_numbers())

    def test_kept(self):
        self.genserv.generate_persistent_selfsigned(self.folder)
        with open(self.crt, "rb") as f:
            first = f.read()
        self.genserv.generate_persistent_selfsigned(self.folder)
        with open(self.crt, "rb") as f:
            self.assertEqual(f.read(), first)

    def test_made_again_when_expired(self):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "*")])
        start = datetime.datetime(2020, 1, 1)
        expired = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                   .public_key(key.public_key()).serial_number(1)
                   .not_valid_before(start).not_valid_after(start + datetime.timedelta(days=365))
                   .sign(key, hashes.SHA256()))
        with open(self.crt, "wb") as f:
            f.write(expired.public_bytes(serialization.Encoding.PEM))
        with open(self.key, "wb") as f:
            f.write(key.private_bytes(serialization.Encoding.PEM,
                                      serialization.PrivateFormat.TraditionalOpenSSL,
                                      serialization.NoEncryption()))
        self.assertIsInstance(self.genserv.generate_persistent_selfsigned(self.folder), ssl.SSLContext)
        self.assertGreater(not_after(load(self.crt)), datetime.datetime.now(datetime.timezone.utc))

    def test_made_again_when_unreadable(self):
        with open(self.crt, "w") as f:
            f.write("not a certificate")
        with open(self.key, "w") as f:
            f.write("not a key")
        self.assertIsInstance(self.genserv.generate_persistent_selfsigned(self.folder), ssl.SSLContext)
        load(self.crt)

    def test_ad_hoc_fallback(self):
        # werkzeug's ad hoc certificate failed: one made by genserv
        with mock.patch("werkzeug.serving.generate_adhoc_ssl_context",
                        side_effect=RuntimeError("no adhoc")):
            context = self.genserv.generate_adhoc_ssl_context()
        self.assertIsInstance(context, ssl.SSLContext)

    def test_ca_certificate_der(self):
        self.genserv.generate_persistent_selfsigned(self.folder)
        der = self.genserv._ca_cert_der(self.crt)
        self.assertEqual(x509.load_der_x509_certificate(der), load(self.crt))


if __name__ == "__main__":
    unittest.main()
