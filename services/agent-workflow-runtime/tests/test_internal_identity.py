import unittest

from agent_workflow_runtime.internal_identity import private_identity
from agent_workflow_runtime.models import ActionRejected


class PrivateIdentityTest(unittest.TestCase):
    def scope(self, user=b"101", env=b"PRT", peer="127.0.0.1"):
        return {"client": (peer, 1234), "headers": [
            (b"x-a2flow-user-id", user), (b"x-a2flow-environment", env)]}

    def test_real_users_and_environment(self):
        resolve = private_identity("PRT")
        self.assertEqual(resolve(self.scope()).user_id, 101)
        self.assertEqual(resolve(self.scope(b"102")).user_id, 102)
        with self.assertRaises(ActionRejected):
            resolve(self.scope(env=b"ONLINE"))

    def test_missing_duplicate_cookie_and_nonprivate_rejected(self):
        resolve = private_identity("PRT")
        for scope in ({"client": ("127.0.0.1", 1), "headers": []},
                      self.scope(peer="192.0.2.1"), self.scope(user=b"")):
            with self.subTest(scope=scope), self.assertRaises(ActionRejected):
                resolve(scope)
        for extra in ((b"cookie", b"not-forwarded"),
                      (b"x-a2flow-user-id", b"102")):
            scope = self.scope()
            scope["headers"].append(extra)
            with self.assertRaises(ActionRejected):
                resolve(scope)
