import { useMemo, useState } from 'react';
import { addBinding, bindingKey, bindingRows, filterBindingAssets, removeBinding } from './skill-binding-state';
import type { AssetKind, AssetSummary, JsonObject, ReferenceCatalog } from './contracts';

const CONFIG: Record<'ABILITY' | 'APPLICATION', { title: string; field: 'abilityBindings' | 'applicationBindings' }> = {
  ABILITY: { title: '业务能力', field: 'abilityBindings' },
  APPLICATION: { title: '渲染应用', field: 'applicationBindings' },
};

function AssetEvidence({ asset }: { asset: AssetSummary }) {
  return <>
    <strong>{asset.name ?? bindingKey(asset)}</strong>
    <code>{bindingKey(asset)}</code>
    <span>{asset.description ?? '未提供描述'}</span>
    <div className="binding-version-facts"><small>{asset.draftOnly ? '尚未发布，暂不可绑定' : asset.versionId ? `当前环境 · 版本 ${asset.versionId}` : '当前环境 · 版本未知'}
      {asset.selection ? ` · ${asset.selection}` : ''}</small></div>
  </>;
}

function BindingSection({ kind, values, document, disabled, references, onChange, onNavigate }: {
  kind: 'ABILITY' | 'APPLICATION'; values: unknown; document: JsonObject; disabled: boolean;
  references?: ReferenceCatalog; onChange: (document: JsonObject) => void;
  onNavigate?: (kind: AssetKind, key: string) => void;
}) {
  const [query, setQuery] = useState('');
  const config = CONFIG[kind];
  const list = Array.isArray(values) ? values : null;
  const assets = references?.assets[kind] ?? [];
  const candidates = references?.bindingCandidates?.[kind] ?? assets;
  const filtered = useMemo(() => filterBindingAssets(candidates, query), [candidates, query]);
  const catalogKnown = Boolean(references) && !references?.loading && !references?.errors[kind];
  const rows = list ? bindingRows(list, catalogKnown ? assets : []) : [];
  const boundKeys = new Set(list?.filter((value): value is string => typeof value === 'string') ?? []);

  const catalogState = references?.loading ? '加载中' : references?.errors[kind] ? '未知（目录错误）' : '当前环境不可用';
  const availableCount = catalogKnown ? `${assets.filter((asset) => !asset.draftOnly).length} 个已发布` : '可用数量未知';

  function update(next: unknown[]) {
    onChange({ ...document, [config.field]: next });
  }

  return <section className="binding-section" aria-label={config.title}>
    <header><div><h4>{config.title}绑定</h4><span>{rows.length} 个绑定 · {availableCount}</span></div><small>修改后点击下方“保存草稿”，刷新后仍保留。</small></header>
    <p className="binding-explanation">{kind === 'ABILITY' ? '选择 Skill 可以调用的业务能力。当前支持仅执行；展示内容通过“渲染组件”绑定 Application。' : '选择 Skill 可以渲染的 A2UI Application。基础组件在组件中心管理，不直接绑定到 Skill。'}绑定不会自动改写 Skill 指令。</p>
    <div className="binding-columns">
      <div className="binding-catalog">
        <h5>{config.title}列表</h5>
        <label><span>搜索 {config.title}</span><input type="search" aria-label={`搜索 ${config.title}`} value={query}
          onChange={(event) => setQuery(event.target.value)} placeholder="按名称、Key 或描述搜索" /></label>
        {references?.loading ? <p className="binding-state">正在加载当前环境目录…</p> : null}
        {references?.errors[kind] ? <div className="binding-state error">目录加载失败：{references.errors[kind]} <button type="button" className="quiet-button" disabled={disabled} onClick={references.retry}>重试</button></div> : null}
        {!references?.loading && !references?.errors[kind] && candidates.length === 0 ? <p className="binding-state">当前环境目录为空。</p> : null}
        {!references?.loading && !references?.errors[kind] && candidates.length > 0 && filtered.length === 0 ? <p className="binding-state">没有匹配项。</p> : null}
        <div className="binding-list">{filtered.map((asset) => {
          const key = bindingKey(asset)!;
          const bound = boundKeys.has(key);
          return <article className={`binding-card${bound ? ' selected-binding' : ''}`} key={key}>
            <span className="binding-badge">{!catalogKnown ? '状态待核对' : asset.draftOnly ? '未发布' : bound ? '已绑定' : '可绑定'}</span>
            <AssetEvidence asset={asset} /><div>
            {onNavigate ? <button type="button" className="quiet-button" disabled={disabled} onClick={() => onNavigate(kind, key)}>查看详情</button> : null}
            <button type="button" className="secondary-button" aria-label={`绑定 ${key}`} disabled={disabled || bound || !catalogKnown || asset.draftOnly || !list}
              onClick={() => { if (catalogKnown && !asset.draftOnly && list) update(addBinding(list, key)); }}>{bound ? '已绑定' : '绑定到 Skill'}</button>
          </div></article>;
        })}</div>
      </div>
      <div className="binding-current">
        <h5>当前 Skill 已绑定{config.title} <span className="binding-badge">{rows.length} 个</span></h5>
        {!list ? <div className="binding-state error">{config.field} 类型异常，原值已保留；请在完整 JSON 模式修复。</div> : null}
        {list && rows.length === 0 ? <p className="binding-state">尚未绑定。</p> : null}
        {rows.map((row) => <article className={`binding-card bound ${row.status}`} key={row.identity}>
          {row.asset ? <AssetEvidence asset={row.asset} /> : <>
            <strong>{row.key ?? '异常绑定'}</strong><code>{row.key ?? JSON.stringify(row.value)}</code>
            <span>{row.status === 'malformed' ? '绑定值类型异常，原值已保留' : row.status === 'duplicate' ? '重复绑定，原值已保留' : catalogState}</span>
            <small>未提供元数据或版本证据</small>
          </>}
          <div>{row.key && row.asset && onNavigate ? <button type="button" className="quiet-button" disabled={disabled} onClick={() => onNavigate(kind, row.key!)}>查看详情</button> : null}
            <button type="button" className="warning-button" aria-label={`解除绑定 ${row.key ?? row.identity}`} disabled={disabled}
              onClick={() => { if (window.confirm(`确认解除绑定 ${row.key ?? '异常项'} 并保存到数据库草稿？已发布版本不受影响。`)) update(removeBinding(list!, row.identity)); }}>解除绑定</button></div>
        </article>)}
      </div>
    </div>
  </section>;
}

export function SkillBindingWorkbench({ kind, document, disabled, references, onChange, onNavigate }: {
  kind?: 'ABILITY' | 'APPLICATION';
  document: JsonObject; disabled: boolean; references?: ReferenceCatalog;
  onChange: (document: JsonObject) => void; onNavigate?: (kind: AssetKind, key: string) => void;
}) {
  return <fieldset className="binding-workbench" aria-label="Skill 绑定工作台"><legend>Skill 绑定工作台</legend>
    {!kind || kind === 'ABILITY' ? <BindingSection kind="ABILITY" values={document.abilityBindings} document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigate} /> : null}
    {!kind || kind === 'APPLICATION' ? <BindingSection kind="APPLICATION" values={document.applicationBindings} document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigate} /> : null}
    <div className="notice"><strong>依赖与发布检查</strong><span>完整版本与反向引用证据位于资产详情的只读检查面板；打开详情不会丢弃当前未保存缓冲区。</span></div>
  </fieldset>;
}
