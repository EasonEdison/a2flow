import unittest

from a2flow_bside import auth


class PasswordHashingTests(unittest.TestCase):
    PEPPER = "test-pepper"

    def test_roundtrip(self):
        encoded = auth.hash_password("correct-horse", pepper=self.PEPPER)
        self.assertTrue(encoded.startswith("scrypt$"))
        self.assertTrue(
            auth.verify_password("correct-horse", encoded, pepper=self.PEPPER)
        )

    def test_wrong_password_rejected(self):
        encoded = auth.hash_password("one", pepper=self.PEPPER)
        self.assertFalse(auth.verify_password("two", encoded, pepper=self.PEPPER))

    def test_pepper_mismatch_rejected(self):
        encoded = auth.hash_password("one", pepper=self.PEPPER)
        self.assertFalse(
            auth.verify_password("one", encoded, pepper="different-pepper")
        )

    def test_empty_password_rejected_at_hash_time(self):
        with self.assertRaises(ValueError):
            auth.hash_password("", pepper=self.PEPPER)

    def test_malformed_hashes_rejected(self):
        for value in ("", "scrypt$", "x$y$z", "scrypt$!!$!!", "argon2$a$b"):
            self.assertFalse(
                auth.verify_password("one", value, pepper=self.PEPPER)
            )

    def test_session_token(self):
        token = auth.new_session_token()
        self.assertGreaterEqual(len(token), 40)
        self.assertNotEqual(token, auth.new_session_token())
        self.assertEqual(
            auth.hash_session_token(token), auth.hash_session_token(token)
        )
        self.assertNotEqual(
            auth.hash_session_token(token), auth.hash_session_token("other")
        )


if __name__ == "__main__":
    unittest.main()
