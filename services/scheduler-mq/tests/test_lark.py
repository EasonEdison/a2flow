import base64
import hashlib
import hmac
import json
import unittest
import urllib.error

from a2flow_scheduler import lark

URL = "https://open.feishu.cn/open-apis/bot/v2/hook/abc"


class FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = json.dumps(payload).encode("utf-8")
        self.status = status
        self.code = status

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FakeOpener:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def open(self, request, timeout=None):
        self.calls.append((request, timeout))
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


def opener_factory(responses):
    return lambda: FakeOpener(responses)


class SigningTests(unittest.TestCase):
    def test_signature_matches_feishu_vector(self):
        secret = "test-secret"
        timestamp = 1726700000
        expected_message = f"{timestamp}\n{secret}".encode("utf-8")
        expected = base64.b64encode(
            hmac.new(expected_message, digestmod=hashlib.sha256).digest()
        ).decode("ascii")
        client = lark.LarkWebhookClient(URL, secret=secret)
        self.assertEqual(expected, client.sign(timestamp))

    def test_sign_requires_secret(self):
        client = lark.LarkWebhookClient(URL)
        with self.assertRaises(ValueError):
            client.sign(1726700000)


class SendTests(unittest.TestCase):
    def test_success_single_attempt_with_signature_headers(self):
        opener = FakeOpener([FakeResponse({"code": 0})])
        client = lark.LarkWebhookClient(
            URL, secret="s", opener_factory=lambda: opener, sleep=lambda _: None
        )
        client.send({"elements": []})
        self.assertEqual(1, len(opener.calls))
        request, timeout = opener.calls[0]
        header_names = " ".join(request.headers.keys()).lower()
        self.assertIn("x-lark-signature", header_names)
        self.assertIn("x-lark-request-timestamp", header_names)

    def test_status_code_zero_also_accepted(self):
        opener = FakeOpener([FakeResponse({"StatusCode": 0})])
        client = lark.LarkWebhookClient(URL, opener_factory=lambda: opener, sleep=lambda _: None)
        client.send({"elements": []})  # must not raise

    def test_transport_retry_then_success(self):
        opener = FakeOpener(
            [urllib.error.URLError("boom"), FakeResponse({"code": 0})]
        )
        client = lark.LarkWebhookClient(
            URL, max_attempts=3, opener_factory=lambda: opener, sleep=lambda _: None
        )
        client.send({"elements": []})
        self.assertEqual(2, len(opener.calls))

    def test_exhausted_attempts_raise(self):
        opener = FakeOpener(
            [urllib.error.URLError("boom") for _ in range(3)]
        )
        client = lark.LarkWebhookClient(
            URL, max_attempts=3, opener_factory=lambda: opener, sleep=lambda _: None
        )
        with self.assertRaises(lark.LarkWebhookError):
            client.send({"elements": []})
        self.assertEqual(3, len(opener.calls))

    def test_rejected_payload_retries(self):
        opener = FakeOpener(
            [FakeResponse({"code": 19001}) for _ in range(2)]
        )
        client = lark.LarkWebhookClient(
            URL, max_attempts=2, opener_factory=lambda: opener, sleep=lambda _: None
        )
        with self.assertRaises(lark.LarkWebhookError):
            client.send({"elements": []})

    def test_invalid_url_rejected(self):
        with self.assertRaises(ValueError):
            lark.LarkWebhookClient("http://example.com/hook")


if __name__ == "__main__":
    unittest.main()
