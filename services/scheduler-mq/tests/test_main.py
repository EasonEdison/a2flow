import datetime as dt
import json
import unittest
import urllib.error

from a2flow_scheduler.main import (
    BsideHttpClient,
    RemoteHttpError,
    SchedulerSettings,
    run_once,
)

UTC = dt.timezone.utc


class FakeResponse:
    def __init__(self, payload="{}", status=200):
        self._payload = payload.encode()
        self.status = status
        self.code = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class BsideHttpClientTests(unittest.TestCase):
    def test_post_ok(self):
        opener = FakeOpener(FakeResponse('{"ok": true}'))
        client = BsideHttpClient("http://127.0.0.1:8000", opener=opener.open)
        client.post("/api/runs", json={"workflowKey": "wf/demo"})
        self.assertEqual(1, len(opener.calls))
        self.assertIn("/api/runs", opener.calls[0].full_url)

    def test_status_error_raises(self):
        opener = FakeOpener(FakeResponse("{}", 500))
        client = BsideHttpClient("http://127.0.0.1:8000", opener=opener.open)
        with self.assertRaises(RemoteHttpError):
            client.post("/api/runs", json={})

    def test_transport_error_raises(self):
        opener = FakeOpener(urllib.error.URLError("down"))
        client = BsideHttpClient("http://127.0.0.1:8000", opener=opener.open)
        with self.assertRaises(RemoteHttpError):
            client.post("/api/runs", json={})

    def test_invalid_base_rejected(self):
        with self.assertRaises(ValueError):
            BsideHttpClient("not-a-url")


class SchedulerSettingsTests(unittest.TestCase):
    def test_required_and_defaults(self):
        import os
        import unittest.mock as mock

        environ = {
            "A2FLOW_SCHEDULER_DATABASE_URL": "postgres://x",
            "A2FLOW_SCHEDULER_BSIDE_URL": "http://127.0.0.1:8000",
        }
        with mock.patch.dict(os.environ, environ, clear=True):
            settings = SchedulerSettings.from_environment()
            self.assertEqual(30.0, settings.trigger_seconds)
            self.assertEqual(300.0, settings.monitor_seconds)
            self.assertEqual(24.0, settings.timeout_hours)
            self.assertIsNone(settings.lark_url)

    def test_missing_required_raises(self):
        import os
        import unittest.mock as mock

        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                SchedulerSettings.from_environment()


if __name__ == "__main__":
    unittest.main()
