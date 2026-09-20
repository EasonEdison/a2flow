from collections import deque

from a2flow_asset_store.records import AssetError, KINDS

from .contracts import ManagementError, require_reader


DEFAULT_MAX_DEPTH = 8
DEFAULT_MAX_NODES = 128
DEFAULT_MAX_EDGES = 256


def _reference(kind, key, path, version_id=None):
    value = {
        "toKind": kind,
        "toKey": key,
        "path": path,
        "selectorType": "exact-release" if version_id else "logical-key",
    }
    if version_id:
        value["requestedVersionId"] = version_id
    return value


def extract_references(kind, document, source):
    if type(document) is not dict:
        return (), ("/",)
    definition = document.get("definition") if source != "saved-draft" else document
    if kind == "APPLICATION" and source == "saved-draft":
        definition = document.get("definition")
    if type(definition) is not dict:
        return (), ("/definition",)
    result = []
    malformed = []
    if kind == "SKILL":
        if source == "saved-draft":
            fields = (("abilityBindings", "ABILITY"),
                      ("applicationBindings", "APPLICATION"))
            for field, target_kind in fields:
                values = definition.get(field, [])
                if type(values) is not list:
                    malformed.append(f"/{field}")
                    continue
                for index, key in enumerate(values):
                    if type(key) is str:
                        result.append(_reference(
                            target_kind, key, f"/{field}/{index}"))
                    else:
                        malformed.append(f"/{field}/{index}")
        else:
            dependencies = document.get("dependencies", [])
            if type(dependencies) is not list:
                return (), ("/dependencies",)
            indexes = {"ABILITY": 0, "APPLICATION": 0}
            for index, dependency in enumerate(dependencies):
                if (type(dependency) is dict
                        and dependency.get("kind") in indexes
                        and type(dependency.get("key")) is str):
                    target_kind = dependency["kind"]
                    field_index = indexes[target_kind]
                    indexes[target_kind] += 1
                    field = "abilityBindings" if target_kind == "ABILITY" else "applicationBindings"
                    result.append(_reference(
                        target_kind, dependency["key"], f"/{field}/{field_index}"))
                elif type(dependency) is not dict:
                    malformed.append(f"/dependencies/{index}")
    elif kind == "APPLICATION":
        asset = definition.get("asset")
        if type(asset) is dict and type(asset.get("componentCatalogRef")) is str:
            result.append(_reference(
                "COMPONENT", asset["componentCatalogRef"],
                "/definition/asset/componentCatalogRef"))
        elif asset is not None:
            malformed.append("/definition/asset")
        policies = definition.get("actionPolicies", [])
        if type(policies) is not list:
            malformed.append("/definition/actionPolicies")
        else:
            for index, policy in enumerate(policies):
                path = f"/definition/actionPolicies/{index}/abilityReleaseRef"
                release = policy.get("abilityReleaseRef") if type(policy) is dict else None
                if type(release) is not str or release.count("@") != 1:
                    malformed.append(path)
                    continue
                key, version_id = release.split("@")
                if not key or not version_id:
                    malformed.append(path)
                    continue
                result.append(_reference("ABILITY", key, path, version_id))
    elif kind == "WORKFLOW":
        nodes = definition.get("nodes", [])
        prefix = "" if source == "saved-draft" else "/definition"
        if type(nodes) is not list:
            malformed.append(f"{prefix}/nodes")
        else:
            for index, node in enumerate(nodes):
                key = node.get("skillKey") if type(node) is dict else None
                if type(key) is str:
                    result.append(_reference(
                        "SKILL", key, f"{prefix}/nodes/{index}/skillKey"))
                else:
                    malformed.append(f"{prefix}/nodes/{index}/skillKey")
    return tuple(result), tuple(malformed)


