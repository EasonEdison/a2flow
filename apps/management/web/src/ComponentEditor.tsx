import { isEditableRecord, updatePath } from './form-editor-state';
import { Field, MalformedValue, Section, type FormProps } from './EditorControls';
import type { ComponentDraftDocument } from './asset-drafts';

export const COMPONENT_IMPLEMENTATIONS = [
  { name: 'Column', description: '纵向布局容器', props: 'id (string, 只读身份) · children (component id[])' },
  { name: 'Text', description: '读取数据绑定并显示文本', props: 'id (string, 只读身份) · text.path (JSON Pointer)' },
  { name: 'ChoicePicker', description: '单选选择器', props: 'id · options.path · value.path · variant=mutuallyExclusive' },
  { name: 'Button', description: '产生有界事件的按钮', props: 'id · label · action.event.name · action.event.context' },
] as const;

export function ComponentEditor({ document, disabled, onChange }: FormProps<ComponentDraftDocument>) {
  const definition = document.definition;
  if (!isEditableRecord(definition)) return <MalformedValue label="definition" value={definition} />;
  const members = definition.components;
  const editableMembers = Array.isArray(members) && members.every((name) => typeof name === 'string');
  const registered = editableMembers ? new Set(members as string[]) : new Set<string>();
  const supportedNames = new Set<string>(COMPONENT_IMPLEMENTATIONS.map((implementation) => implementation.name));
  const unsupportedMembers = editableMembers ? (members as string[]).filter((name) => !supportedNames.has(name)) : [];

  function setRegistered(name: string, checked: boolean) {
    if (!editableMembers) return;
    const next = checked
      ? [...(members as string[]).filter((member) => member !== name), name]
      : (members as string[]).filter((member) => member !== name);
    onChange(updatePath(document, ['definition', 'components'], next));
  }

  return <div className="asset-form component-catalog-editor">
    <Section title="目录身份">
      <Field label="Catalog key" value={definition.catalogKey} disabled={disabled} readOnly />
      <Field label="Protocol profile" value={definition.protocolProfileRef} disabled={disabled}
        onChange={(value) => onChange(updatePath(document, ['definition', 'protocolProfileRef'], value))} />
    </Section>
    <Section title="已注册组件">
      <div className="notice warning"><strong>这是配置目录，不是代码上传器</strong><span>只能勾选下方宿主已实现的四种组件。自定义 JavaScript、HTML 或远程组件无法在此注册。</span></div>
      {unsupportedMembers.length ? <div className="notice error"><strong>草稿含有未实现的组件名</strong><span>{unsupportedMembers.join(', ')}；表单不会静默删除，请取消对应成员后保存，后端验证会拒绝发布。</span></div> : null}
      {!editableMembers ? <MalformedValue label="definition.components" value={members} /> : <div className="component-implementation-list">
        {COMPONENT_IMPLEMENTATIONS.map((implementation) => <label className="component-implementation" key={implementation.name}>
          <input type="checkbox" checked={registered.has(implementation.name)} disabled={disabled}
            onChange={(event) => setRegistered(implementation.name, event.target.checked)} />
          <span><strong>{implementation.name}</strong><small>{implementation.description}</small><code>{implementation.props}</code></span>
        </label>)}
      </div>}
      <p className="field-feedback">勾选项会直接写入 <code>definition.components</code>；保存、验证、发布、历史与回滚均使用通用资产流程。</p>
    </Section>
    {Array.isArray(document.dependencies) ? <Section title="依赖（只读）"><pre className="resource-summary">{JSON.stringify(document.dependencies, null, 2)}</pre></Section> : <MalformedValue label="dependencies" value={document.dependencies} />}
  </div>;
}
