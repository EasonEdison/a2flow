const value = (input) => input ?? null;

export function dependencyNodeIdentity(node) {
  return JSON.stringify([
    node.kind,
    node.key,
    node.source,
    node.environment,
    node.status,
    value(node.assetId),
    value(node.versionId),
    value(node.revision),
    value(node.selection),
  ]);
}

export function dependencyEdgeIdentity(edge) {
  return JSON.stringify([
    dependencyNodeIdentity(edge.from ?? fallbackNode(edge.fromKind, edge.fromKey, edge.source)),
    dependencyNodeIdentity(edge.target ?? fallbackNode(edge.toKind, edge.toKey, edge.source, edge)),
    edge.path,
    edge.selectorType,
    value(edge.requestedVersionId),
  ]);
}

export function initialExpandedNodes(roots) {
  return new Set(roots.map(dependencyNodeIdentity));
}

export function isNavigableDependencyNode(node) {
  return node.kind !== 'COMPONENT' && node.status === 'resolved';
}

function fallbackNode(kind, key, source, edge = {}) {
  return {
    kind,
    key,
    source,
    environment: edge.target?.environment ?? edge.from?.environment ?? 'PRT',
    status: edge.error ? 'missing' : 'resolved',
    versionId: edge.requestedVersionId,
  };
}

export function dependencyEdgeNodes(edge) {
  return [
    edge.from ?? fallbackNode(edge.fromKind, edge.fromKey, edge.source, edge),
    edge.target ?? fallbackNode(edge.toKind, edge.toKey, edge.source, edge),
  ];
}

function compareEdges(left, right) {
  return dependencyEdgeIdentity(left).localeCompare(dependencyEdgeIdentity(right));
}

export function buildLineageView(graph, filters, expanded) {
  const roots = [graph.root, ...(graph.rootVariants ?? [])];
  const rootIds = new Set(roots.map(dependencyNodeIdentity));
  const rootLogicalIds = new Set(roots.map((root) => JSON.stringify([root.kind, root.key])));
  const allowedEdges = [
    ...(filters.direction === 'downstream' ? [] : graph.upstream),
    ...(filters.direction === 'upstream' ? [] : graph.dependents),
  ].filter((edge) => filters.source === 'all' || edge.source === filters.source);
  const uniqueEdges = new Map();
  for (const edge of allowedEdges) uniqueEdges.set(dependencyEdgeIdentity(edge), edge);
  const adjacency = new Map();
  for (const edge of uniqueEdges.values()) {
    const [from, target] = dependencyEdgeNodes(edge);
    for (const node of [from, target]) {
      const id = dependencyNodeIdentity(node);
      if (!adjacency.has(id)) adjacency.set(id, []);
      adjacency.get(id).push(edge);
    }
  }
  const selectedRoots = roots.filter((root, index) => index === 0 || filters.source === 'all' || root.source === filters.source);
  const visibleNodes = new Map(selectedRoots.map((root) => [dependencyNodeIdentity(root), root]));
  for (const edge of uniqueEdges.values()) {
    const [from, target] = dependencyEdgeNodes(edge);
    for (const candidate of [from, target]) {
      if (rootLogicalIds.has(JSON.stringify([candidate.kind, candidate.key]))) {
        visibleNodes.set(dependencyNodeIdentity(candidate), candidate);
      }
    }
  }
  const visibleEdges = new Map();
  const queue = [...visibleNodes.keys()];
  const visited = new Set();
  while (queue.length) {
    const currentId = queue.shift();
    const currentNode = visibleNodes.get(currentId);
    const isRootIdentity = currentNode && rootLogicalIds.has(JSON.stringify([currentNode.kind, currentNode.key]));
    if (visited.has(currentId) || (!expanded.has(currentId) && !isRootIdentity)) continue;
    visited.add(currentId);
    for (const edge of (adjacency.get(currentId) ?? []).sort(compareEdges)) {
      const [from, target] = dependencyEdgeNodes(edge);
      const fromId = dependencyNodeIdentity(from);
      const targetId = dependencyNodeIdentity(target);
      const traversable = filters.direction === 'upstream'
        ? fromId === currentId
        : filters.direction === 'downstream'
          ? targetId === currentId
          : fromId === currentId || targetId === currentId;
      if (!traversable) continue;
      visibleEdges.set(dependencyEdgeIdentity(edge), edge);
      for (const node of [from, target]) {
        const id = dependencyNodeIdentity(node);
        visibleNodes.set(id, node);
        if (expanded.has(id) && !visited.has(id)) queue.push(id);
      }
    }
  }
  const depth = new Map([...rootIds].map((id) => [id, 0]));
  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of visibleEdges.values()) {
      const [from, target] = dependencyEdgeNodes(edge);
      const fromId = dependencyNodeIdentity(from);
      const targetId = dependencyNodeIdentity(target);
      if (depth.has(fromId) && !depth.has(targetId)) { depth.set(targetId, depth.get(fromId) + 1); changed = true; }
      if (depth.has(targetId) && !depth.has(fromId)) { depth.set(fromId, depth.get(targetId) - 1); changed = true; }
    }
  }
  const ordered = [...visibleNodes.values()].sort((left, right) => {
    const difference = (depth.get(dependencyNodeIdentity(left)) ?? 0) - (depth.get(dependencyNodeIdentity(right)) ?? 0);
    return difference || dependencyNodeIdentity(left).localeCompare(dependencyNodeIdentity(right));
  });
  const rows = new Map();
  const nodes = ordered.map((node) => {
    const level = depth.get(dependencyNodeIdentity(node)) ?? 0;
    const row = rows.get(level) ?? 0;
    rows.set(level, row + 1);
    return { ...node, x: (level + 8) * 220 + 40, y: row * 112 + 42 };
  });
  return { nodes, edges: [...visibleEdges.values()].sort(compareEdges) };
}
