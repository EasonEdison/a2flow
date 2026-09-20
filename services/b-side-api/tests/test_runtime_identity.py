import json
import unittest
from unittest.mock import patch

from a2flow_bside.runtime_client import HttpRuntimeClient


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        return b'{}'

    def __iter__(self):
        return iter([b'data: {"type":"done"}\n\n'])

    def close(self):
        pass


class RuntimeIdentityTest(unittest.TestCase):
    def test_json_and_stream_identity_is_bound_without_cookie(self):
        seen = []
        def open_request(request, **kwargs):
            seen.append(dict((k.lower(), v) for k, v in request.header_items()))
            return Response()
        root = HttpRuntimeClient("http://127.0.0.1:8765")
        alice, bob = root.for_user("101", "PRT"), root.for_user("102", "ONLINE")
        with patch("urllib.request.urlopen", open_request):
            alice.start("control", "workflow", {})
            bob.control("control")
            list(alice.action_stream("run", "node", {}))
            list(bob.surface_stream("run"))
        self.assertEqual([h["x-a2flow-user-id"] for h in seen],
                         ["101", "102", "101", "102"])
        self.assertEqual([h["x-a2flow-environment"] for h in seen],
                         ["PRT", "ONLINE", "PRT", "ONLINE"])
        self.assertTrue(all("cookie" not in h for h in seen))
        with self.assertRaises(ValueError):
            root.control("control")

    def test_invalid_identity_is_not_a_header_injection(self):
        root = HttpRuntimeClient("http://127.0.0.1:8765")
        for user, env in (("101\r\nCookie:x", "PRT"), ("101", "other"), ("", "PRT")):
            with self.assertRaises(ValueError):
                root.for_user(user, env)
