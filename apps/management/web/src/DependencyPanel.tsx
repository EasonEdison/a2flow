import type { AssetKind, DependencyEdge, DependencyGraph, DependencyKind } from './contracts';

function Evidence({ edge, direction, onNavigate }: {
  edge: DependencyEdge;
  direction: 'upstream' | 'dependent';
  onNavigate: (kind: AssetKind, key: string) => void;
}) {
  const node = direction === 'upstream' ? edge.target : edge.from;
  const kind = direction === 'upstream' ? edge.toKind : edge.fromKind;
  const key = direction === 'upstream' ? edge.toKey : edge.fromKey;
  const navigable = kind !== 'COMPONENT';
  return <li className={edge.error ? 'dependency-edge error' : 'dependency-edge'}>
    <div><strong>{kind} · {key}</strong><code>{edge.path}</code></div>
    <span>{edge.selectorType === 'exact-release' ? `精确版本 ${edge.requestedVersionId}` : '逻辑 Key'}</span>
    <span>{node?.source ?? edge.source} · {node?.versionId ? `版本 ${node.versionId}` : node?.revision ? `草稿修订 #${node.revision}` : '无版本证据'}</span>
    {edge.error ? <span className="error">{edge.error}</span> : null}
    {edge.cycle ? <span className="error">检测到循环</span> : null}
    {navigable ? <button className="quiet-button" type="button" onClick={() => onNavigate(kind, key)}>查看详情</button> : null}
  </li>;
}

function EdgeList({ title, edges, direction, onNavigate }: {
  title: string;
  edges: DependencyEdge[];
  direction: 'upstream' | 'dependent';
  onNavigate: (kind: AssetKind, key: string) => void;
}) {
  return <section><h3>{title}</h3>{edges.length === 0
    ? <p className="dependency-empty">无声明引用。</p>
    : <ul className="dependency-list">{edges.map((edge, index) => <Evidence key={`${edge.source}:${edge.fromKind}:${edge.fromKey}:${edge.path}:${index}`} edge={edge} direction={direction} onNavigate={onNavigate} />)}</ul>}</section>;
}

export function DependencyPanel({ graph, loading, error, stale, staleReason, canAuthor, unsaved, onRefresh, onNavigate }: {
  graph: DependencyGraph | null;
  loading: boolean;
  error: string | null;
  stale: boolean;
  staleReason: string | null;
  canAuthor: boolean;
  unsaved: boolean;
  onRefresh: () => void;
  onNavigate: (kind: AssetKind, key: string) => void;
}) {
  const draftEdges = graph?.upstream.filter((edge) => edge.source === 'saved-draft') ?? [];
  const publishedEdges = graph?.upstream.filter((edge) => edge.source !== 'saved-draft') ?? [];
  return <section className="readonly-panel dependency-panel" id="dependency-publication-check" aria-label="依赖与发布检查">
    <header className="panel-heading"><div><p className="section-label">只读检查</p><h2>依赖与发布检查</h2></div><button className="quiet-button" type="button" disabled={loading} onClick={onRefresh}>{loading ? '刷新中…' : '显式刷新'}</button></header>
    <p>检查基于当前可信环境和当前选择；它不是运行时、部署保证或发布锁。</p>
    {unsaved ? <div className="notice warning"><strong>未保存本地编辑已排除</strong><span>保存后仍需显式刷新，现有检查结果不会自动改写。</span></div> : null}
    {stale ? <div className="notice warning"><strong>检查结果已过期</strong><span>{staleReason}</span></div> : null}
    {loading && !graph ? <div className="workspace-state">正在读取依赖证据…</div> : null}
    {error ? <div className="notice error"><strong>依赖检查失败</strong><span>{error}</span></div> : null}
    {graph ? <>
      <div className={graph.incomplete ? 'notice error' : 'notice success'}><strong>{graph.incomplete ? '检查不完整，不能判定为可发布' : '当前依赖证据完整'}</strong><span>{graph.truncated ? '结果达到边界并已截断。' : graph.cycle ? '检测到循环引用。' : graph.historyScope}</span></div>
      <EdgeList title="已发布依赖事实" edges={publishedEdges} direction="upstream" onNavigate={onNavigate} />
      {canAuthor ? <EdgeList title="已保存草稿诊断" edges={draftEdges} direction="upstream" onNavigate={onNavigate} /> : null}
      <EdgeList title="反向引用" edges={graph.dependents} direction="dependent" onNavigate={onNavigate} />
    </> : null}
  </section>;
}

export function dependencyKindLabel(kind: DependencyKind): string {
  return kind;
}
