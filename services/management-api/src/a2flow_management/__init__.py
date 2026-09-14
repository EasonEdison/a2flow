"""Trusted modular management surface for A2Flow assets."""
from .contracts import (
    ManagedDraft, ManagementError, PublicationPlan, PublicationTarget,
    TrustedManagementContext, ValidationReport, require_admin,
)
from .repositories import DraftRepository, MemoryDraftRepository, PostgresDraftRepository
from .service import ManagementFeature, ManagementService

__all__ = [
    "DraftRepository", "ManagedDraft", "ManagementError", "ManagementFeature",
    "ManagementService", "MemoryDraftRepository", "PostgresDraftRepository",
    "PublicationPlan", "PublicationTarget", "TrustedManagementContext",
    "ValidationReport", "require_admin",
]
