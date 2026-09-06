"""Bounded Skill Registry domain primitives released by SW-P1-SUBSET-01."""

from .ports import CatalogPort, MaterialPort, SkillMaterial
from .resources import (
    PackageEntry,
    PackageEntryDescriptor,
    ResourceLimits,
    ResourceValidationError,
    VerifiedResource,
    validate_package_entries,
)
from .use_skill import (
    InvocationScope,
    SkillRegistryValidationError,
    TrustedContext,
    TrustedInvocationContext,
    TrustedResolutionEvidence,
    UseSkillRequest,
    use_skill,
)

__all__ = (
    "CatalogPort",
    "InvocationScope",
    "MaterialPort",
    "PackageEntry",
    "PackageEntryDescriptor",
    "ResourceLimits",
    "ResourceValidationError",
    "SkillMaterial",
    "SkillRegistryValidationError",
    "TrustedContext",
    "TrustedInvocationContext",
    "TrustedResolutionEvidence",
    "UseSkillRequest",
    "VerifiedResource",
    "use_skill",
    "validate_package_entries",
)
