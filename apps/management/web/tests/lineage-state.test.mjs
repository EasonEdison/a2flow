import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildLineageView,
  dependencyEdgeIdentity,
  dependencyNodeIdentity,
  initialExpandedNodes,
  isNavigableDependencyNode,
} from '../src/lineage-state.js';

const node = (kind, key, source = 'published', versionId = 'v1', extra = {}) => ({
  kind, key, source, environment: 'PRT', status: 'resolved', versionId, ...extra,
});
const edge = (from, target, path, extra = {}) => ({
  fromKind: from.kind, fromKey: from.key, toKind: target.kind, toKey: target.key,
  source: from.source, path, selectorType: 'logical-key', from, target, depth: 1, ...extra,
});
const graph = (root, upstream = [], dependents = [], extra = {}) => ({
  root, rootVariants: [root], upstream, dependents, missing: [], unresolved: [], diagnostics: [],
  cycle: false, truncated: false, incomplete: false,
  limits: { maxDepth: 8, maxNodes: 128, maxEdges: 256 }, counts: { nodes: 1, edges: 0 },
  historyScope: 'current-selection-and-explicit-retained-references', ...extra,
});

test('node identities preserve structured values without delimiter collisions', () => {
  const first = node('SKILL', 'a:b', 'retained', 'c');
  const second = node('SKILL', 'a', 'retained', 'b:c');
  assert.notEqual(dependencyNodeIdentity(first), dependencyNodeIdentity(second));
  assert.deepEqual(JSON.parse(dependencyNodeIdentity(first)), ['SKILL', 'a:b', 'retained', 'PRT', 'resolved', null, 'c', null, null]);
});

test('two retained versions of one logical key remain separate nodes and edges', () => {
  const root = node('ABILITY', 'ability.one', 'published', 'v2');
  const app1 = node('APPLICATION', 'app/one', 'published', 'v1');
  const app2 = node('APPLICATION', 'app/two', 'published', 'v1');
  const retained1 = node('ABILITY', 'ability.one', 'retained', 'v1');
  const retained2 = node('ABILITY', 'ability.one', 'retained', 'v2');
  const edges = [
    edge(app1, retained1, '/release', { selectorType: 'exact-release', requestedVersionId: 'v1', targetsInspectedVersion: false }),
    edge(app2, retained2, '/release', { selectorType: 'exact-release', requestedVersionId: 'v2', targetsInspectedVersion: true }),
  ];
  const view = buildLineageView(graph(root, [], edges), { direction: 'downstream', source: 'all' }, initialExpandedNodes([root]));
  assert.equal(view.nodes.filter((item) => item.key === 'ability.one').length, 3);
  assert.equal(new Set(view.edges.map(dependencyEdgeIdentity)).size, 2);
  assert.deepEqual(view.edges.map((item) => item.targetsInspectedVersion), [false, true]);
});

test('logical and exact references remain distinct with paths and inspection evidence', () => {
  const root = node('SKILL', 'root');
  const target = node('ABILITY', 'lookup');
  const retained = node('ABILITY', 'lookup', 'retained', 'v0');
  const edges = [
    edge(root, target, '/bindings/0'),
    edge(root, retained, '/bindings/1', { selectorType: 'exact-release', requestedVersionId: 'v0', targetsInspectedVersion: false }),
  ];
  const view = buildLineageView(graph(root, edges), { direction: 'upstream', source: 'all' }, initialExpandedNodes([root]));
  assert.deepEqual(view.edges.map((item) => [item.path, item.selectorType, item.requestedVersionId ?? null]), [
    ['/bindings/0', 'logical-key', null], ['/bindings/1', 'exact-release', 'v0'],
  ]);
});

test('root variants are roots and source filters do not merge them', () => {
  const published = node('SKILL', 'root', 'published', 'v2');
  const draft = node('SKILL', 'root', 'saved-draft', undefined, { revision: 7 });
  const target = node('ABILITY', 'lookup');
  const draftTarget = node('ABILITY', 'draft-lookup');
  const value = graph(published, [edge(published, target, '/published'), edge(draft, draftTarget, '/draft')], [], { rootVariants: [published, draft] });
  const expanded = initialExpandedNodes(value.rootVariants);
  assert.equal(expanded.size, 2);
  assert.deepEqual(buildLineageView(value, { direction: 'upstream', source: 'saved-draft' }, expanded).nodes.map((item) => item.source), ['published', 'saved-draft', 'published']);
});

test('shared diamond edges deduplicate while cycles stop at returned evidence', () => {
  const root = node('WORKFLOW', 'root');
  const left = node('SKILL', 'left');
  const right = node('SKILL', 'right');
  const shared = node('ABILITY', 'shared');
  const edges = [
    edge(root, left, '/nodes/0'), edge(root, right, '/nodes/1'),
    edge(left, shared, '/ability'), edge(right, shared, '/ability'),
    edge(right, shared, '/ability'), edge(shared, root, '/cycle', { cycle: true }),
  ];
  const expanded = new Set([root, left, right, shared].map(dependencyNodeIdentity));
  const view = buildLineageView(graph(root, edges, [], { cycle: true, incomplete: true }), { direction: 'upstream', source: 'all' }, expanded);
  assert.equal(view.nodes.length, 4);
  assert.equal(view.edges.length, 5);
  assert.equal(view.edges.filter((item) => item.cycle).length, 1);
  assert.ok(view.nodes.every((item) => Number.isFinite(item.x) && Number.isFinite(item.y)));
});

test('bounded expansion shows only adjacent evidence until a visible node expands', () => {
  const root = node('SKILL', 'root');
  const middle = node('ABILITY', 'middle');
  const leaf = node('APPLICATION', 'leaf');
  const value = graph(root, [edge(root, middle, '/middle'), edge(middle, leaf, '/leaf')]);
  const initial = initialExpandedNodes([root]);
  assert.deepEqual(buildLineageView(value, { direction: 'upstream', source: 'all' }, initial).nodes.map((item) => item.key), ['root', 'middle']);
  initial.add(dependencyNodeIdentity(middle));
  assert.deepEqual(buildLineageView(value, { direction: 'upstream', source: 'all' }, initial).nodes.map((item) => item.key), ['root', 'middle', 'leaf']);
});

test('missing nodes and API boundaries remain explicit and empty evidence stays empty', () => {
  const root = node('SKILL', 'root');
  const missing = node('ABILITY', 'gone', 'published', undefined, { status: 'missing' });
  const value = graph(root, [edge(root, missing, '/missing', { error: 'MISSING_DEPENDENCY' })], [], {
    missing: [{ kind: 'ABILITY', key: 'gone' }], truncated: true, incomplete: true,
  });
  const view = buildLineageView(value, { direction: 'both', source: 'all' }, initialExpandedNodes([root]));
  assert.equal(view.nodes.find((item) => item.key === 'gone').status, 'missing');
  assert.equal(view.edges[0].error, 'MISSING_DEPENDENCY');
  assert.deepEqual(buildLineageView(graph(root), { direction: 'both', source: 'all' }, initialExpandedNodes([root])).edges, []);
});

test('detail navigation is limited to resolved asset nodes', () => {
  assert.equal(isNavigableDependencyNode(node('ABILITY', 'ready')), true);
  assert.equal(isNavigableDependencyNode(node('ABILITY', 'gone', 'published', undefined, { status: 'missing' })), false);
  assert.equal(isNavigableDependencyNode(node('COMPONENT', 'surface')), false);
});
