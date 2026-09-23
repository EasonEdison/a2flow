import test from 'node:test';
import assert from 'node:assert/strict';
import { basicCatalog } from '@a2ui/react/v0_9';
import { actionRequest, cardIsOperable, createSnapshotProcessor } from '../src/a2uiSnapshot.mjs';
import { fixtureCard } from './a2ui-fixture.mjs';

test('complete v0.9.1 snapshot restores nested components and per-surface DataModel', () => {
  const card = fixtureCard();
  const p = createSnapshotProcessor(card.display, [basicCatalog]);
  const surface = p.model.getSurface('main');
  assert.equal(surface.componentsModel.get('row').type, 'Row');
  assert.equal(surface.dataModel.get('/form/name'), '初始姓名');
  surface.dataModel.set('/form/name', '编辑后');
  assert.equal(createSnapshotProcessor(card.display, [basicCatalog]).model.getSurface('main').dataModel.get('/form/name'), '初始姓名');
  p.model.dispose();
});
test('unknown catalogs/components, wrong version, missing/cyclic layout fail explicitly', () => {
  for (const mutate of [
    c => { c.display.catalog.catalogId = 'unregistered'; },
    c => { c.display.snapshotMessages[1].updateComponents.components[2].component = 'PrivateWidget'; },
    c => { c.display.snapshotMessages[0].version = 'v0.9'; },
    c => { c.display.snapshotMessages[1].updateComponents.components[0].children = ['missing']; },
    c => { c.display.snapshotMessages[1].updateComponents.components[0].children = ['root']; },
    c => { c.display.actions[0].componentId = 'name'; },
  ]) {
    const c = fixtureCard(); mutate(c);
    assert.throws(() => createSnapshotProcessor(c.display, [basicCatalog]));
  }
});
test('DISPLAY_ONLY declared actions are operable, completed/unknown/executing are read-only', () => {
  for (const status of ['DISPLAY_ONLY', 'WAITING_ACTION']) assert.equal(cardIsOperable(fixtureCard(status)), true);
  for (const status of ['COMPLETED', 'UNKNOWN', 'EXECUTING', 'INVALID']) assert.equal(cardIsOperable(fixtureCard(status)), false);
});
test('submission matches all action coordinates and sends context only, never trusted server state', () => {
  const c = fixtureCard();
  const event = { name: 'submitForm', surfaceId: 'main', sourceComponentId: 'submit',
    context: { nested: { value: 42 }, referenceId: '9223372036854775807' }, sessionId: 'must-not-send', appBuild: 'must-not-send', userId: 'must-not-send' };
  assert.deepEqual(actionRequest(c, event), { actionName: 'submitForm', inputs: {
    surfaceId: 'main', sourceComponentId: 'submit', context: event.context,
  } });
  for (const patch of [{ name: 'other' }, { surfaceId: 'other' }, { sourceComponentId: 'other' }]) assert.throws(() => actionRequest(c, { ...event, ...patch }));
  assert.throws(() => actionRequest(fixtureCard('COMPLETED'), event));
});
