"""Lifecycle-neutral preparation of a published Skill Application.

This layer prepares display material, not a Workflow definition or graph node.
It neither executes business operations nor decides when Chat/Workflow resumes.
The caller owns trusted asset resolution, version admission, surface identity,
durable storage and transport. Model content is never interpreted as a template.
"""

from dataclasses import dataclass
import json

from .models import ActionRejected, json_copy


def validate_choice_data(value):
    """Existing MVP input profile; retained until a new profile is admitted."""
    if type(value) is not dict or set(value) != {"prompt", "options"}:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    if type(value["prompt"]) is not str or not 1 <= len(value["prompt"]) <= 2000:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    options = value["options"]
    if type(options) is not list or not 2 <= len(options) <= 8:
        raise ActionRejected("INVALID_APPLICATION_DATA")
    for option in options:
        if (type(option) is not dict or set(option) != {"label", "value"}
                or type(option["label"]) is not str or not 1 <= len(option["label"]) <= 2000
                or type(option["value"]) is not str or not 1 <= len(option["value"]) <= 128):
            raise ActionRejected("INVALID_APPLICATION_DATA")
    if len({option["value"] for option in options}) != len(options):
        raise ActionRejected("INVALID_APPLICATION_DATA")
    return json_copy(value)


@dataclass(frozen=True)
class PreparedApplication:
    """Immutable display material. Has no user, run, node or checkpoint identity."""

    application_key: str
    application_version: str
    interactive: bool
    display_json: str

    def display(self):
        return json.loads(self.display_json)


class ApplicationRuntime:
    def __init__(self, application_validator, data_validator=None):
        if not callable(application_validator):
            raise ValueError("APPLICATION_VALIDATOR_REQUIRED")
        if data_validator is not None and not callable(data_validator):
            raise ValueError("APPLICATION_DATA_VALIDATOR_INVALID")
        self._application_validator = application_validator
        self._data_validator = data_validator

    def prepare(self, *, application_key, resolved, data, actions):
        """Build a detached view from backend-resolved, published configuration.

        Actions are resolved server-side descriptors, not client/model input.
        This does not grant Action execution or persistence authority.
        """
        application = json_copy(resolved["application"])
        asset = application["asset"]
        if (asset["applicationKey"] != application_key
                or asset["protocolProfileRef"] != "a2flow.mvp08.v1"):
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        if self._application_validator(application) is not True:
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        policy = application["renderPolicy"]
        interactive = policy == {
            "tool": "render_application", "interactionMode": "INTERACTIVE",
            "requiresPause": True,
        }
        display_only = policy == {
            "tool": "render_application", "interactionMode": "DISPLAY_ONLY",
            "requiresPause": False,
        }
        if not interactive and not display_only:
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        if type(actions) is not list or (interactive and not actions) or (display_only and actions):
            raise ActionRejected("UNSUPPORTED_APPLICATION_PROFILE")
        names = []
        for action in actions:
            if (type(action) is not dict or set(action) != {"actionName", "inputSchema"}
                    or type(action["actionName"]) is not str or not action["actionName"]
                    or type(action["inputSchema"]) is not dict):
                raise ActionRejected("INVALID_APPLICATION_ACTION")
            names.append(action["actionName"])
        if len(names) != len(set(names)):
            raise ActionRejected("INVALID_APPLICATION_ACTION")
        safe_data = json_copy(data)
        if self._data_validator is None:
            safe_data = validate_choice_data(safe_data)
        elif self._data_validator(application, safe_data) is not True:
            raise ActionRejected("INVALID_APPLICATION_DATA")
        version = resolved["resolvedVersion"]["versionId"]
        if type(version) is not str or not version:
            raise ActionRejected("APPLICATION_VERSION_REQUIRED")
        template = application["surfaceTemplate"]
        display = {
            "applicationKey": application_key, "applicationVersion": version,
            "protocolProfile": asset["protocolProfileRef"],
            "componentCatalogRef": asset["componentCatalogRef"],
            "rootId": template["rootId"], "components": template["components"],
            "data": safe_data, "inputSchema": template["inputSchema"],
            "actions": json_copy(actions),
        }
        return PreparedApplication(application_key, version, interactive,
            json.dumps(display, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False))
