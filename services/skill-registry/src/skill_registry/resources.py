"""Bounded validation for material entries supplied by a trusted adapter.

This module validates immutable metadata against actual bytes. It does not locate
files, extract archives, parse Skill frontmatter, execute content, or grant Tool
permissions.
"""

from __future__ import unicode_literals

from collections import namedtuple
from itertools import islice
import hashlib
import re


ACCESS_MODE_READ_ONLY = "READ_ONLY"
DEFAULT_MAX_ENTRIES = 128
DEFAULT_MAX_ENTRY_BYTES = 4 * 1024 * 1024
DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_PATH_LENGTH = 1024
DEFAULT_MAX_PATH_DEPTH = 32
MAX_CONTRACT_PATH_LENGTH = 1024
MAX_MEDIA_TYPE_LENGTH = 128
READ_CHUNK_BYTES = 64 * 1024

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_LOGICAL_PATH_PATTERN = re.compile(
    r"^[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*$"
)


class ResourceLimits(namedtuple(
        "_ResourceLimits",
        (
            "max_entries",
            "max_entry_bytes",
            "max_total_bytes",
            "max_path_length",
            "max_path_depth",
        ))):
    """Finite immutable limits applied before material is exposed."""

    __slots__ = ()

    def __new__(
            cls,
            max_entries=DEFAULT_MAX_ENTRIES,
            max_entry_bytes=DEFAULT_MAX_ENTRY_BYTES,
            max_total_bytes=DEFAULT_MAX_TOTAL_BYTES,
            max_path_length=DEFAULT_MAX_PATH_LENGTH,
            max_path_depth=DEFAULT_MAX_PATH_DEPTH):
        return super(ResourceLimits, cls).__new__(
            cls,
            max_entries,
            max_entry_bytes,
            max_total_bytes,
            max_path_length,
            max_path_depth,
        )


class PackageEntryDescriptor(namedtuple(
        "_PackageEntryDescriptor",
        (
            "handle_id",
            "logical_path",
            "media_type",
            "declared_byte_size",
            "declared_content_digest",
        ))):
    """Immutable metadata asserted by a trusted material adapter."""

    __slots__ = ()


class PackageEntry(namedtuple("_PackageEntry", ("descriptor", "content"))):
    """Immutable pairing of a descriptor and bounded bytes or binary stream."""

    __slots__ = ()


class VerifiedResource(namedtuple(
        "_VerifiedResource",
        (
            "handle_id",
            "access_mode",
            "logical_path",
            "media_type",
            "byte_size",
            "content_digest",
            "content",
            "text",
        ))):
    """Material whose declared metadata agrees with the supplied bytes."""

    __slots__ = ()


class ResourceValidationError(ValueError):
    """Fail-closed validation error without exposing material contents."""

    def __init__(self, code, message, logical_path=None):
        super(ResourceValidationError, self).__init__(message)
        self.code = code
        self.logical_path = logical_path


def _fail(code, message, logical_path=None):
    raise ResourceValidationError(code, message, logical_path)


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _validate_limits(limits):
    if not isinstance(limits, ResourceLimits):
        _fail("INVALID_LIMITS", "limits must be a ResourceLimits value")
    values = (
        limits.max_entries,
        limits.max_entry_bytes,
        limits.max_total_bytes,
        limits.max_path_length,
        limits.max_path_depth,
    )
    if not all(_is_positive_integer(value) for value in values):
        _fail("INVALID_LIMITS", "resource limits must be finite positive integers")
    hard_ceilings = (
        (limits.max_entries, DEFAULT_MAX_ENTRIES),
        (limits.max_entry_bytes, DEFAULT_MAX_ENTRY_BYTES),
        (limits.max_total_bytes, DEFAULT_MAX_TOTAL_BYTES),
        (limits.max_path_length, MAX_CONTRACT_PATH_LENGTH),
        (limits.max_path_depth, DEFAULT_MAX_PATH_DEPTH),
    )
    if any(value > ceiling for value, ceiling in hard_ceilings):
        _fail(
            "INVALID_LIMITS",
            "resource limits may only tighten non-negotiable hard ceilings",
        )
    if limits.max_entry_bytes > limits.max_total_bytes:
        _fail(
            "INVALID_LIMITS",
            "max_entry_bytes cannot exceed max_total_bytes",
        )


def _validate_logical_path(logical_path, limits):
    if not isinstance(logical_path, str) or not logical_path:
        _fail("INVALID_LOGICAL_PATH", "logicalPath must be a non-empty string")
    if len(logical_path) > limits.max_path_length:
        _fail(
            "PATH_LENGTH_LIMIT_EXCEEDED",
            "logicalPath exceeds the configured length limit",
            logical_path,
        )
    if not _LOGICAL_PATH_PATTERN.fullmatch(logical_path):
        _fail(
            "INVALID_LOGICAL_PATH",
            "logicalPath must be a safe relative slash-separated path",
            logical_path,
        )
    segments = logical_path.split("/")
    if any(segment in (".", "..") for segment in segments):
        _fail(
            "INVALID_LOGICAL_PATH",
            "logicalPath cannot contain dot traversal segments",
            logical_path,
        )
    if len(segments) > limits.max_path_depth:
        _fail(
            "PATH_DEPTH_LIMIT_EXCEEDED",
            "logicalPath exceeds the configured depth limit",
            logical_path,
        )


