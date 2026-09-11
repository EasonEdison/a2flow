from __future__ import unicode_literals

import hashlib
import io
import sys
import unittest

from skill_registry.resources import (
    PackageEntry,
    PackageEntryDescriptor,
    ResourceLimits,
    ResourceValidationError,
    validate_package_entries,
)


def sha256_digest(content):
    return "sha256:" + hashlib.sha256(content).hexdigest()


def entry(
        logical_path,
        content,
        media_type="text/plain",
        handle_id="material-1",
        declared_byte_size=None,
        declared_content_digest=None):
    payload = content if isinstance(content, bytes) else content.getvalue()
    descriptor = PackageEntryDescriptor(
        handle_id=handle_id,
        logical_path=logical_path,
        media_type=media_type,
        declared_byte_size=(
            len(payload)
            if declared_byte_size is None
            else declared_byte_size
        ),
        declared_content_digest=(
            sha256_digest(payload)
            if declared_content_digest is None
            else declared_content_digest
        ),
    )
    return PackageEntry(descriptor=descriptor, content=content)


class ValidatePackageEntriesTest(unittest.TestCase):

    def test_validates_text_and_retains_opaque_binary(self):
        text_payload = "说明".encode("utf-8")
        binary_payload = b"\x89PNG\x00\xff"
        entries = (
            entry("references/guide.md", text_payload, "text/markdown"),
            entry(
                "assets/cover.png",
                io.BytesIO(binary_payload),
                "image/png",
                handle_id="material-2",
            ),
        )

        verified = validate_package_entries(entries, ResourceLimits())

        self.assertIsInstance(verified, tuple)
        self.assertEqual("说明", verified[0].text)
        self.assertEqual(text_payload, verified[0].content)
        self.assertIsNone(verified[1].text)
        self.assertEqual(binary_payload, verified[1].content)
        self.assertEqual(len(binary_payload), verified[1].byte_size)
        self.assertEqual(sha256_digest(binary_payload), verified[1].content_digest)

    def test_rejects_duplicate_logical_path(self):
        entries = (
            entry("references/guide.md", b"one", handle_id="material-1"),
            entry("references/guide.md", b"two", handle_id="material-2"),
        )

        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries(entries, ResourceLimits())

        self.assertEqual("DUPLICATE_LOGICAL_PATH", raised.exception.code)
        self.assertEqual("references/guide.md", raised.exception.logical_path)

    def test_rejects_declared_size_or_digest_disagreement(self):
        cases = (
            ("DECLARED_SIZE_MISMATCH", entry("size.txt", b"abc", declared_byte_size=2)),
            (
                "DECLARED_DIGEST_MISMATCH",
                entry("digest.txt", b"abc", declared_content_digest=sha256_digest(b"xyz")),
            ),
        )

        for expected_code, package_entry in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ResourceValidationError) as raised:
                    validate_package_entries((package_entry,), ResourceLimits())
                self.assertEqual(expected_code, raised.exception.code)

    def test_stops_reading_iterable_after_entry_limit_boundary(self):
        consumed = []

        def many_entries():
            for index in range(5):
                consumed.append(index)
                yield entry(
                    "item-{0}.txt".format(index),
                    b"x",
                    handle_id="material-{0}".format(index),
                )

        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries(
                many_entries(),
                ResourceLimits(max_entries=2),
            )

        self.assertEqual("ENTRY_COUNT_LIMIT_EXCEEDED", raised.exception.code)
        self.assertEqual([0, 1, 2], consumed)

    def test_rejects_unsafe_or_overdeep_logical_paths(self):
        invalid_paths = (
            "/absolute.txt",
            "../secret.txt",
            "assets/../secret.txt",
            "assets\\secret.txt",
            "assets//secret.txt",
            ".",
        )
        for logical_path in invalid_paths:
            with self.subTest(logical_path=logical_path):
                with self.assertRaises(ResourceValidationError) as raised:
                    validate_package_entries(
                        (entry(logical_path, b"x"),),
                        ResourceLimits(),
                    )
                self.assertEqual("INVALID_LOGICAL_PATH", raised.exception.code)

        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries(
                (entry("one/two/three.txt", b"x"),),
                ResourceLimits(max_path_depth=2),
            )
        self.assertEqual("PATH_DEPTH_LIMIT_EXCEEDED", raised.exception.code)

    def test_enforces_entry_total_and_path_length_limits(self):
        cases = (
            (
                "ENTRY_BYTES_LIMIT_EXCEEDED",
                (entry("large.txt", b"four"),),
                ResourceLimits(max_entry_bytes=3),
            ),
            (
                "TOTAL_BYTES_LIMIT_EXCEEDED",
                (
                    entry("one.txt", b"12", handle_id="material-1"),
                    entry("two.txt", b"34", handle_id="material-2"),
                ),
                ResourceLimits(max_entry_bytes=2, max_total_bytes=3),
            ),
            (
                "PATH_LENGTH_LIMIT_EXCEEDED",
                (entry("long.txt", b"x"),),
                ResourceLimits(max_path_length=3),
            ),
        )

        for expected_code, entries, limits in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(ResourceValidationError) as raised:
                    validate_package_entries(entries, limits)
                self.assertEqual(expected_code, raised.exception.code)

    def test_rejects_invalid_utf8_text_but_keeps_same_binary_bytes(self):
        invalid_utf8 = b"\xff\xfe"

        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries(
                (entry("bad.txt", invalid_utf8, "text/plain"),),
                ResourceLimits(),
            )
        self.assertEqual("INVALID_TEXT_ENCODING", raised.exception.code)

        verified = validate_package_entries(
            (entry("raw.bin", invalid_utf8, "application/octet-stream"),),
            ResourceLimits(),
        )
        self.assertEqual(invalid_utf8, verified[0].content)
        self.assertIsNone(verified[0].text)

    def test_rejects_invalid_limits_and_non_binary_stream(self):
        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries((), ResourceLimits(max_entries=0))
        self.assertEqual("INVALID_LIMITS", raised.exception.code)

        with self.assertRaises(ResourceValidationError) as raised:
            validate_package_entries(
                (
                    PackageEntry(
                        descriptor=PackageEntryDescriptor(
                            handle_id="material-1",
                            logical_path="bad.txt",
                            media_type="text/plain",
                            declared_byte_size=4,
                            declared_content_digest=sha256_digest(b"text"),
                        ),
                        content=io.StringIO("text"),
                    ),
                ),
                ResourceLimits(),
            )
        self.assertEqual("INVALID_CONTENT_SOURCE", raised.exception.code)

    def test_rejects_line_breaks_in_contract_pattern_fields(self):
        digest = sha256_digest(b"x")

        for line_break in ("\n", "\r", "\r\n"):
            cases = (
                (
                    "INVALID_LOGICAL_PATH",
                    entry("unsafe.txt" + line_break, b"x"),
                ),
                (
                    "INVALID_HANDLE_ID",
                    entry(
                        "safe.txt",
                        b"x",
                        handle_id="material-1" + line_break,
                    ),
                ),
                (
                    "INVALID_DECLARED_DIGEST",
                    entry(
                        "safe.txt",
                        b"x",
                        declared_content_digest=digest + line_break,
                    ),
                ),
            )

            for expected_code, package_entry in cases:
                with self.subTest(
                        expected_code=expected_code,
                        line_break=repr(line_break)):
                    with self.assertRaises(ResourceValidationError) as raised:
                        validate_package_entries(
                            (package_entry,),
                            ResourceLimits(),
                        )
                    self.assertEqual(expected_code, raised.exception.code)

    def test_limits_can_only_tighten_non_negotiable_hard_ceilings(self):
        invalid_limits = (
            ResourceLimits(max_entries=129),
            ResourceLimits(max_entry_bytes=4 * 1024 * 1024 + 1),
            ResourceLimits(max_total_bytes=16 * 1024 * 1024 + 1),
            ResourceLimits(max_path_depth=33),
            ResourceLimits(max_entry_bytes=4, max_total_bytes=3),
            ResourceLimits(max_entries=sys.maxsize + 1),
        )

        for limits in invalid_limits:
            with self.subTest(limits=limits):
                with self.assertRaises(ResourceValidationError) as raised:
                    validate_package_entries((), limits)
                self.assertEqual("INVALID_LIMITS", raised.exception.code)


if __name__ == "__main__":
    unittest.main()
