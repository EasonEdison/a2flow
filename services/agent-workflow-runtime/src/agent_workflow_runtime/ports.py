"""Narrow trusted ports shared by the Action service and PostgreSQL adapter."""

from contextlib import AbstractContextManager
from typing import Protocol

from skillweave_contracts import TrustedContext

from .models import ActionConfig, Interaction


class InteractionRepository(Protocol):
    """Serialize controls by trusted user/environment/run; save commits immediately.

    Native graph continuation runs outside this scope to permit SDK worker reads.
    continuation_scope is a distinct run-scoped delivery lock; graph Tools must
    never acquire it. It serializes different accepted controls targeting the same
    native graph, without holding the admission lock while SDK workers replay.
    Each save must survive later executor/graph exceptions: this is not a unit of
    work rolled back when the scope exits. Stop acceptance and competing controls
    must use the same serialization boundary. Every read/write requires an owning
    scope; check_scope detects connection loss but cannot fence in-flight effects.
    """

    def scope(self, owner: TrustedContext, run_id: str) -> AbstractContextManager: ...
    def continuation_scope(self, owner: TrustedContext, run_id: str) -> AbstractContextManager: ...
    def check_scope(self) -> None: ...
    def for_run(self, owner: TrustedContext, run_id: str) -> tuple[Interaction, ...]: ...
    def get(self, key: tuple[str, str, str], owner: TrustedContext) -> Interaction | None: ...
    def save(self, interaction: Interaction) -> None: ...
    def for_node(self, owner: TrustedContext, run_id: str, node_id: str) -> tuple[Interaction, ...]: ...


class ConfigurationPort(Protocol):
    """Resolve current environment-local configuration and full recorded closure."""

    def versions(self, interaction: Interaction) -> tuple[tuple[str, str], ...]: ...
    def action(self, interaction: Interaction, action_name: str) -> ActionConfig: ...


class ExecutorPort(Protocol):
    """Execute one trusted configured operation; returned data is business evidence."""

    def __call__(self, config: ActionConfig, inputs: object, owner: TrustedContext) -> object: ...


class ContinuationPort(Protocol):
    """Dispatch only a saved successful completion, never arbitrary client booleans."""

    def __call__(self, interaction: Interaction, control_request_id: str) -> object: ...
