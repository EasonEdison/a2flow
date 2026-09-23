import {
  capabilityClientModeOf,
  capabilityClientsForMode,
  resolveCapabilityClientVariantView,
} from './capabilityClientVariantLayout';

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

test('dual-client capability shows one global switch and keeps the selected client', () => {
  const view = resolveCapabilityClientVariantView('PC_APP_DIFFERENT', 'APP');

  assertDeepEqual(view.supportedClients, ['PC', 'APP'], 'supported clients');
  assertEqual(view.activeClient, 'APP', 'active client');
  assertEqual(view.showClientSwitch, true, 'switch visibility');
  assertEqual(view.singleClientLabel, '', 'single-client label');
});

test('single-client capability hides the switch and identifies the only supported client', () => {
  const pcView = resolveCapabilityClientVariantView('PC_ONLY', 'APP');
  const appView = resolveCapabilityClientVariantView('APP_ONLY', 'PC');

  assertEqual(pcView.activeClient, 'PC', 'PC active client');
  assertEqual(pcView.showClientSwitch, false, 'PC switch visibility');
  assertEqual(pcView.singleClientLabel, '仅 PC', 'PC identity label');
  assertEqual(appView.activeClient, 'APP', 'APP active client');
  assertEqual(appView.showClientSwitch, false, 'APP switch visibility');
  assertEqual(appView.singleClientLabel, '仅 APP', 'APP identity label');
});

test('four dropdown modes map to four exact canonical client shapes', () => {
  assertDeepEqual(capabilityClientsForMode('PC_ONLY'), ['PC'], 'PC only');
  assertDeepEqual(capabilityClientsForMode('APP_ONLY'), ['APP'], 'APP only');
  assertDeepEqual(capabilityClientsForMode('PC_APP_DIFFERENT'), ['PC', 'APP'], 'different');
  assertDeepEqual(capabilityClientsForMode('PC_APP_COMMON'), ['COMMON'], 'common');
});

test('common mode hides the switch and uses its independently authored variant', () => {
  const view = resolveCapabilityClientVariantView('PC_APP_COMMON', 'PC');

  assertEqual(view.activeClient, 'COMMON', 'COMMON active variant');
  assertEqual(view.showClientSwitch, false, 'COMMON switch visibility');
  assertEqual(view.singleClientLabel, 'PC 与 APP 通用', 'COMMON identity label');
});

test('only exact canonical arrays resolve to a dropdown mode', () => {
  assertEqual(capabilityClientModeOf(['PC']), 'PC_ONLY', 'PC shape');
  assertEqual(capabilityClientModeOf(['APP']), 'APP_ONLY', 'APP shape');
  assertEqual(capabilityClientModeOf(['PC', 'APP']), 'PC_APP_DIFFERENT', 'different shape');
  assertEqual(capabilityClientModeOf(['COMMON']), 'PC_APP_COMMON', 'common shape');
  assertEqual(capabilityClientModeOf(['APP', 'PC']), undefined, 'reordered shape rejected');
  assertEqual(capabilityClientModeOf(['COMMON', 'PC']), undefined, 'mixed common rejected');
  assertEqual(capabilityClientModeOf([]), undefined, 'empty shape rejected');
});
