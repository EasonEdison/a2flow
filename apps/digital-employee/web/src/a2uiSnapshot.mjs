import { A2uiMessageListSchema, MessageProcessor, extractRefFields } from '@a2ui/web_core/v0_9';

export const RPC_PROFILE = 'a2flow.java-rpc.v1';
const record = value => value !== null && typeof value === 'object' && !Array.isArray(value);

/** A complete persisted snapshot is replayed into a fresh official processor, never patched onto another card. */
export function createSnapshotProcessor(display, catalogs) {
  if (display.protocolProfile !== RPC_PROFILE) throw new Error('不支持的 A2UI 协议配置');
  const meta = display.catalog;
  if (!meta || !['v0.9.1', '0.9.1'].includes(meta.protocolVersion) ||
      !meta.catalogId || meta.catalogRevision === undefined || !meta.catalogDigest) {
    throw new Error('缺少完整 v0.9.1 Catalog 身份');
  }
  const catalog = catalogs.find(item => item.id === meta.catalogId);
  if (!catalog) throw new Error('未注册此 Catalog 的前端实现：' + meta.catalogId);
  const messages = A2uiMessageListSchema.parse(structuredClone(display.snapshotMessages));
  if (!messages.length || messages.length > 1000) throw new Error('快照消息数量不合法');
  const processor = new MessageProcessor([catalog], undefined, { version: 'v0.9.1' });
  try {
    for (const message of messages) {
      if (message.version !== 'v0.9.1') throw new Error('快照必须使用 v0.9.1');
      if (message.createSurface && message.createSurface.catalogId !== meta.catalogId) throw new Error('快照 Catalog 与发布身份不一致');
      for (const component of message.updateComponents?.components || []) {
        if (component.component && !catalog.components.has(component.component)) {
          throw new Error('未实现的 Catalog 组件：' + component.component);
        }
      }
      processor.processMessages([message]);
    }
    if (!processor.model.surfacesMap.size) throw new Error('快照没有可展示的 Surface');
    for (const surface of processor.model.surfacesMap.values()) {
      const nodes = new Map(surface.componentsModel.entries);
      if (!nodes.has('root')) throw new Error('Surface 缺少 root 组件：' + surface.id);
      if (nodes.size > 1000) throw new Error('Surface 组件数量超限');
      // The official renderer resolves arbitrary nesting and list templates. Check references first
      // so an incomplete snapshot never looks like a successful, indefinitely loading card.
      const refs = node => {
        const result = [];
        for (const [field, ref] of extractRefFields(catalog.components.get(node.type).schema)) {
          const value = node.properties[field];
          if (ref.kind === 'single') result.push(value);
          else if (ref.kind === 'list') result.push(...(Array.isArray(value) ? value : [value?.componentId]));
          else if (Array.isArray(value)) for (const entry of value) for (const key of ref.keys) result.push(entry[key]);
        }
        return result.filter(value => typeof value === 'string');
      };
      const visiting = new Set(), visited = new Set();
      const visit = (id, depth = 0) => {
        if (depth > 64 || visiting.has(id)) throw new Error('组件布局循环或深度超限：' + id);
        if (visited.has(id)) return;
        const node = nodes.get(id);
        if (!node) throw new Error('组件引用不存在：' + id);
        visiting.add(id);
        refs(node).forEach(child => visit(child, depth + 1));
        visiting.delete(id); visited.add(id);
      };
      visit('root');
    }
    if (!Array.isArray(display.actions)) throw new Error('缺少 Action 声明');
    for (const action of display.actions) {
      const node = processor.model.getSurface(action.surfaceId)?.componentsModel.get(action.componentId);
      if (!node || node.properties.action?.event?.name !== action.actionName) throw new Error('Action 声明与组件不一致');
      if (!record(action.inputSchema)) throw new Error('Action 缺少输入契约');
    }
    return processor;
  } catch (error) { processor.model.dispose(); throw error; }
}

export function cardIsOperable(card) {
  return ['WAITING_ACTION', 'DISPLAY_ONLY'].includes(card.status) && Array.isArray(card.display.actions) && card.display.actions.length > 0;
}

/** The official binder has resolved event.context against this surface's current DataModel. */
export function actionRequest(card, event) {
  if (!cardIsOperable(card)) throw new Error('卡片当前不可操作');
  const declared = card.display.actions.find(action => action.actionName === event.name &&
    action.surfaceId === event.surfaceId && action.componentId === event.sourceComponentId);
  if (!declared || !record(event.context)) throw new Error('Action 未声明或上下文无效');
  return { actionName: declared.actionName, inputs: {
    surfaceId: event.surfaceId, sourceComponentId: event.sourceComponentId,
    context: structuredClone(event.context),
  } };
}
