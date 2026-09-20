import json
import unittest

from skillweave_contracts.user_id import (
    MIN_USER_ID, MAX_USER_ID, require_user_id, user_id_from_wire, user_id_to_wire,
)


class LongUserIdTests(unittest.TestCase):
    def test_trusted_context_and_schema_round_trip(self):
        import re
        from skillweave_contracts.models import TrustedContext
        from skillweave_contracts.schema_loader import load_definition_schema
        schema = load_definition_schema("longUserId")["definitions"]["longUserId"]
        for value in (MIN_USER_ID, -1, 0, 2**53 + 1, MAX_USER_ID):
            owner = TrustedContext(value, "ONLINE")
            wire = owner.to_mapping()
            self.assertIs(type(wire["userId"]), str)
            self.assertEqual(owner, TrustedContext.from_mapping(wire))
            self.assertIsNotNone(re.fullmatch(schema["pattern"], wire["userId"]))
        for value in ("01", "-0", str(MAX_USER_ID+1), str(MIN_USER_ID-1), "a"):
            self.assertIsNone(re.fullmatch(schema["pattern"], value))

    def test_signed_boundaries_and_browser_precision(self):
        for value in (MIN_USER_ID, -1, 0, 1, 2**53 + 1, MAX_USER_ID):
            self.assertEqual(value, require_user_id(value))
            wire = json.loads(json.dumps({"userId": user_id_to_wire(value)}))
            self.assertIs(type(wire["userId"]), str)
            self.assertEqual(value, user_id_from_wire(wire["userId"]))
            self.assertEqual(value, user_id_from_wire(value))

    def test_internal_type_is_not_string_bool_or_float(self):
        for value in ("1", True, False, 1.0, None, [], {}, MAX_USER_ID+1, MIN_USER_ID-1):
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                require_user_id(value)

    def test_wire_rejects_lossy_or_ambiguous_forms(self):
        for value in ("01", "-0", "+1", " 1", "1 ", "1.0", "1e3", "１２",
                      'user_1', "", str(MAX_USER_ID+1), str(MIN_USER_ID-1),
                      True, 1.0, None, "1"*10000):
            with self.subTest(value=repr(value)[:50]), self.assertRaises(ValueError):
                user_id_from_wire(value)
