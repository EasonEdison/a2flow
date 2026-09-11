"""Build operator seed documents from original files, never a runtime fallback."""
import base64
from pathlib import Path

from a2flow_asset_store.records import canonical, digest
from . import (APPLICATION_KEY, BUDGET_KEY, COMPONENT_KEY, CONFIRM_KEY, WORKFLOW_KEY,
               ability_definition, application_definition, component_definition)

NAMESPACE = "a2flow-mvp-activity-planning"


def make_bundle(environment):
    if environment not in ("PRT", "ONLINE"):
        raise ValueError("INVALID_ENVIRONMENT")
    assets = []
    def add(kind, key, definition, dependencies=()):
        value = {"kind": kind, "key": key, "assetId": kind.lower() + "-" + key.replace("/", "-"),
                 "versionId": "v1", "definition": definition,
                 "dependencies": [{"kind": k, "key": v} for k, v in dependencies]}
        assets.append({**value, "contentDigest": digest(canonical(value))})
    add("COMPONENT", COMPONENT_KEY, component_definition())
    for key in (BUDGET_KEY, CONFIRM_KEY):
        add("ABILITY", key, ability_definition(key))
    add("APPLICATION", APPLICATION_KEY, application_definition(),
        (("COMPONENT", COMPONENT_KEY), ("ABILITY", CONFIRM_KEY)))
    root = Path(__file__).resolve().parent.parent
    for directory, key, tools, dependencies in (
        ("activity-plan", "activity-planning/plan", ["execute_ability", "render_application"],
         (("ABILITY", BUDGET_KEY), ("APPLICATION", APPLICATION_KEY))),
        ("activity-copy", "activity-planning/copy", [], ()),
    ):
        raw = (root / directory / "SKILL.md").read_bytes()
        add("SKILL", key, {"entries": [{"handleId": directory + "-instructions",
            "logicalPath": "SKILL.md", "mediaType": "text/markdown", "byteSize": len(raw),
            "contentDigest": digest(raw), "base64": base64.b64encode(raw).decode("ascii")}],
            "requiredToolNames": tools}, dependencies)
    add("WORKFLOW", WORKFLOW_KEY, {
        "definitionKey": WORKFLOW_KEY, "entryNodeId": "plan",
        "nodes": [{"nodeId": "plan", "skillKey": "activity-planning/plan"},
                  {"nodeId": "copy", "skillKey": "activity-planning/copy"}]},
        (("SKILL", "activity-planning/plan"), ("SKILL", "activity-planning/copy")))
    return {"format": "AF-MVP-08-ASSETS-1", "namespace": NAMESPACE,
            "environment": environment, "assets": assets,
            "serving": [{"kind": a["kind"], "key": a["key"],
                "current": "v1" if environment == "PRT" else None,
                "stable": "v1" if environment == "ONLINE" else None,
                "gray": None, "grayUserIds": []} for a in assets]}
