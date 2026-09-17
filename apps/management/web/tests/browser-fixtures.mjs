export const digest = `sha256:${'1'.repeat(64)}`;

export const drafts = {
  SKILL: {
    metadata: { name: 'plan', description: 'Plan safely', extra: { retained: true } },
    skillMd: '---\nname: plan\ndescription: Plan safely\n---\n\n# Plan',
    requiredToolNames: ['execute_ability', { extension: 1 }, 42, null],
    abilityBindings: ['demo.lookup'],
    applicationBindings: ['demo.confirm'],
    resources: [{ logicalPath: 'guide.md', contentBase64: 'c2VjcmV0LWJ5dGVz', digest: 'sha256:resource' }],
    extension: { nested: { retained: true } },
  },
  ABILITY: {
    abilityKey: 'demo.lookup', adapterOperationRef: 'demo.lookup.read',
    credentialRequirements: [{ slotId: 'read', required: true, extension: 'keep' }],
    defaultSuccessPolicyRef: 'ok',
    inputBindings: [{ targetPath: '/query', source: 'MODEL_ARGUMENT', sourcePath: '/query', extension: 1 }],
    modelArgumentSchema: { type: 'object', extension: { keep: true } },
    outputSchema: { type: 'object' }, resolvedInputSchema: { type: 'object' },
    resultInterpretationPolicies: [{ policyRef: 'ok', operator: 'JSON_POINTER_EQUALS' }],
    extension: { keep: true },
  },
  APPLICATION: {
    definition: {
      asset: { kind: 'APPLICATION', applicationKey: 'demo.app', protocolProfileRef: 'a2ui/v1', componentCatalogRef: 'catalog/v1', extra: 'keep' },
      renderPolicy: { tool: 'render_application', interactionMode: 'INTERACTIVE', requiresPause: true },
      interactionPolicy: { fixed: true }, versionAdmissionPolicy: { fixed: true }, retryPolicy: { fixed: true }, finalizerPolicy: { fixed: true },
      actionPolicies: [{ actionName: 'confirm', sourceComponentId: 'button', abilityReleaseRef: 'demo.confirm@v1', successPolicyRef: 'ok', completeInteractionOnSuccess: true, controlRequestDedupeOnly: true, businessIdempotencyOwner: 'CALLED_API_BACKEND', extension: 1 }],
      surfaceTemplate: { inputSchema: { type: 'object' }, components: [], extension: { keep: true } },
      extension: { keep: true },
    },
    dependencies: [{ kind: 'ABILITY', key: 'demo.confirm', extension: true }],
    extension: { keep: true },
  },
  WORKFLOW: {
    definitionKey: 'demo.workflow', topology: 'SEQUENTIAL',
    nodes: [{ nodeId: 'one', skillKey: 'demo/one', extension: { keep: true } }, { nodeId: 'two', skillKey: 'demo/two' }],
    extension: { nested: true },
  },
};
