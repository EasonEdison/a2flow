import { isEditableRecord, skillFrontmatterMismatch, updatePath } from './form-editor-state';
import { Field, MalformedValue, Section, type FormProps } from './EditorControls';
import { StringRows } from './StringRows';

function resourceSummary(resources: unknown): unknown {
  if (!Array.isArray(resources)) return resources;
  return resources.map((resource) => {
    if (!isEditableRecord(resource)) return resource;
    const summary: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(resource)) {
      summary[key] = /content|base64/i.test(key) && typeof value === 'string'
        ? `[已保留 ${value.length} 字符，表单不显示内容]`
        : value;
    }
    return summary;
  });
}

export function SkillEditor({ document, disabled, onChange }: FormProps) {
  const mismatch = skillFrontmatterMismatch(document);
  const metadata = isEditableRecord(document.metadata) ? document.metadata : undefined;
  return <div className="asset-form">
    {mismatch ? <div className="notice warning"><strong>metadata 与 frontmatter 需要核对</strong><span>{mismatch}</span></div> : null}
    <Section title="Metadata">
      {metadata || document.metadata === undefined ? <>
        <Field label="名称" value={metadata?.name} disabled={disabled} onChange={(value) => onChange(updatePath(document, ['metadata', 'name'], value))} />
        <Field label="描述" value={metadata?.description} disabled={disabled} multiline onChange={(value) => onChange(updatePath(document, ['metadata', 'description'], value))} />
      </> : <MalformedValue label="metadata" value={document.metadata} />}
    </Section>
    <Section title="Markdown 指令"><Field label="SKILL.md（不会自动改写 frontmatter）" value={document.skillMd} disabled={disabled} multiline onChange={(value) => onChange(updatePath(document, ['skillMd'], value))} /></Section>
    <StringRows label="所需工具" document={document} path={['requiredToolNames']} disabled={disabled} onChange={onChange} />
    <StringRows label="Ability 绑定" document={document} path={['abilityBindings']} disabled={disabled} onChange={onChange} />
    <StringRows label="Application 绑定" document={document} path={['applicationBindings']} disabled={disabled} onChange={onChange} />
    <Section title="资源（只读）"><pre className="resource-summary">{JSON.stringify(resourceSummary(document.resources), null, 2)}</pre><small>资源内容、摘要和 base64 不能在表单模式修改。</small></Section>
  </div>;
}
