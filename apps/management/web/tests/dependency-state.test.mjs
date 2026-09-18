import assert from 'node:assert/strict';
import test from 'node:test';

import { beginDependencyLoad, settleDependencyLoad, staleDependencyState } from '../src/dependency-state.js';

const identity = 'admin:PRT:SKILL:team/root';
const graph = {
  root: { kind: 'SKILL', key: 'team/root', source: 'published', status: 'resolved' },
  upstream: [], dependents: [], cycle: false, truncated: false, incomplete: false,
};

test('outdated dependency responses cannot replace a newer request', () => {
  const first = beginDependencyLoad(null, identity);
  const second = beginDependencyLoad(first, identity);
  const ignored = settleDependencyLoad(second, identity, first.requestId, graph, null);
  assert.equal(ignored.loading, true);
  assert.equal(ignored.graph, null);
  const settled = settleDependencyLoad(ignored, identity, second.requestId, graph, null);
  assert.equal(settled.loading, false);
  assert.equal(settled.graph, graph);
});

test('local edits retain evidence and mark dependency checks stale', () => {
  const loading = beginDependencyLoad(null, identity);
  const settled = settleDependencyLoad(loading, identity, loading.requestId, graph, null);
  const stale = staleDependencyState(settled, 'UNSAVED_LOCAL_EDITS_EXCLUDED');
  assert.equal(stale.graph, graph);
  assert.equal(stale.stale, true);
  assert.equal(stale.staleReason, 'UNSAVED_LOCAL_EDITS_EXCLUDED');
});

test('edit during pending read invalidates success and error without permanent loading', () => {
  const loading = beginDependencyLoad(null, identity);
  const stale = staleDependencyState(loading, 'UNSAVED_LOCAL_EDITS_EXCLUDED');
  assert.equal(stale.loading, false);
  assert.equal(stale.stale, true);
  assert.equal(settleDependencyLoad(stale, identity, loading.requestId, graph, null), stale);
  assert.equal(settleDependencyLoad(stale, identity, loading.requestId, null, 'OLD_ERROR'), stale);
});

test('save during pending read preserves old evidence as stale', () => {
  const initial = beginDependencyLoad(null, identity);
  const settled = settleDependencyLoad(initial, identity, initial.requestId, graph, null);
  const loading = beginDependencyLoad(settled, identity);
  const stale = staleDependencyState(loading, 'SAVED_DRAFT_CHANGED');
  const ignored = settleDependencyLoad(stale, identity, loading.requestId, { ...graph }, null);
  assert.equal(ignored.graph, graph);
  assert.equal(ignored.loading, false);
  assert.equal(ignored.staleReason, 'SAVED_DRAFT_CHANGED');
});

test('asset identity change cannot restore old selection evidence', () => {
  const oldIdentity = identity;
  const nextIdentity = 'admin:PRT:ABILITY:demo.lookup';
  const oldLoad = beginDependencyLoad(null, oldIdentity);
  const nextLoad = beginDependencyLoad(oldLoad, nextIdentity);
  assert.equal(nextLoad.graph, null);
  const ignored = settleDependencyLoad(nextLoad, oldIdentity, oldLoad.requestId, graph, null);
  assert.equal(ignored, nextLoad);
  assert.equal(settleDependencyLoad(null, oldIdentity, oldLoad.requestId, graph, null), null);
});

test('explicit refresh records persisted evidence but remains stale for excluded edits', () => {
  const initial = beginDependencyLoad(null, identity);
  const stale = staleDependencyState(
    settleDependencyLoad(initial, identity, initial.requestId, graph, null),
    'UNSAVED_LOCAL_EDITS_EXCLUDED',
  );
  const refresh = beginDependencyLoad(stale, identity);
  const refreshed = settleDependencyLoad(
    refresh, identity, refresh.requestId, { ...graph }, null, 'UNSAVED_LOCAL_EDITS_EXCLUDED');
  assert.equal(refreshed.loading, false);
  assert.equal(refreshed.stale, true);
  assert.equal(refreshed.staleReason, 'UNSAVED_LOCAL_EDITS_EXCLUDED');
});

test('loading error and empty graph remain distinct states', () => {
  const loading = beginDependencyLoad(null, identity);
  assert.equal(loading.loading, true);
  const failed = settleDependencyLoad(loading, identity, loading.requestId, null, 'NETWORK_ERROR');
  assert.equal(failed.loading, false);
  assert.equal(failed.error, 'NETWORK_ERROR');
  assert.equal(failed.graph, null);
});
