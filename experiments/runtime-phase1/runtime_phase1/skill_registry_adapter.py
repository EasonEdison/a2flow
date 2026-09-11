"""Experiment-only bridge from shared Runtime context to Skill Registry."""

from skill_registry import (
    InvocationScope as RegistryInvocationScope,
    MaterialPort,
    TrustedContext as RegistryTrustedContext,
    TrustedInvocationContext as RegistryInvocationContext,
    UseSkillRequest,
    use_skill as registry_use_skill,
)
from skillweave_contracts import TrustedInvocationContext


class SkillRegistryResolver:
    """Call the integrated Skill Registry without changing its public contract."""

    def __init__(self, material_port: MaterialPort) -> None:
        self._material_port = material_port

    def __call__(
        self,
        skill_key: str,
        context: TrustedInvocationContext,
    ) -> dict[str, object]:
        """Translate trusted structural types and return the approved result."""

        scope = context.invocation_scope
        registry_scope = RegistryInvocationScope(
            kind=scope.kind,
            conversation_id=getattr(scope, "conversation_id", None),
            run_id=getattr(scope, "run_id", None),
            node_id=getattr(scope, "node_id", None),
        )
        registry_context = RegistryInvocationContext(
            contract_revision=context.contract_revision,
            trusted_context=RegistryTrustedContext(
                user_id=context.trusted_context.user_id,
                environment=context.trusted_context.environment,
            ),
            invocation_scope=registry_scope,
            control_request_id=context.control_request_id,
        )
        result = registry_use_skill(
            UseSkillRequest(skill_key=skill_key),
            registry_context,
            self._material_port,
        )
        return result.to_mapping()
