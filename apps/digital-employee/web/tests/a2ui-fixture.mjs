export const catalogId = 'https://a2ui.org/specification/v0_9/catalogs/basic/catalog.json';
export function fixtureCard(status = 'DISPLAY_ONLY') {
  return {
    cardId: 'rpc-card', conversationId: 'c1', status,
    display: {
      applicationKey: 'rpc-form', applicationVersion: 1, protocolProfile: 'a2flow.java-rpc.v1',
      catalog: { protocolVersion: 'v0.9.1', catalogId, catalogRevision: '1', catalogDigest: 'fixture-only' },
      actions: [{ actionName: 'submitForm', surfaceId: 'main', componentId: 'submit', inputSchema: { type: 'object' } }],
      snapshotMessages: [
        { version: 'v0.9.1', createSurface: { surfaceId: 'main', catalogId } },
        { version: 'v0.9.1', updateComponents: { surfaceId: 'main', components: [
          { id: 'root', component: 'Column', children: ['title', 'row', 'choices', 'consent', 'items', 'submit'] },
          { id: 'title', component: 'Text', text: '**RPC 配置表单**', variant: 'h2' },
          { id: 'row', component: 'Row', children: ['name', 'details'], align: 'start' },
          { id: 'name', component: 'TextField', label: '姓名', value: { path: '/form/name' }, variant: 'shortText' },
          { id: 'details', component: 'Card', child: 'detailText' },
          { id: 'detailText', component: 'Text', text: { path: '/description' } },
          { id: 'choices', component: 'ChoicePicker', label: '选择方案', variant: 'mutuallyExclusive',
            options: [{ label: '方案甲', value: 'a' }, { label: '方案乙', value: 'b' }], value: { path: '/form/choices' } },
          { id: 'consent', component: 'CheckBox', label: '确认资料', value: { path: '/form/consent' } },
          { id: 'items', component: 'List', children: { componentId: 'item', path: '/items' } },
          { id: 'item', component: 'Text', text: { path: 'label' } },
          { id: 'submit', component: 'Button', child: 'submitText', variant: 'primary', action: { event: {
            name: 'submitForm', context: { name: { path: '/form/name' }, choices: { path: '/form/choices' },
              consent: { path: '/form/consent' }, referenceId: { path: '/referenceId' }, fixed: 'keep' },
          } } },
          { id: 'submitText', component: 'Text', text: '提交表单' },
        ] } },
        { version: 'v0.9.1', updateDataModel: { surfaceId: 'main', path: '/', value: {
          form: { name: '初始姓名', choices: ['a'], consent: false }, description: '嵌套卡片内容',
          items: [{ label: '列表第一项' }, { label: '列表第二项' }], referenceId: '9223372036854775807',
        } } },
      ],
    },
  };
}
