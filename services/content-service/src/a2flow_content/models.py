"""Strict business DTOs; scenario documents decode into closed dataclasses."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TypeAlias, cast
from uuid import UUID

from .errors import ContentError

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]

MIN_I64 = -(1 << 63)
MAX_I64 = (1 << 63) - 1
MAX_REVISION = (1 << 32) - 1
MAX_SOURCE_CHARS = 30_000
MAX_TEXT_CHARS = 200_000
REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}")


class Environment(StrEnum):
    PRT = "PRT"
    ONLINE = "ONLINE"


class OutputFormat(StrEnum):
    ARTICLE = "ARTICLE"
    SPOKEN_SCRIPT = "SPOKEN_SCRIPT"


class ArtifactKind(StrEnum):
    READING_BRIEF = "READING_BRIEF"
    TOPIC_PLAN = "TOPIC_PLAN"
    MANUSCRIPT = "MANUSCRIPT"


class ArtifactOrigin(StrEnum):
    MODEL_GENERATED = "MODEL_GENERATED"
    USER_EDITED = "USER_EDITED"


class ReferenceKind(StrEnum):
    SOURCE = "SOURCE"
    ARTIFACT = "ARTIFACT"


class DecisionType(StrEnum):
    READING = "READING"
    TOPIC = "TOPIC"
    MANUSCRIPT = "MANUSCRIPT"


class ExportFormat(StrEnum):
    MARKDOWN = "MARKDOWN"
    TXT = "TXT"


def text(value: object, field: str, *, maximum: int, optional: bool = False) -> str | None:
    if value is None and optional:
        return None
    if type(value) is not str:
        raise ContentError(f"INVALID_{field}")
    if len(value) > maximum:
        raise ContentError(f"INVALID_{field}")
    if optional and value.strip() == "":
        return None
    if value.strip() == "":
        raise ContentError(f"INVALID_{field}")
    return value


def uuid_value(value: object, field: str) -> UUID:
    if isinstance(value, UUID):
        return value
    if type(value) is not str:
        raise ContentError(f"INVALID_{field}")
    try:
        return UUID(value)
    except ValueError:
        raise ContentError(f"INVALID_{field}") from None


def revision(value: object, field: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_REVISION:
        raise ContentError(f"INVALID_{field}")
    return value


@dataclass(frozen=True, slots=True)
class TrustedContext:
    user_id: int
    environment: Environment
    request_id: str
    trace_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.user_id) is not int or not MIN_I64 <= self.user_id <= MAX_I64:
            raise ContentError("INVALID_TRUSTED_USER", 401)
        if not isinstance(self.environment, Environment):
            raise ContentError("INVALID_TRUSTED_ENVIRONMENT", 401)
        if type(self.request_id) is not str or not REQUEST_ID.fullmatch(self.request_id):
            raise ContentError("INVALID_TRUSTED_REQUEST_ID", 401)
        if self.trace_id is not None:
            text(self.trace_id, "TRACE_ID", maximum=256)


@dataclass(frozen=True, slots=True)
class CreateProjectCommand:
    title: str
    audience: str
    output_format: OutputFormat

    def __post_init__(self) -> None:
        text(self.title, "PROJECT_TITLE", maximum=200)
        text(self.audience, "AUDIENCE", maximum=500)
        if not isinstance(self.output_format, OutputFormat):
            raise ContentError("INVALID_OUTPUT_FORMAT")


@dataclass(frozen=True, slots=True)
class ListProjectsQuery:
    page: int = 1
    page_size: int = 20

    def __post_init__(self) -> None:
        if type(self.page) is not int or self.page < 1:
            raise ContentError("INVALID_PAGE")
        if type(self.page_size) is not int or not 1 <= self.page_size <= 100:
            raise ContentError("INVALID_PAGE_SIZE")


@dataclass(frozen=True, slots=True)
class GetProjectQuery:
    project_id: UUID

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")


@dataclass(frozen=True, slots=True)
class SaveSourceCommand:
    project_id: UUID
    title: str
    body: str
    source_url: str | None
    expected_project_revision: int

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")
        text(self.title, "SOURCE_TITLE", maximum=500)
        text(self.body, "SOURCE_BODY", maximum=MAX_SOURCE_CHARS)
        text(self.source_url, "SOURCE_URL", maximum=2_048, optional=True)
        revision(self.expected_project_revision, "EXPECTED_PROJECT_REVISION")


@dataclass(frozen=True, slots=True)
class GetSourceQuery:
    source_id: UUID

    def __post_init__(self) -> None:
        uuid_value(self.source_id, "SOURCE_ID")


@dataclass(frozen=True, slots=True)
class InputReference:
    kind: ReferenceKind
    id: UUID
    revision: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ReferenceKind):
            raise ContentError("INVALID_REFERENCE_KIND")
        uuid_value(self.id, "REFERENCE_ID")
        revision(self.revision, "REFERENCE_REVISION")


@dataclass(frozen=True, slots=True)
class ReadingPoint:
    id: str
    claim: str
    evidence_quote: str | None
    evidence_locator: str | None
    explanation: str
    model_suggestion: bool = False

    def __post_init__(self) -> None:
        text(self.id, "POINT_ID", maximum=128)
        text(self.claim, "POINT_CLAIM", maximum=2_000)
        evidence = text(self.evidence_quote, "EVIDENCE_QUOTE", maximum=4_000, optional=True)
        text(self.evidence_locator, "EVIDENCE_LOCATOR", maximum=500, optional=True)
        text(self.explanation, "POINT_EXPLANATION", maximum=4_000)
        if type(self.model_suggestion) is not bool:
            raise ContentError("INVALID_MODEL_SUGGESTION")
        if not self.model_suggestion and evidence is None:
            raise ContentError("READING_EVIDENCE_REQUIRED")


@dataclass(frozen=True, slots=True)
class ReadingBrief:
    points: tuple[ReadingPoint, ...]
    questions: tuple[str, ...] = ()
    usable_materials: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.points) is not tuple or not self.points:
            raise ContentError("READING_POINTS_REQUIRED")
        ids = [point.id for point in self.points]
        if len(ids) != len(set(ids)):
            raise ContentError("DUPLICATE_POINT_ID")
        for item in (*self.questions, *self.usable_materials):
            text(item, "READING_TEXT", maximum=4_000)


@dataclass(frozen=True, slots=True)
class TopicOption:
    id: str
    title: str
    angle: str
    audience: str
    rationale: str
    source_point_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        text(self.id, "TOPIC_ID", maximum=128)
        text(self.title, "TOPIC_TITLE", maximum=300)
        text(self.angle, "TOPIC_ANGLE", maximum=2_000)
        text(self.audience, "TOPIC_AUDIENCE", maximum=500)
        text(self.rationale, "TOPIC_RATIONALE", maximum=2_000)
        if type(self.source_point_ids) is not tuple:
            raise ContentError("INVALID_SOURCE_POINT_IDS")
        for item in self.source_point_ids:
            text(item, "POINT_ID", maximum=128)


@dataclass(frozen=True, slots=True)
class TopicPlan:
    topics: tuple[TopicOption, ...]

    def __post_init__(self) -> None:
        if type(self.topics) is not tuple or not self.topics:
            raise ContentError("TOPICS_REQUIRED")
        ids = [topic.id for topic in self.topics]
        if len(ids) != len(set(ids)):
            raise ContentError("DUPLICATE_TOPIC_ID")


@dataclass(frozen=True, slots=True)
class Citation:
    reference_kind: ReferenceKind
    reference_id: UUID
    revision: int
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.reference_kind, ReferenceKind):
            raise ContentError("INVALID_REFERENCE_KIND")
        uuid_value(self.reference_id, "REFERENCE_ID")
        revision(self.revision, "REFERENCE_REVISION")
        text(self.label, "CITATION_LABEL", maximum=500)


@dataclass(frozen=True, slots=True)
class Manuscript:
    title: str
    body_markdown: str
    citations: tuple[Citation, ...] = ()

    def __post_init__(self) -> None:
        text(self.title, "MANUSCRIPT_TITLE", maximum=300)
        text(self.body_markdown, "MANUSCRIPT_BODY", maximum=MAX_TEXT_CHARS)
        if type(self.citations) is not tuple:
            raise ContentError("INVALID_CITATIONS")


ArtifactBody: TypeAlias = ReadingBrief | TopicPlan | Manuscript


@dataclass(frozen=True, slots=True)
class SaveArtifactCommand:
    project_id: UUID
    kind: ArtifactKind
    body: ArtifactBody
    input_refs: tuple[InputReference, ...]
    origin: ArtifactOrigin

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")
        if not isinstance(self.kind, ArtifactKind):
            raise ContentError("INVALID_ARTIFACT_KIND")
        expected = {
            ArtifactKind.READING_BRIEF: ReadingBrief,
            ArtifactKind.TOPIC_PLAN: TopicPlan,
            ArtifactKind.MANUSCRIPT: Manuscript,
        }[self.kind]
        if not isinstance(self.body, expected):
            raise ContentError("ARTIFACT_BODY_KIND_MISMATCH")
        if type(self.input_refs) is not tuple or not self.input_refs:
            raise ContentError("INPUT_REFERENCES_REQUIRED")
        keys = [(item.kind, item.id, item.revision) for item in self.input_refs]
        if len(keys) != len(set(keys)):
            raise ContentError("DUPLICATE_INPUT_REFERENCE")
        if not isinstance(self.origin, ArtifactOrigin):
            raise ContentError("INVALID_ARTIFACT_ORIGIN")


@dataclass(frozen=True, slots=True)
class GetArtifactQuery:
    artifact_id: UUID

    def __post_init__(self) -> None:
        uuid_value(self.artifact_id, "ARTIFACT_ID")


@dataclass(frozen=True, slots=True)
class GetConfirmationQuery:
    confirmation_id: UUID

    def __post_init__(self) -> None:
        uuid_value(self.confirmation_id, "CONFIRMATION_ID")


@dataclass(frozen=True, slots=True)
class ConfirmReadingCommand:
    project_id: UUID
    artifact_id: UUID
    selected_point_ids: tuple[str, ...]
    user_notes: str | None
    expected_project_revision: int

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")
        uuid_value(self.artifact_id, "ARTIFACT_ID")
        if type(self.selected_point_ids) is not tuple or not self.selected_point_ids:
            raise ContentError("SELECTED_POINTS_REQUIRED")
        if len(self.selected_point_ids) != len(set(self.selected_point_ids)):
            raise ContentError("DUPLICATE_SELECTED_POINT")
        for item in self.selected_point_ids:
            text(item, "POINT_ID", maximum=128)
        text(self.user_notes, "USER_NOTES", maximum=8_000, optional=True)
        revision(self.expected_project_revision, "EXPECTED_PROJECT_REVISION")


@dataclass(frozen=True, slots=True)
class ConfirmTopicCommand:
    project_id: UUID
    artifact_id: UUID
    topic_id: str
    edited_title: str
    edited_angle: str
    expected_project_revision: int

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")
        uuid_value(self.artifact_id, "ARTIFACT_ID")
        text(self.topic_id, "TOPIC_ID", maximum=128)
        text(self.edited_title, "TOPIC_TITLE", maximum=300)
        text(self.edited_angle, "TOPIC_ANGLE", maximum=2_000)
        revision(self.expected_project_revision, "EXPECTED_PROJECT_REVISION")


@dataclass(frozen=True, slots=True)
class ConfirmManuscriptCommand:
    project_id: UUID
    artifact_id: UUID
    expected_project_revision: int

    def __post_init__(self) -> None:
        uuid_value(self.project_id, "PROJECT_ID")
        uuid_value(self.artifact_id, "ARTIFACT_ID")
        revision(self.expected_project_revision, "EXPECTED_PROJECT_REVISION")


@dataclass(frozen=True, slots=True)
class ExportManuscriptQuery:
    artifact_id: UUID
    format: ExportFormat

    def __post_init__(self) -> None:
        uuid_value(self.artifact_id, "ARTIFACT_ID")
        if not isinstance(self.format, ExportFormat):
            raise ContentError("INVALID_EXPORT_FORMAT")


@dataclass(frozen=True, slots=True)
class ProjectRecord:
    id: UUID
    title: str
    audience: str
    output_format: OutputFormat
    current_source_id: UUID | None
    current_selection_id: UUID | None
    current_manuscript_id: UUID | None
    revision: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProjectPage:
    items: tuple[ProjectRecord, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True, slots=True)
class SourceRecord:
    id: UUID
    project_id: UUID
    revision: int
    title: str
    source_url: str | None
    body: str
    digest: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ArtifactRecord:
    id: UUID
    project_id: UUID
    kind: ArtifactKind
    revision: int
    body: ArtifactBody
    input_refs: tuple[InputReference, ...]
    origin: ArtifactOrigin
    created_at: datetime

    @property
    def body_markdown(self) -> str:
        return self.body.body_markdown if isinstance(self.body, Manuscript) else ""


@dataclass(frozen=True, slots=True)
class ReadingSelection:
    selected_point_ids: tuple[str, ...]
    user_notes: str | None


@dataclass(frozen=True, slots=True)
class TopicSelection:
    topic_id: str
    edited_title: str
    edited_angle: str


@dataclass(frozen=True, slots=True)
class ManuscriptSelection:
    artifact_revision: int


ConfirmationSelection: TypeAlias = ReadingSelection | TopicSelection | ManuscriptSelection


@dataclass(frozen=True, slots=True)
class ConfirmationRecord:
    id: UUID
    project_id: UUID
    artifact_id: UUID
    decision_type: DecisionType
    selection: ConfirmationSelection
    created_at: datetime


@dataclass(frozen=True, slots=True)
class ExportedManuscript:
    filename: str
    media_type: str
    content: str


def canonical_json(value: JsonValue) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ContentError("INVALID_JSON") from None


def payload_digest(value: JsonValue) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def reference_json(item: InputReference) -> JsonObject:
    return {"kind": item.kind.value, "id": str(item.id), "revision": item.revision}


def body_json(body: ArtifactBody) -> JsonObject:
    if isinstance(body, ReadingBrief):
        return {
            "type": ArtifactKind.READING_BRIEF.value,
            "points": [
                {
                    "id": item.id,
                    "claim": item.claim,
                    "evidenceQuote": item.evidence_quote,
                    "evidenceLocator": item.evidence_locator,
                    "explanation": item.explanation,
                    "modelSuggestion": item.model_suggestion,
                }
                for item in body.points
            ],
            "questions": list(body.questions),
            "usableMaterials": list(body.usable_materials),
        }
    if isinstance(body, TopicPlan):
        return {
            "type": ArtifactKind.TOPIC_PLAN.value,
            "topics": [
                {
                    "id": item.id,
                    "title": item.title,
                    "angle": item.angle,
                    "audience": item.audience,
                    "rationale": item.rationale,
                    "sourcePointIds": list(item.source_point_ids),
                }
                for item in body.topics
            ],
        }
    return {
        "type": ArtifactKind.MANUSCRIPT.value,
        "title": body.title,
        "bodyMarkdown": body.body_markdown,
        "citations": [
            {
                "referenceKind": item.reference_kind.value,
                "referenceId": str(item.reference_id),
                "revision": item.revision,
                "label": item.label,
            }
            for item in body.citations
        ],
    }


def _object(value: object, code: str) -> dict[str, object]:
    if type(value) is not dict or not all(type(key) is str for key in value):
        raise ContentError(code)
    return cast(dict[str, object], value)


def _list(value: object, code: str) -> list[object]:
    if type(value) is not list:
        raise ContentError(code)
    return cast(list[object], value)


def body_from_json(raw: object) -> ArtifactBody:
    value = _object(raw, "INVALID_ARTIFACT_BODY")
    try:
        kind = ArtifactKind(cast(str, value.get("type")))
    except (TypeError, ValueError):
        raise ContentError("INVALID_ARTIFACT_BODY_TYPE") from None
    if kind is ArtifactKind.READING_BRIEF:
        points: list[ReadingPoint] = []
        for raw_point in _list(value.get("points"), "INVALID_READING_POINTS"):
            point = _object(raw_point, "INVALID_READING_POINT")
            suggestion = point.get("modelSuggestion", False)
            if type(suggestion) is not bool:
                raise ContentError("INVALID_MODEL_SUGGESTION")
            points.append(
                ReadingPoint(
                    cast(str, text(point.get("id"), "POINT_ID", maximum=128)),
                    cast(str, text(point.get("claim"), "POINT_CLAIM", maximum=2_000)),
                    text(
                        point.get("evidenceQuote"), "EVIDENCE_QUOTE", maximum=4_000, optional=True
                    ),
                    text(
                        point.get("evidenceLocator"), "EVIDENCE_LOCATOR", maximum=500, optional=True
                    ),
                    cast(str, text(point.get("explanation"), "POINT_EXPLANATION", maximum=4_000)),
                    suggestion,
                )
            )
        questions = tuple(
            cast(str, text(item, "READING_TEXT", maximum=4_000))
            for item in _list(value.get("questions", []), "INVALID_READING_QUESTIONS")
        )
        materials = tuple(
            cast(str, text(item, "READING_TEXT", maximum=4_000))
            for item in _list(value.get("usableMaterials", []), "INVALID_USABLE_MATERIALS")
        )
        return ReadingBrief(tuple(points), questions, materials)
    if kind is ArtifactKind.TOPIC_PLAN:
        topics: list[TopicOption] = []
        for raw_topic in _list(value.get("topics"), "INVALID_TOPICS"):
            item = _object(raw_topic, "INVALID_TOPIC")
            source_ids = tuple(
                cast(str, text(point_id, "POINT_ID", maximum=128))
                for point_id in _list(item.get("sourcePointIds", []), "INVALID_SOURCE_POINT_IDS")
            )
            topics.append(
                TopicOption(
                    cast(str, text(item.get("id"), "TOPIC_ID", maximum=128)),
                    cast(str, text(item.get("title"), "TOPIC_TITLE", maximum=300)),
                    cast(str, text(item.get("angle"), "TOPIC_ANGLE", maximum=2_000)),
                    cast(str, text(item.get("audience"), "TOPIC_AUDIENCE", maximum=500)),
                    cast(str, text(item.get("rationale"), "TOPIC_RATIONALE", maximum=2_000)),
                    source_ids,
                )
            )
        return TopicPlan(tuple(topics))
    citations: list[Citation] = []
    for raw_citation in _list(value.get("citations", []), "INVALID_CITATIONS"):
        item = _object(raw_citation, "INVALID_CITATION")
        try:
            reference_kind = ReferenceKind(cast(str, item.get("referenceKind")))
        except (TypeError, ValueError):
            raise ContentError("INVALID_REFERENCE_KIND") from None
        citations.append(
            Citation(
                reference_kind,
                uuid_value(item.get("referenceId"), "REFERENCE_ID"),
                revision(item.get("revision"), "REFERENCE_REVISION"),
                cast(str, text(item.get("label"), "CITATION_LABEL", maximum=500)),
            )
        )
    return Manuscript(
        cast(str, text(value.get("title"), "MANUSCRIPT_TITLE", maximum=300)),
        cast(str, text(value.get("bodyMarkdown"), "MANUSCRIPT_BODY", maximum=MAX_TEXT_CHARS)),
        tuple(citations),
    )
