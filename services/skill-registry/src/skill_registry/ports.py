"""Application ports for catalog discovery and trusted material loading."""

from __future__ import unicode_literals

from abc import ABCMeta, abstractmethod
from collections import namedtuple


class SkillMaterial(namedtuple(
        "_SkillMaterial",
        (
            "instructions",
            "entries",
            "required_tool_names",
            "resolution_evidence",
        ))):
    """Immutable material returned by a trusted adapter implementation."""

    __slots__ = ()


class CatalogPort(object, metaclass=ABCMeta):
    """Port for environment-local catalog discovery.

    Implementations own authorization and persistence. This domain interface does
    not provide a production fallback.
    """

    @abstractmethod
    def list_skills(self, trusted_context):
        """Return descriptors visible under the server-supplied context."""


class MaterialPort(object, metaclass=ABCMeta):
    """Port for loading one resolved Skill from trusted infrastructure."""

    @abstractmethod
    def load_skill(self, skill_key, trusted_context):
        """Return SkillMaterial without accepting a model-selected locator."""
