"""Build the independent additive three-node demo bundle."""
import base64
from pathlib import Path

from a2flow_asset_store.records import canonical, digest
from . import (
    PACKAGE_APPLICATION_KEYS,
    PACKAGE_CHOOSE_APPLICATION_KEY,
    PACKAGE_COMPONENT_KEY,
    PACKAGE_DISPLAY_APPLICATION_KEY,
    PACKAGE_SCHEDULE_ABILITY_KEY,
    PACKAGE_SCHEDULE_APPLICATION_KEY,
    PACKAGE_SELECT_ABILITY_KEY,
    PACKAGE_WORKFLOW_KEY,
    ability_definition,
    package_application_definition,
    package_component_definition,
)
from .bundle import NAMESPACE


def make_package_bundle(environment):
    if environment not in ("PRT", "ONLINE"):
        raise ValueError("INVALID_ENVIRONMENT")
    assets = []

    def add(kind, key, definition, dependencies=()):
        value = {
            "kind": kind, "key": key,
            "assetId": kind.lower() + "-" + key.replace("/", "-"),
            "versionId": "v1", "definition": definition,
            "dependencies": [{"kind": item_kind, "key": item_key}
                             for item_kind, item_key in dependencies],
        }
        assets.append({**value, "contentDigest": digest(canonical(value))})

    add("COMPONENT", PACKAGE_COMPONENT_KEY, package_component_definition())
    for key in (PACKAGE_SELECT_ABILITY_KEY, PACKAGE_SCHEDULE_ABILITY_KEY):
        add("ABILITY", key, ability_definition(key))
    for key in sorted(PACKAGE_APPLICATION_KEYS):
        ability = {
            PACKAGE_CHOOSE_APPLICATION_KEY: PACKAGE_SELECT_ABILITY_KEY,
            PACKAGE_SCHEDULE_APPLICATION_KEY: PACKAGE_SCHEDULE_ABILITY_KEY,
        }.get(key)
        dependencies = [("COMPONENT", PACKAGE_COMPONENT_KEY)]
        if ability is not None:
            dependencies.append(("ABILITY", ability))
        add("APPLICATION", key, package_application_definition(key), dependencies)

    root = Path(__file__).resolve().parent.parent
    skills = (
        ("activity-choose-plan", "activity-package/choose-plan"),
        ("activity-confirm-schedule", "activity-package/confirm-schedule"),
        ("activity-show-package", "activity-package/show-package"),
    )
    for directory, key in skills:
        raw = (root / directory / "SKILL.md").read_bytes()
        add("SKILL", key, {"entries": [{
            "handleId": directory + "-instructions", "logicalPath": "SKILL.md",
            "mediaType": "text/markdown", "byteSize": len(raw),
            "contentDigest": digest(raw),
            "base64": base64.b64encode(raw).decode("ascii"),
        }], "requiredToolNames": ["render_application"]}, (
            ("APPLICATION", {
                "activity-choose-plan": PACKAGE_CHOOSE_APPLICATION_KEY,
                "activity-confirm-schedule": PACKAGE_SCHEDULE_APPLICATION_KEY,
                "activity-show-package": PACKAGE_DISPLAY_APPLICATION_KEY,
            }[directory]),
        ))
    nodes = [
        {"nodeId": "choose_plan", "skillKey": "activity-package/choose-plan"},
        {"nodeId": "confirm_schedule", "skillKey": "activity-package/confirm-schedule"},
        {"nodeId": "show_activity_package", "skillKey": "activity-package/show-package"},
    ]
    add("WORKFLOW", PACKAGE_WORKFLOW_KEY, {
        "definitionKey": PACKAGE_WORKFLOW_KEY,
        "entryNodeId": nodes[0]["nodeId"], "nodes": nodes,
    }, tuple(("SKILL", node["skillKey"]) for node in nodes))
    return {
        "format": "AF-MVP-08-ASSETS-1", "namespace": NAMESPACE,
        "environment": environment, "assets": assets,
        "serving": [{
            "kind": asset["kind"], "key": asset["key"],
            "current": "v1" if environment == "PRT" else None,
            "stable": "v1" if environment == "ONLINE" else None,
            "gray": None, "grayUserIds": [],
        } for asset in assets],
    }
