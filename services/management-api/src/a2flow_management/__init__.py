"""Trusted modular management surface for A2Flow assets."""

from .contracts import (
    ManagedDraft,
    ManagementError,
    PublicationPlan,
    PublicationTarget,
    TrustedManagementContext,
    ValidationReport,
    require_admin,
)
from .draft_models import parse_draft_structure
from .publication import PublicationService
from .repositories import DraftRepository, MemoryDraftRepository, PostgresDraftRepository
from .service import ManagementFeature, ManagementService

__all__ = [
    "DraftRepository",
    "ManagedDraft",
    "ManagementError",
    "ManagementFeature",
    "ManagementService",
    "MemoryDraftRepository",
    "PostgresDraftRepository",
    "PublicationPlan",
    "PublicationService",
    "PublicationTarget",
    "TrustedManagementContext",
    "ValidationReport",
    "parse_draft_structure",
    "require_admin",
]
