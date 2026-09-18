import { useMemo, useState } from 'react';
import { addBinding, bindingKey, bindingRows, filterBindingAssets, removeBinding } from './skill-binding-state';
import type { AssetKind, AssetSummary, JsonObject, ReferenceCatalog } from './contracts';

const CONFIG: Record<'ABILITY' | 'APPLICATION', { title: string; field: 'abilityBindings' | 'applicationBindings' }> = {
  ABILITY: { title: 'Business abilities', field: 'abilityBindings' },
  APPLICATION: { title: 'A2UI Applications', field: 'applicationBindings' },
};

function AssetEvidence({ asset }: { asset: AssetSummary }) {
  return <>
    <strong>{asset.name ?? bindingKey(asset)}</strong>
    <code>{bindingKey(asset)}</code>
    <span>{asset.description ?? '未提供描述'}</span>
    {asset.versionId || asset.selection ? <small>{asset.versionId ? `当前环境版本 ${asset.versionId}` : ''}{asset.versionId && asset.selection ? ' · ' : ''}{asset.selection ? `选择 ${asset.selection}` : ''}</small> : <small>当前 API 未提供版本/选择证据</small>}
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
  const filtered = useMemo(() => filterBindingAssets(assets, query), [assets, query]);
  const catalogKnown = Boolean(references) && !references?.loading && !references?.errors[kind];
  const rows = list ? bindingRows(list, catalogKnown ? assets : []) : [];
  const boundKeys = new Set(list?.filter((value): value is string => typeof value === 'string') ?? []);

  const catalogState = references?.loading ? '加载中' : references?.errors[kind] ? '未知（目录错误）' : '当前环境不可用';
  const availableCount = catalogKnown ? `${assets.length} 个可用` : '可用数量未知';

  function update(next: unknown[]) {
    onChange({ ...document, [config.field]: next });
  }

  return <section className="binding-section" aria-label={config.title}>
    <header><div><h4>{config.title}</h4><span>{rows.length} 个绑定 · {availableCount}</span></div><small>关系修改仅进入本地草稿，保存后才持久化。</small></header>
    <div className="binding-columns">
      <div className="binding-catalog">
        <label><span>搜索 {config.title}</span><input type="search" aria-label={`搜索 ${config.title}`} value={query} disabled={disabled}
          onChange={(event) => setQuery(event.target.value)} placeholder="按名称、Key 或描述搜索" /></label>
        {references?.loading ? <p className="binding-state">正在加载当前环境目录…</p> : null}
        {references?.errors[kind] ? <div className="binding-state error">目录加载失败：{references.errors[kind]} <button type="button" className="quiet-button" disabled={disabled} onClick={references.retry}>重试</button></div> : null}
        {!references?.loading && !references?.errors[kind] && assets.length === 0 ? <p className="binding-state">当前环境目录为空。</p> : null}
        {!references?.loading && !references?.errors[kind] && assets.length > 0 && filtered.length === 0 ? <p className="binding-state">没有匹配项。</p> : null}
        <div className="binding-list">{filtered.map((asset) => {
          const key = bindingKey(asset)!;
          const bound = boundKeys.has(key);
          return <article className="binding-card" key={key}><AssetEvidence asset={asset} /><div>
            {onNavigate ? <button type="button" className="quiet-button" disabled={disabled} onClick={() => onNavigate(kind, key)}>查看详情</button> : null}
            <button type="button" className="secondary-button" aria-label={`绑定 ${key}`} disabled={disabled || bound || !catalogKnown}
              onClick={() => { if (catalogKnown && list) update(addBinding(list, key)); }}>{bound ? '已绑定' : '绑定'}</button>
          </div></article>;
        })}</div>
      </div>
      <div className="binding-current">
        <h5>当前绑定</h5>
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
              onClick={() => { if (window.confirm(`确认解除绑定 ${row.key ?? '异常项'}？此操作只修改本地草稿。`)) update(removeBinding(list!, row.identity)); }}>解除绑定</button></div>
        </article>)}
      </div>
    </div>
  </section>;
}

export function SkillBindingWorkbench({ document, disabled, references, onChange, onNavigate }: {
  document: JsonObject; disabled: boolean; references?: ReferenceCatalog;
  onChange: (document: JsonObject) => void; onNavigate?: (kind: AssetKind, key: string) => void;
}) {
  return <fieldset className="binding-workbench" aria-label="Skill 绑定工作台"><legend>Skill 绑定工作台</legend>
    <BindingSection kind="ABILITY" values={document.abilityBindings} document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigate} />
    <BindingSection kind="APPLICATION" values={document.applicationBindings} document={document} disabled={disabled} references={references} onChange={onChange} onNavigate={onNavigate} />
    <div className="notice warning"><strong>版本与就绪信息暂未扩展</strong><span>仅展示当前环境管理 API 已提供的证据；完整依赖、版本与发布就绪面板将在后续包实现。</span></div>
  </fieldset>;
}
