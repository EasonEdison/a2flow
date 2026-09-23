"""Transport contract checks; not a claim of business-service or database readiness."""

import unittest

from a2flow.capability.v1 import capability_pb2 as capability
from a2flow.content.v1 import content_pb2 as content
from google.protobuf.json_format import MessageToDict


class ContentContractTest(unittest.TestCase):
    def test_all_operations_use_exact_common_context(self) -> None:
        service = content.DESCRIPTOR.services_by_name["ContentService"]
        self.assertEqual(len(service.methods), 11)
        for method in service.methods:
            context = method.input_type.fields_by_name["context"]
            self.assertEqual(context.message_type, capability.ExecutionContext.DESCRIPTOR)
            self.assertNotIn("user_id", method.input_type.fields_by_name)
            self.assertNotIn("cookie", method.input_type.fields_by_name)

    def test_signed64_identity_roundtrip_and_presence(self) -> None:
        for user_id in (-(2**63), 0, 2**63 - 1):
            request = content.CreateProjectRequest(
                context=capability.ExecutionContext(
                    user_id=user_id,
                    environment=capability.PRT,
                    request_id="test",
                    client="PC",
                ),
                title="测试资料",
                audience="读者",
                output_format="ARTICLE",
            )
            restored = content.CreateProjectRequest.FromString(request.SerializeToString())
            self.assertTrue(restored.context.HasField("user_id"))
            self.assertEqual(restored.context.user_id, user_id)
            self.assertEqual(MessageToDict(restored.context)["userId"], str(user_id))
        self.assertFalse(capability.ExecutionContext().HasField("user_id"))

    def test_mutating_confirmation_requires_explicit_revision_presence(self) -> None:
        request = content.ConfirmManuscriptRequest()
        self.assertFalse(request.HasField("expected_project_revision"))
        request.expected_project_revision = 0
        self.assertTrue(request.HasField("expected_project_revision"))

    def test_document_uses_typed_json_not_base64(self) -> None:
        request = content.SaveArtifactRequest(
            body=content.ArtifactBody(
                manuscript=content.Manuscript(title="中文标题", body_markdown="# 正文")
            )
        )
        restored = content.SaveArtifactRequest.FromString(request.SerializeToString())
        self.assertEqual(restored.body.WhichOneof("value"), "manuscript")
        self.assertEqual(MessageToDict(restored)["body"]["manuscript"]["bodyMarkdown"], "# 正文")

    def test_document_oneof_cannot_carry_two_kinds(self) -> None:
        body = content.ArtifactBody(manuscript=content.Manuscript(title="draft"))
        body.reading_brief.CopyFrom(content.ReadingBrief(points=[content.ReadingPoint(id="point")]))
        self.assertEqual(body.WhichOneof("value"), "reading_brief")
        self.assertFalse(body.HasField("manuscript"))

    def test_list_is_paged_object_not_bare_array(self) -> None:
        page = content.ListProjectsResponse(page=1, page_size=20, total=0)
        self.assertEqual(list(page.list), [])
        self.assertEqual(page.page_size, 20)


if __name__ == "__main__":
    unittest.main()
