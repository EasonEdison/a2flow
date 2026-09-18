export const digest = `sha256:${'1'.repeat(64)}`;

export const drafts = {
  SKILL: {
    metadata: { name: 'plan', description: 'Plan safely', extra: { retained: true } },
    skillMd: '---\nname: plan\ndescription: Plan safely\n---\n\n# Plan\n\n- safe item\n\n```js\nconst preserved = true;\n```\n\n<script>globalThis.pwned = true</script>\n\n![remote](https://example.invalid/track.png)\n\n[blocked](javascript:alert(1))',
    requiredToolNames: ['execute_ability', { extension: 1 }, 42, null],
    abilityBindings: ['demo.lookup', 'missing.ability'],
    applicationBindings: ['demo.confirm'],
    resources: [{ handleId: 'guide-md', logicalPath: 'guide.md', mediaType: 'text/markdown', byteSize: 12, contentDigest: 'sha256:0364152ae8c7da79c1ee2d96e53bebe5dfbff303e7ee51621fe6fef2505da94a', base64: 'c2VjcmV0LWJ5dGVz' }],
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
      surfaceTemplate: {
        surfaceKey: 'demo', rootId: 'root',
        inputSchema: { type: 'object', required: ['prompt', 'options'], properties: { prompt: { type: 'string' }, options: { type: 'array' }, selection: { type: 'string' } } },
        components: [
          { id: 'root', component: 'Column', children: ['prompt', 'selection', 'button'], extension: { keep: true } },
          { id: 'prompt', component: 'Text', text: { path: '/prompt' }, extension: 'keep' },
          { id: 'selection', component: 'ChoicePicker', options: { path: '/options' }, value: { path: '/selection' }, variant: 'mutuallyExclusive' },
          { id: 'button', component: 'Button', label: 'Confirm', action: { event: { name: 'confirm', context: { selection: { path: '/selection' } } } } },
        ],
        extension: { keep: true },
      },
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
