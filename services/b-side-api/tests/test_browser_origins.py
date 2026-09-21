"""Exact allowlist handling for public and local account ingress."""
import os
import unittest
from unittest.mock import patch
from starlette.datastructures import Headers
from a2flow_bside.config import BsideConfig
from a2flow_bside.errors import BsideError
from a2flow_bside.identity import require_origin


class BrowserOriginsTests(unittest.TestCase):
    env = {
        "A2FLOW_BSIDE_DATABASE_URL": "dbname=test",
        "A2FLOW_BSIDE_PEPPER": "test-pepper-0123456789abcdef",
        "A2FLOW_BSIDE_BROWSER_ORIGIN": "http://127.0.0.1:14184",
        "A2FLOW_BSIDE_RUNTIME_URL": "http://127.0.0.1:8782",
        "A2FLOW_BSIDE_ENVIRONMENT": "PRT",
        "A2FLOW_BSIDE_ASSET_NAMESPACE": "test",
        "A2FLOW_BSIDE_SESSION_SECONDS": "7200",
    }

    def test_default_is_single_origin(self):
        with patch.dict(os.environ, self.env, clear=True):
            config = BsideConfig.from_environment()
        self.assertEqual(config.browser_origins, (config.browser_origin,))

    def test_public_and_local_exact_match(self):
        values = dict(self.env, A2FLOW_BSIDE_BROWSER_ORIGINS="http://127.0.0.1:14184,http://example.test")
        with patch.dict(os.environ, values, clear=True):
            config = BsideConfig.from_environment()
        for origin in config.browser_origins:
            require_origin(Headers({"origin": origin}), config.browser_origins)
        for raw in [[], [(b"origin", b"http://evil.test")],
                    [(b"origin", b"http://example.test"), (b"origin", b"http://example.test")],
                    [(b"origin", b"http://example.test.attacker")]]:
            with self.assertRaises(BsideError):
                require_origin(Headers(raw=raw), config.browser_origins)

    def test_misconfiguration_rejected(self):
        for origins in ["", "http://127.0.0.1:14184,https://example.test",
                        "http://example.test", "http://127.0.0.1:14184,http://*",
                        "http://127.0.0.1:14184,http://example.test/path"]:
            values = dict(self.env, A2FLOW_BSIDE_BROWSER_ORIGINS=origins)
            with patch.dict(os.environ, values, clear=True):
                with self.assertRaises(RuntimeError):
                    BsideConfig.from_environment()
