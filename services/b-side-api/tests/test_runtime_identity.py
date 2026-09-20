import json
import unittest
from unittest.mock import patch

from a2flow_bside.runtime_client import HttpRuntimeClient
from a2flow_bside.app import InternalRunStart
from a2flow_bside.identity import RequestIdentity


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
        alice, bob = root.for_user(101, "PRT"), root.for_user(102, "ONLINE")
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
        for user, env in (("101\r\nCookie:x", "PRT"), (101, "other"), ("", "PRT"),
                          ("101", "PRT"), (True, "PRT"), (2**63, "PRT")):
            with self.assertRaises(ValueError):
                root.for_user(user, env)

    def test_long_id_transport_is_lossless_and_internal_identity_is_strict(self):
        maximum = 2**63 - 1
        request = InternalRunStart(userId=str(maximum), workflowKey="workflow", input={})
        self.assertIs(type(request.userId), int)
        self.assertEqual(maximum, request.userId)
        identity = RequestIdentity(maximum, "alice", "USER")
        self.assertEqual(maximum, identity.userId)
        client = HttpRuntimeClient("http://localhost").for_user(maximum, "PRT")
        seen = []
        def open_request(request, **kwargs):
            seen.append(dict((k.lower(), v) for k, v in request.header_items()))
            return Response()
        with patch("urllib.request.urlopen", open_request):
            client.control("control")
        self.assertEqual(str(maximum), seen[0]["x-a2flow-user-id"])
        for value in (True, 1.0, "alice", "01", " 1", str(2**63)):
            with self.subTest(value=value), self.assertRaises(ValueError):
                InternalRunStart(userId=value, workflowKey="workflow", input={})
        with self.assertRaises(ValueError):
            RequestIdentity("1", "alice", "USER")