class DependencyService:
    def __init__(self, repository, drafts, namespace):
        self.repository = repository
        self.drafts = drafts
        self.namespace = namespace
        if getattr(repository, "environment", None) != getattr(drafts, "environment", None):
            raise ManagementError("DRAFT_ENVIRONMENT_MISMATCH")

    def inspect(self, context, kind, key, *, max_depth=DEFAULT_MAX_DEPTH,
                max_nodes=DEFAULT_MAX_NODES, max_edges=DEFAULT_MAX_EDGES,
                root_sources=None):
        require_reader(context)
        if context.environment != self.repository.environment:
            raise ManagementError("TRUSTED_ENVIRONMENT_MISMATCH", 403)
        if kind not in KINDS or type(key) is not str:
            raise ManagementError("INVALID_ASSET_IDENTITY")
        if (type(max_depth) is not int or not 0 <= max_depth <= DEFAULT_MAX_DEPTH
                or type(max_nodes) is not int or not 1 <= max_nodes <= DEFAULT_MAX_NODES
                or type(max_edges) is not int or not 1 <= max_edges <= DEFAULT_MAX_EDGES):
            raise ManagementError("INVALID_DEPENDENCY_BOUNDS")
        allowed_sources = {"published", "saved-draft"}
        if root_sources is None:
            root_sources = ("published", "saved-draft")
        if (type(root_sources) is not tuple or not root_sources
                or not set(root_sources) <= allowed_sources):
            raise ManagementError("INVALID_DEPENDENCY_SOURCE")
        if "saved-draft" in root_sources and "ADMIN" not in context.roles:
            root_sources = tuple(source for source in root_sources if source != "saved-draft")
        try:
            bundle = self.repository.read(self.namespace)
        except AssetError as error:
            raise ManagementError(error.code, 404 if error.code == "ASSET_NOT_FOUND" else 400) from None
        if bundle.namespace != self.namespace or bundle.environment != context.environment:
            raise ManagementError("DESTINATION_MISMATCH", 403)
        state_by_identity = {
            (state["kind"], state["key"]): state for state in bundle.serving
        }
        assets_by_version = {asset.identity: asset for asset in bundle.assets}

        def selected(identity):
            state = state_by_identity.get(identity)
            if state is None:
                return None, None
            if context.environment == "PRT":
                version_id, selection = state["current"], "PRT_CURRENT"
            elif state["gray"] is not None and context.user_id in state["grayUserIds"]:
                version_id, selection = state["gray"], "ONLINE_GRAY"
            else:
                version_id, selection = state["stable"], "ONLINE_STABLE"
            return assets_by_version.get((*identity, version_id)), selection

        draft_map = {}
        if "ADMIN" in context.roles:
            for draft_kind in (
                    "SKILL", "ABILITY", "APPLICATION", "COMPONENT", "WORKFLOW"):
                for draft in self.drafts.list(self.namespace, draft_kind):
                    draft_map[(draft.kind, draft.key)] = draft

        def asset_node(identity, exact_version=None):
            target, selection = selected(identity)
            source = "published"
            if exact_version is not None:
                target = assets_by_version.get((*identity, exact_version))
                selection = None
                source = "retained"
            if target is None:
                value = {
                    "kind": identity[0], "key": identity[1], "source": source,
                    "environment": context.environment, "status": "missing",
                }
                if exact_version is not None:
                    value["versionId"] = exact_version
                return value
            return {
                "kind": target.kind, "key": target.key, "source": source,
                "assetId": target.asset_id, "versionId": target.version_id,
                "contentDigest": target.content_digest,
                "environment": context.environment, "status": "resolved",
                **({"selection": selection} if selection else {}),
            }

        def draft_node(identity):
            draft = draft_map.get(identity)
            if draft is None:
                return None
            return {
                "kind": identity[0], "key": identity[1], "source": "saved-draft",
                "revision": draft.revision, "contentDigest": draft.content_digest,
                "environment": context.environment, "status": "resolved",
            }

        def node_id(node):
            return (node["kind"], node["key"], node["source"],
                    node.get("versionId"), node.get("revision"))

        root_candidates = []
        root_asset, _ = selected((kind, key))
        if "published" in root_sources and root_asset is not None:
            root_candidates.append((asset_node((kind, key)), root_asset.document))
        if "saved-draft" in root_sources and (kind, key) in draft_map:
            root_candidates.append((draft_node((kind, key)), draft_map[(kind, key)].document))
        if not root_candidates:
            raise ManagementError("ASSET_NOT_FOUND", 404)

        admitted = set()
        roots = []
        truncated = False
        incomplete = False
        for node, document in root_candidates:
            identity = node_id(node)
            if identity not in admitted and len(admitted) >= max_nodes:
                truncated = incomplete = True
                continue
            admitted.add(identity)
            roots.append((node, document))
        root = roots[0][0]
        upstream = []
        dependents = []
        seen_edges = set()
        diagnostics = []
        cycle = False
        edge_count = 0

        def add_diagnostic(node, paths):
            nonlocal incomplete
            if not paths:
                return
            incomplete = True
            value = {
                "code": "MALFORMED_DEPENDENCY_REFERENCE",
                "kind": node["kind"], "key": node["key"],
                "source": node["source"], "paths": list(paths),
            }
            if node.get("versionId") is not None:
                value["versionId"] = node["versionId"]
            if node.get("revision") is not None:
                value["revision"] = node["revision"]
            if value not in diagnostics:
                diagnostics.append(value)

        queue = deque((node, document, 0, (node_id(node),)) for node, document in roots)
        while queue:
            from_node, document, depth, ancestry = queue.popleft()
            references, malformed = extract_references(
                from_node["kind"], document, from_node["source"])
            add_diagnostic(from_node, malformed)
            for reference in references:
                target_identity = reference["toKind"], reference["toKey"]
                target = asset_node(target_identity, reference.get("requestedVersionId"))
                target_id = node_id(target)
                edge_identity = (node_id(from_node), target_id, reference["path"],
                                 reference["selectorType"], reference.get("requestedVersionId"))
                if edge_identity in seen_edges:
                    continue
                if edge_count >= max_edges:
                    truncated = incomplete = True
                    continue
                if target_id not in admitted and len(admitted) >= max_nodes:
                    truncated = incomplete = True
                    continue
                admitted.add(target_id)
                edge = {
                    "fromKind": from_node["kind"], "fromKey": from_node["key"],
                    "source": from_node["source"], "from": from_node,
                    **reference, "target": target, "depth": depth + 1,
                }
                if target["status"] == "missing":
                    edge["error"] = "MISSING_EXACT_VERSION" if reference.get("requestedVersionId") else "MISSING_DEPENDENCY"
                    incomplete = True
                if target_id in ancestry:
                    edge["cycle"] = True
                    cycle = incomplete = True
                upstream.append(edge)
                seen_edges.add(edge_identity)
                edge_count += 1
                if edge.get("cycle") or target["status"] != "resolved":
                    continue
                if depth >= max_depth:
                    truncated = incomplete = True
                    continue
                target_asset = assets_by_version.get(
                    (*target_identity, target.get("versionId")))
                if target_asset is not None:
                    queue.append((target, target_asset.document, depth + 1,
                                  ancestry + (target_id,)))

        documents = []
        for identity in state_by_identity:
            current, _ = selected(identity)
            if current is not None:
                documents.append((asset_node(identity), current.document))
        if "ADMIN" in context.roles:
            documents.extend((draft_node(identity), draft.document)
                             for identity, draft in draft_map.items())
        reverse = {}
        for from_node, document in documents:
            references, malformed = extract_references(
                from_node["kind"], document, from_node["source"])
            for reference in references:
                reverse.setdefault((reference["toKind"], reference["toKey"]), []).append(
                    (from_node, document, reference, malformed))

        reverse_queue = deque((node, 0, (node_id(node),)) for node, _ in roots)
        seen_reverse = set()
        while reverse_queue:
            target_node, depth, ancestry = reverse_queue.popleft()
            target_identity = target_node["kind"], target_node["key"]
            for from_node, document, reference, malformed in reverse.get(target_identity, ()):
                exact_version = reference.get("requestedVersionId")
                referenced_target = asset_node(target_identity, exact_version)
                from_id = node_id(from_node)
                target_id = node_id(referenced_target)
                edge_identity = (from_id, target_id, reference["path"],
                                 reference["selectorType"], exact_version)
                if edge_identity in seen_reverse or edge_identity in seen_edges:
                    continue
                if edge_count >= max_edges:
                    truncated = incomplete = True
                    continue
                new_nodes = {from_id, target_id} - admitted
                if len(admitted) + len(new_nodes) > max_nodes:
                    truncated = incomplete = True
                    continue
                admitted.update(new_nodes)
                seen_reverse.add(edge_identity)
                add_diagnostic(from_node, malformed)
                edge = {
                    "fromKind": from_node["kind"], "fromKey": from_node["key"],
                    "source": from_node["source"], "from": from_node,
                    **reference, "target": referenced_target, "depth": depth + 1,
                }
                if exact_version is not None:
                    edge["targetsInspectedVersion"] = (
                        target_node.get("versionId") == exact_version)
                if from_id in ancestry:
                    edge["cycle"] = True
                    cycle = incomplete = True
                dependents.append(edge)
                edge_count += 1
                if edge.get("cycle"):
                    continue
                if depth >= max_depth:
                    truncated = incomplete = True
                    continue
                reverse_queue.append((from_node, depth + 1,
                                      ancestry + (from_id,)))

        missing = []
        for edge in upstream:
            if edge.get("error"):
                item = {"kind": edge["toKind"], "key": edge["toKey"]}
                if edge.get("requestedVersionId"):
                    item["versionId"] = edge["requestedVersionId"]
                if item not in missing:
                    missing.append(item)
        return {
            "root": root,
            "rootVariants": [node for node, _ in roots],
            "upstream": upstream,
            "dependents": dependents,
            "missing": missing,
            "unresolved": [],
            "diagnostics": diagnostics,
            "cycle": cycle,
            "truncated": truncated,
            "incomplete": incomplete,
            "limits": {"maxDepth": max_depth, "maxNodes": max_nodes,
                       "maxEdges": max_edges},
            "counts": {"nodes": len(admitted), "edges": edge_count},
            "historyScope": "current-selection-and-explicit-retained-references",
        }
