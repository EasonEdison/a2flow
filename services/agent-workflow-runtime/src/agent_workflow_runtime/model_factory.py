"""One DeepSeek SDK factory; no provider registry, fallback or protocol parser."""

from pydantic import SecretStr

from .model_config import ModelConfigurationError, parse_deepseek_configuration
from .service import require_owner


class DeepSeekModelFactory:
    """Host-only configuration/secret resolution; fixtures inject mock HTTP clients.

    A returned ChatDeepSeek remains the native execution/history model. This
    construction boundary alone does not prove provider-field or replay coverage.
    No environment mutation, package installation or automatic provider selection.
    """

    def __init__(self, resolve_configuration, resolve_secret, *,
                 http_client=None, http_async_client=None):
        self._resolve_configuration = resolve_configuration
        self._resolve_secret = resolve_secret
        self._http_client = http_client
        self._http_async_client = http_async_client

    def create(self, logical_reference, owner):
        require_owner(owner)
        if type(logical_reference) is not str or not logical_reference:
            raise ModelConfigurationError("INVALID_MODEL_REFERENCE")
        try:
            configuration = parse_deepseek_configuration(
                self._resolve_configuration(logical_reference, owner),
            )
            try:
                from langchain_deepseek import ChatDeepSeek
            except ImportError:
                raise ModelConfigurationError("DEEPSEEK_ADAPTER_UNAVAILABLE") from None
            secret = self._resolve_secret(configuration.credential_ref, owner)
            if not isinstance(secret, SecretStr) or not secret.get_secret_value():
                raise ModelConfigurationError("MODEL_CREDENTIAL_UNAVAILABLE")
            return ChatDeepSeek(
                model=configuration.model_id, base_url=configuration.endpoint,
                api_key=secret, timeout=configuration.timeout_seconds, max_retries=0,
                http_client=self._http_client, http_async_client=self._http_async_client,
                **configuration.options.sdk_options(),
            )
        except ModelConfigurationError:
            raise
        except Exception:
            raise ModelConfigurationError("MODEL_CONSTRUCTION_FAILED") from None
