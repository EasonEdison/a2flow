import { resolveCapabilityCreateChangeView } from './capabilityCreateChangeModel';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function assertDeepEqual(actual: unknown, expected: unknown, description: string) {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(
      `${description}: expected ${JSON.stringify(expected)}, received ${JSON.stringify(actual)}`,
    );
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

test('sealed capability can create a change from the basic-information side panel', () => {
  const view = resolveCapabilityCreateChangeView({
    canEdit: true,
    readonlyReason: '',
    allowedActions: ['CREATE_CHANGE'],
    versions: [{ version: 3 }, { version: 7 }],
    baseVersion: undefined,
    changeName: '补齐分类关系',
  });

  assertEqual(view.canCreateChange, true, 'create permission');
  assertEqual(view.defaultBaseVersion, 7, 'latest source version');
  assertDeepEqual(
    view.versionOptions,
    [
      { label: '7', value: 7 },
      { label: '3', value: 3 },
    ],
    'source version options',
  );
  assertEqual(view.submitDisabled, false, 'submit enabled');
  assertEqual(view.submitLabel, '新建变更', 'submit label before source selection');
});

test('create-change action remains fail-closed without backend permission or a change name', () => {
  const forbidden = resolveCapabilityCreateChangeView({
    canEdit: true,
    readonlyReason: '',
    allowedActions: [],
    versions: [],
    baseVersion: undefined,
    changeName: '无权限变更',
  });
  const blankName = resolveCapabilityCreateChangeView({
    canEdit: true,
    readonlyReason: '',
    allowedActions: ['CREATE_CHANGE'],
    versions: [],
    baseVersion: undefined,
    changeName: '   ',
  });

  assertEqual(forbidden.canCreateChange, false, 'backend action gate');
  assertEqual(forbidden.submitDisabled, true, 'forbidden submit');
  assertEqual(blankName.submitDisabled, true, 'blank-name submit');
  assertEqual(blankName.submitTitle, '请先填写变更名称', 'blank-name guidance');
});

test('choosing a historical source makes the restore intent explicit', () => {
  const view = resolveCapabilityCreateChangeView({
    canEdit: true,
    readonlyReason: '',
    allowedActions: ['CREATE_CHANGE'],
    versions: [{ version: 5 }],
    baseVersion: 5,
    changeName: '回溯修复',
  });

  assertEqual(view.submitLabel, '恢复并新建变更', 'historical-source label');
});