def _validate_descriptor(descriptor, limits):
    if not isinstance(descriptor, PackageEntryDescriptor):
        _fail("INVALID_DESCRIPTOR", "entry descriptor has an unsupported type")
    _validate_logical_path(descriptor.logical_path, limits)
    if (
            not isinstance(descriptor.handle_id, str)
            or not _IDENTIFIER_PATTERN.fullmatch(descriptor.handle_id)):
        _fail(
            "INVALID_HANDLE_ID",
            "handleId does not match the approved identifier primitive",
            descriptor.logical_path,
        )
    if (
            not isinstance(descriptor.media_type, str)
            or not descriptor.media_type
            or len(descriptor.media_type) > MAX_MEDIA_TYPE_LENGTH):
        _fail(
            "INVALID_MEDIA_TYPE",
            "mediaType must be a non-empty bounded string",
            descriptor.logical_path,
        )
    if (
            not isinstance(descriptor.declared_byte_size, int)
            or isinstance(descriptor.declared_byte_size, bool)
            or descriptor.declared_byte_size < 0):
        _fail(
            "INVALID_DECLARED_SIZE",
            "declared byte size must be a non-negative integer",
            descriptor.logical_path,
        )
    if descriptor.declared_byte_size > limits.max_entry_bytes:
        _fail(
            "ENTRY_BYTES_LIMIT_EXCEEDED",
            "declared byte size exceeds the configured entry limit",
            descriptor.logical_path,
        )
    if (
            not isinstance(descriptor.declared_content_digest, str)
            or not _DIGEST_PATTERN.fullmatch(
                descriptor.declared_content_digest
            )):
        _fail(
            "INVALID_DECLARED_DIGEST",
            "declared digest must be lowercase sha256 evidence",
            descriptor.logical_path,
        )


def _read_content(content, limit, logical_path):
    if isinstance(content, bytes):
        payload = content
    elif isinstance(content, (bytearray, memoryview)):
        payload = bytes(content)
    else:
        read = getattr(content, "read", None)
        if not callable(read):
            _fail(
                "INVALID_CONTENT_SOURCE",
                "content must be bytes or a readable binary stream",
                logical_path,
            )
        chunks = []
        size = 0
        while True:
            chunk = read(min(READ_CHUNK_BYTES, limit - size + 1))
            if not isinstance(chunk, (bytes, bytearray, memoryview)):
                _fail(
                    "INVALID_CONTENT_SOURCE",
                    "content stream must return bytes",
                    logical_path,
                )
            if not chunk:
                break
            chunk = bytes(chunk)
            size += len(chunk)
            if size > limit:
                _fail(
                    "ENTRY_BYTES_LIMIT_EXCEEDED",
                    "actual bytes exceed the configured entry limit",
                    logical_path,
                )
            chunks.append(chunk)
        payload = b"".join(chunks)
    if len(payload) > limit:
        _fail(
            "ENTRY_BYTES_LIMIT_EXCEEDED",
            "actual bytes exceed the configured entry limit",
            logical_path,
        )
    return payload


def _decode_text(media_type, content, logical_path):
    if not media_type.lower().startswith("text/"):
        return None
    try:
        return content.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _fail(
            "INVALID_TEXT_ENCODING",
            "text material must be strict UTF-8",
            logical_path,
        )


def validate_package_entries(entries, limits=None):
    """Validate trusted entries against actual bytes and return immutable data."""

    if limits is None:
        limits = ResourceLimits()
    _validate_limits(limits)
    try:
        iterator = iter(entries)
    except TypeError:
        _fail("INVALID_ENTRIES", "entries must be a finite iterable")
    entries = tuple(islice(iterator, limits.max_entries + 1))
    if len(entries) > limits.max_entries:
        _fail(
            "ENTRY_COUNT_LIMIT_EXCEEDED",
            "entry count exceeds the configured limit",
        )

    seen_paths = set()
    for package_entry in entries:
        if not isinstance(package_entry, PackageEntry):
            _fail("INVALID_ENTRY", "entry has an unsupported type")
        descriptor = package_entry.descriptor
        _validate_descriptor(descriptor, limits)
        if descriptor.logical_path in seen_paths:
            _fail(
                "DUPLICATE_LOGICAL_PATH",
                "logicalPath must be unique within material",
                descriptor.logical_path,
            )
        seen_paths.add(descriptor.logical_path)

    verified = []
    total_bytes = 0
    for package_entry in entries:
        descriptor = package_entry.descriptor
        payload = _read_content(
            package_entry.content,
            limits.max_entry_bytes,
            descriptor.logical_path,
        )
        byte_size = len(payload)
        if byte_size != descriptor.declared_byte_size:
            _fail(
                "DECLARED_SIZE_MISMATCH",
                "declared byte size does not match actual bytes",
                descriptor.logical_path,
            )
        total_bytes += byte_size
        if total_bytes > limits.max_total_bytes:
            _fail(
                "TOTAL_BYTES_LIMIT_EXCEEDED",
                "actual bytes exceed the configured total limit",
                descriptor.logical_path,
            )
        content_digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        if content_digest != descriptor.declared_content_digest:
            _fail(
                "DECLARED_DIGEST_MISMATCH",
                "declared digest does not match actual bytes",
                descriptor.logical_path,
            )
        verified.append(VerifiedResource(
            handle_id=descriptor.handle_id,
            access_mode=ACCESS_MODE_READ_ONLY,
            logical_path=descriptor.logical_path,
            media_type=descriptor.media_type,
            byte_size=byte_size,
            content_digest=content_digest,
            content=payload,
            text=_decode_text(
                descriptor.media_type,
                payload,
                descriptor.logical_path,
            ),
        ))
    return tuple(verified)
