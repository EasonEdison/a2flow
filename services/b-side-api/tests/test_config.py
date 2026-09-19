"""Offline tests for fail-closed environment configuration."""

import os
import unittest
from unittest import mock

from a2flow_bside.config import (
    BsideConfig,
    browser_origin,
    runtime_url,
    session_seconds,
)


class BrowserOriginTests(unittest.TestCase):
    def test_loopback_accepted(self):
        self.assertEqual("http://127.0.0.1:14177",
                         browser_origin("http://127.0.0.1:14177"))
        self.assertEqual("http://127.0.0.1:14177",
                         browser_origin("http://127.0.0.1:14177/"))

    def test_explicit_public_origin_accepted(self):
        self.assertEqual("http://47.110.84.69",
                         browser_origin("http://47.110.84.69"))

    def test_invalid_origins_rejected(self):
        for value in ("http://127.0.0.1:14177/path",
                      "http://user:pass@127.0.0.1",
                      "ftp://127.0.0.1",
                      "http://127.0.0.1:14177?x=1",
                      "http://127.0.0.1:14177#frag"):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    browser_origin(value)


class RuntimeUrlTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual("http://127.0.0.1:8765",
                         runtime_url("http://127.0.0.1:8765/"))

    def test_invalid(self):
        for value in ("http://host/path", "ws://host", "not-a-url"):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    runtime_url(value)


class SessionSecondsTests(unittest.TestCase):
    def test_bounds(self):
        self.assertEqual(7200, session_seconds("7200"))
        for value in ("59", "604801", "abc"):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    session_seconds(value)


class EnvironmentFactoryTests(unittest.TestCase):
    ENV = {
        "A2FLOW_BSIDE_DATABASE_URL": "host=/tmp/sock dbname=a2flow",
        "A2FLOW_BSIDE_PEPPER": "0123456789abcdef",
        "A2FLOW_BSIDE_BROWSER_ORIGIN": "http://127.0.0.1:14177",
        "A2FLOW_BSIDE_RUNTIME_URL": "http://127.0.0.1:8765",
        "A2FLOW_BSIDE_ENVIRONMENT": "PRT",
        "A2FLOW_BSIDE_ASSET_NAMESPACE": "a2flow-mvp-activity-planning",
        "A2FLOW_BSIDE_SESSION_SECONDS": "7200",
    }

    def test_missing_value_fails(self):
        for missing in self.ENV:
            with self.subTest(missing=missing):
                partial = {key: value for key, value in self.ENV.items()
                           if key != missing}
                with mock.patch.dict(os.environ, partial, clear=True):
                    with self.assertRaises(RuntimeError):
                        BsideConfig.from_environment()

    def test_short_pepper_fails(self):
        values = dict(self.ENV)
        values["A2FLOW_BSIDE_PEPPER"] = "short"
        with mock.patch.dict(os.environ, values, clear=True):
            with self.assertRaises(RuntimeError):
                BsideConfig.from_environment()

    def test_invalid_environment_fails(self):
        values = dict(self.ENV)
        values["A2FLOW_BSIDE_ENVIRONMENT"] = "DEV"
        with mock.patch.dict(os.environ, values, clear=True):
            with self.assertRaises(RuntimeError):
                BsideConfig.from_environment()

    def test_complete_environment_ok(self):
        with mock.patch.dict(os.environ, self.ENV, clear=True):
            config = BsideConfig.from_environment()
            self.assertEqual("PRT", config.environment)
            self.assertEqual(7200, config.session_seconds)


if __name__ == "__main__":
    unittest.main()
