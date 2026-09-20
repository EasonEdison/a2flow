import { useState } from 'react';
import { isEditableRecord, skillFrontmatterMismatch, updatePath } from './form-editor-state';
import { Field, MalformedValue, Section, type FormProps } from './EditorControls';
import { SkillBindingWorkbench } from './SkillBindingWorkbench';
import { StringRows } from './StringRows';

export function SkillEditor(props: FormProps) {
  const { document, disabled, onChange, references, onNavigateReference } = props;
  const [localStage, setStage] = useState('overview');
  const stage = props.skillStage ?? localStage;
  const stages = [
    ['overview', '基础信息'], ['abilities', '业务能力'],
    ['applications', '渲染组件'], ['resources', '文件处理'],
  ];
  const mismatch = skillFrontmatterMismatch(document);
  const metadata = isEditableRecord(document.metadata) ? document.metadata : undefined;
  return <div className="asset-form">
    {!props.skillStage ? <nav className="skill-stage-tabs" aria-label="Skill 配置阶段">
      {stages.map(([key, label]) => <button type="button" key={key} aria-pressed={stage === key}
        className={stage === key ? 'active' : ''} onClick={() => setStage(key)}>{label}
        {key === 'abilities' && Array.isArray(document.abilityBindings) ? <span>{document.abilityBindings.length}</span> : null}
        {key === 'applications' && Array.isArray(document.applicationBindings) ? <span>{document.applicationBindings.length}</span> : null}
      </button>)}
    </nav> : null}
    <div hidden={stage !== 'overview'}>
    {mismatch ? <div className="notice warning"><strong>metadata 与 frontmatter 需要核对</strong><span>{mismatch}</span></div> : null}
    <Section title="Skill 基础信息">
      {metadata || document.metadata === undefined ? <>
        <Field label="名称" value={metadata?.name} disabled={disabled} onChange={(value) => onChange(updatePath(document, ['metadata', 'name'], value))} />
        <Field label="描述" value={metadata?.description} disabled={disabled} multiline onChange={(value) => onChange(updatePath(document, ['metadata', 'description'], value))} />
      </> : <MalformedValue label="metadata" value={document.metadata} />}
    </Section>
    <StringRows label="所需工具" document={document} path={['requiredToolNames']} disabled={disabled} onChange={onChange} />
    <p className="skill-stage-hint">业务能力和展示应用在对应页签绑定；发布与版本历史仍使用资产详情的统一入口。</p>
    </div>
    <div hidden={stage !== 'abilities'}><SkillBindingWorkbench kind="ABILITY" document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigateReference} /></div>
    <div hidden={stage !== 'applications'}><SkillBindingWorkbench kind="APPLICATION" document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigateReference} /></div>
  </div>;
}
