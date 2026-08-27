from __future__ import annotations

import os
import ssl
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from research_cli.http import ssl_context  # noqa: E402


class SslContextTests(unittest.TestCase):
    def test_ssl_cert_file_env(self) -> None:
        candidates = (
            "/etc/ssl/cert.pem",
            "/etc/ssl/certs/ca-certificates.crt",
        )
        cafile = next((path for path in candidates if Path(path).is_file()), None)
        if cafile is None:
            self.skipTest("no system CA bundle on this host")
        previous = os.environ.get("SSL_CERT_FILE")
        os.environ["SSL_CERT_FILE"] = cafile
        try:
            ctx = ssl_context()
            self.assertIsInstance(ctx, ssl.SSLContext)
            self.assertTrue(ctx.check_hostname)
        finally:
            if previous is None:
                os.environ.pop("SSL_CERT_FILE", None)
            else:
                os.environ["SSL_CERT_FILE"] = previous

    def test_default_context_verifies(self) -> None:
        ctx = ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)
