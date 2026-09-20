"""Identity boundaries preserve signed64 values without broadening authority."""
import unittest

from pydantic import ValidationError
from a2flow_management.contracts import (
    ManagedDraft, ManagementError, PublicationPlan, PublicationTarget,
    TrustedManagementContext,
)
from a2flow_management.http import Target


class LongUserIdTests(unittest.TestCase):
    def test_large_ids_remain_integers_inside_and_decimal_text_on_wire(self):
        user = (1 << 63) - 1
        context = TrustedManagementContext(user, "ONLINE", frozenset({"ADMIN"}))
        self.assertIs(type(context.user_id), int)
        draft = ManagedDraft.create("SKILL", "team/skill", 1, {}, user)
        self.assertEqual(str(user), draft.to_mapping()["updatedBy"])
        for raw in (user, str(user)):
            parsed = Target(environment="ONLINE", versionId="v1", channel="GRAY",
                            grayUserIds=[raw])
            self.assertEqual([user], parsed.grayUserIds)
            target = PublicationTarget("ONLINE", "v1", "GRAY", tuple(parsed.grayUserIds))
            plan = PublicationPlan.create("SKILL", "team/skill", 1, target, {})
            self.assertEqual([str(user)], plan.to_mapping()["target"]["grayUserIds"])

    def test_untrusted_types_and_out_of_range_ids_fail_closed(self):
        for invalid in (True, 1.0, "1", None, 1 << 63, -(1 << 63) - 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ManagementError):
                    TrustedManagementContext(invalid, "PRT", frozenset({"ADMIN"}))
                with self.assertRaises(ManagementError):
                    PublicationTarget("ONLINE", "v1", "GRAY", (invalid,))
        for invalid in (True, 1.0, "01", "+1", " 1", "1.0", str(1 << 63)):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                Target(environment="ONLINE", versionId="v1", channel="GRAY",
                       grayUserIds=[invalid])


if __name__ == "__main__":
    unittest.main()
