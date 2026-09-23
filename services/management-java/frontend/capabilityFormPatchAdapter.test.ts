import { createEmptyCapabilityDraft } from './capabilityDraftLifecycle';
import { createCapabilityFormPatchAdapter } from './capabilityFormPatchAdapter';
import {
  buildCapabilityClientCanonicalDraft,
  splitCapabilityClientCanonicalDraft,
} from './capabilityClientTechnicalDraft';
import {
  applyFormPatchReview,
  buildFormPatchReview,
  captureFormPatchBaseline,
} from './shared/authoringFormPatch';

function assertEqual(actual: unknown, expected: unknown, description: string) {
  if (actual !== expected) {
    throw new Error(`${description}: expected ${String(expected)}, received ${String(actual)}`);
  }
}

function test(description: string, callback: () => void) {
  callback();
  console.log(`PASS ${description}`);
}

const adapter = createCapabilityFormPatchAdapter({
  draft: createEmptyCapabilityDraft(),
  draftId: 'cap_draft_test',
  revision: 8,
  normalize: (value) => value,
  apply: () => undefined,
});

test('canonical PC APP and COMMON technical paths are editable', () => {
  [
    '/clientVariants/PC/modelContract/inputFields',
    '/clientVariants/APP/executionBinding/target/serviceName',
    '/clientVariants/COMMON/apiSource/sourceType',
  ].forEach((path) => {
    assertEqual(adapter?.validateOperation({ op: 'replace', path, value: {} })?.length, 0, path);
  });
});

test('legacy root technical and unknown client paths remain rejected', () => {
  [
    '/modelContract/inputFields',
    '/executionBinding/target',
    '/clientVariants/MINI/modelContract/inputFields',
  ].forEach((path) => {
    assertEqual(adapter?.validateOperation({ op: 'replace', path, value: {} })?.length, 1, path);
  });
});

test('shared review applies APP patch without changing the PC contract', () => {
  const pcDraft = createEmptyCapabilityDraft();
  pcDraft.modelContract.description = 'PC 参数契约';
  const appDraft = createEmptyCapabilityDraft();
  appDraft.modelContract.description = 'APP 参数契约';
  const canonicalDraft = buildCapabilityClientCanonicalDraft(
    pcDraft,
    appDraft,
    createEmptyCapabilityDraft(),
    ['PC', 'APP'],
  );
  let appliedDraft = canonicalDraft;
  const reviewAdapter = createCapabilityFormPatchAdapter({
    draft: canonicalDraft,
    draftId: 'cap_draft_test',
    revision: 8,
    normalize: (value) => value,
    apply: (next) => {
      appliedDraft = next;
    },
  });
  const baseline = captureFormPatchBaseline(reviewAdapter);
  const path = '/clientVariants/APP/modelContract/inputFields';
  const review = buildFormPatchReview(reviewAdapter, baseline, canonicalDraft, {
    formKey: reviewAdapter.formKey,
    entityId: reviewAdapter.entityId,
    baseRevision: baseline.revision,
    baseFingerprint: baseline.fingerprint,
    operations: [
      {
        op: 'replace',
        path,
        value: [
          {
            toolField: 'isNewMerchant',
            type: 'boolean',
            businessMeaning: '是否为新商家',
            source: 'MODEL_INPUT',
            required: true,
          },
        ],
      },
    ],
  });
  reviewAdapter.apply(applyFormPatchReview(reviewAdapter, review, new Set([path]), {}));
  const restored = splitCapabilityClientCanonicalDraft(appliedDraft, createEmptyCapabilityDraft());

  assertEqual(restored.canonicalDraft?.modelContract?.description, 'PC 参数契约', 'PC unchanged');
  assertEqual(
    restored.appDraft?.modelContract?.description,
    'APP 参数契约',
    'APP description retained',
  );
  assertEqual(
    restored.appDraft?.modelContract?.inputFields?.[0]?.toolField,
    'isNewMerchant',
    'APP input applied',
  );
});
