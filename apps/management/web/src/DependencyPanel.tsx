import { useEffect, useMemo, useState } from 'react';
import type { AssetKind, DependencyEdge, DependencyGraph, DependencyKind, DependencyNode } from './contracts';
import {
  buildLineageView,
  dependencyEdgeIdentity,
  dependencyEdgeNodes,
  dependencyNodeIdentity,
  initialExpandedNodes,
  isNavigableDependencyNode,
} from './lineage-state.js';
import type { LineageDirection, LineageSource } from './lineage-state.js';

function nodeVersion(node: DependencyNode): string {
  if (node.versionId) return `版本 ${node.versionId}`;
  if (node.revision !== undefined) return `草稿修订 #${node.revision}`;
  return '无版本证据';
}

function sourceLabel(source: DependencyNode['source']): string {
  return source === 'saved-draft' ? '已保存草稿' : source === 'retained' ? '保留版本' : '已发布';
}

function NodeEvidence({ node, root, expanded, expandable, selected, onSelect, onToggle }: {
  node: DependencyNode;
  root: boolean;
  expanded: boolean;
  expandable: boolean;
  selected: boolean;
  onSelect: () => void;
  onToggle: () => void;
}) {
  return <li className={selected ? 'lineage-list-node selected' : 'lineage-list-node'}>
    <button type="button" className="lineage-node-button" aria-pressed={selected} onClick={onSelect}>
      <strong>{node.kind} · {node.key}</strong>
      <span>{root ? '根节点 · ' : ''}{sourceLabel(node.source)} · {nodeVersion(node)}</span>
      <span>{node.environment} · {node.status === 'missing' ? '缺失' : node.selection ?? '已解析'}</span>
    </button>
    {expandable ? <button type="button" className="quiet-button" aria-expanded={expanded} onClick={onToggle}>{expanded ? '收起分支' : '展开分支'}</button> : null}
  </li>;
}

function EdgeEvidence({ edge, selected, onSelect, onNavigate }: {
  edge: DependencyEdge;
  selected: boolean;
  onSelect: () => void;
  onNavigate: (kind: AssetKind, key: string) => void;
}) {
  const [from, target] = dependencyEdgeNodes(edge);
  const navigable = isNavigableDependencyNode(target);
  return <li className={edge.error ? 'dependency-edge error' : 'dependency-edge'}>
    <button type="button" className={selected ? 'lineage-edge-button selected' : 'lineage-edge-button'} aria-pressed={selected} onClick={onSelect}>
      <strong>{from.kind} · {from.key} → {target.kind} · {target.key}</strong>
      <code>{edge.path}</code>
      <span>{edge.selectorType === 'exact-release' ? `精确版本 ${edge.requestedVersionId}` : '逻辑 Key'}</span>
    </button>
    <span>{sourceLabel(edge.source)}</span>
    {edge.targetsInspectedVersion === false ? <span className="warning-text">此引用不指向当前检查版本</span> : null}
    {edge.error ? <span className="error">{edge.error}</span> : null}
    {edge.cycle ? <span className="error">检测到循环</span> : null}
    {navigable ? <button className="quiet-button" type="button" onClick={() => onNavigate(target.kind as AssetKind, target.key)}>查看目标详情</button> : null}
  </li>;
}

function LineageGraph({ graph, canAuthor, onNavigate }: {
  graph: DependencyGraph;
  canAuthor: boolean;
  onNavigate: (kind: AssetKind, key: string) => void;
}) {
  const visibleGraph = useMemo(() => canAuthor ? graph : {
    ...graph,
    rootVariants: (graph.rootVariants ?? [graph.root]).filter((node) => node.source !== 'saved-draft'),
    upstream: graph.upstream.filter((edge) => edge.source !== 'saved-draft'),
    dependents: graph.dependents.filter((edge) => edge.source !== 'saved-draft'),
    diagnostics: [],
  }, [canAuthor, graph]);
  const roots = visibleGraph.rootVariants?.length ? visibleGraph.rootVariants : [visibleGraph.root];
  const graphIdentity = roots.map(dependencyNodeIdentity).join('\n');
  const [direction, setDirection] = useState<LineageDirection>('both');
  const [source, setSource] = useState<LineageSource>('all');
  const [expanded, setExpanded] = useState<Set<string>>(() => initialExpandedNodes(roots));
  const [selectedNode, setSelectedNode] = useState<string>(() => dependencyNodeIdentity(visibleGraph.root));
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  useEffect(() => {
    setDirection('both');
    setSource('all');
    setExpanded(initialExpandedNodes(roots));
    setSelectedNode(dependencyNodeIdentity(visibleGraph.root));
    setSelectedEdge(null);
  }, [graphIdentity]);
  const view = useMemo(() => buildLineageView(visibleGraph, { direction, source }, expanded), [visibleGraph, direction, source, expanded]);
  const rootIds = new Set(roots.map(dependencyNodeIdentity));
  const nodeById = new Map(view.nodes.map((node) => [dependencyNodeIdentity(node), node]));
  const edgeById = new Map(view.edges.map((edge) => [dependencyEdgeIdentity(edge), edge]));
  const selectedNodeValue = nodeById.get(selectedNode);
  const selectedEdgeValue = selectedEdge ? edgeById.get(selectedEdge) : undefined;
  const connected = new Set(view.edges.flatMap((edge) => dependencyEdgeNodes(edge).map(dependencyNodeIdentity)));
  const width = Math.max(720, ...view.nodes.map((node) => node.x + 190));
  const height = Math.max(260, ...view.nodes.map((node) => node.y + 82));
  const reset = () => {
    setDirection('both');
    setSource('all');
    setExpanded(initialExpandedNodes(roots));
    setSelectedNode(dependencyNodeIdentity(visibleGraph.root));
    setSelectedEdge(null);
  };
  return <section className="lineage-explorer" aria-label="资产血缘图">
    <header className="lineage-heading">
      <div><p className="section-label">声明配置血缘</p><h3>资产血缘图</h3></div>
      <button type="button" className="quiet-button" onClick={reset}>重置视图</button>
    </header>
    <p>箭头表示“来源资产依赖目标资产”。仅展示本次 API 返回的声明引用，不代表完整历史或执行来源。</p>
    <div className="lineage-controls">
      <label>方向<select aria-label="血缘方向" value={direction} onChange={(event) => setDirection(event.target.value as LineageDirection)}><option value="both">上游与下游</option><option value="upstream">仅上游依赖</option><option value="downstream">仅下游依赖方</option></select></label>
      <label>来源<select aria-label="证据来源" value={source} onChange={(event) => setSource(event.target.value as LineageSource)}><option value="all">全部来源</option><option value="published">已发布</option><option value="retained">保留版本</option>{canAuthor ? <option value="saved-draft">已保存草稿</option> : null}</select></label>
      <span>{view.nodes.length} 节点 · {view.edges.length} 条可见边</span>
    </div>
    {view.edges.length === 0 ? <div className="lineage-empty">当前筛选下无返回的声明引用；不表示全局不存在引用。</div> : <>
      <div className="lineage-canvas" tabIndex={0} aria-label="可滚动资产血缘画布">
        <svg width={width} height={height} role="img" aria-label={`资产血缘图，${view.nodes.length} 个节点，${view.edges.length} 条边`}>
          <defs><marker id="lineage-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" /></marker></defs>
          {view.edges.map((edge) => {
            const [from, target] = dependencyEdgeNodes(edge);
            const start = nodeById.get(dependencyNodeIdentity(from));
            const end = nodeById.get(dependencyNodeIdentity(target));
            if (!start || !end) return null;
            const id = dependencyEdgeIdentity(edge);
            return <g key={id} className={selectedEdge === id ? 'lineage-svg-edge selected' : 'lineage-svg-edge'} onClick={() => { setSelectedEdge(id); setSelectedNode(''); }}>
              <line x1={start.x + 164} y1={start.y + 30} x2={end.x} y2={end.y + 30} markerEnd="url(#lineage-arrow)" />
              <title>{from.key} 依赖 {target.key}，路径 {edge.path}</title>
            </g>;
          })}
          {view.nodes.map((node) => {
            const id = dependencyNodeIdentity(node);
            return <g key={id} className={`lineage-svg-node ${node.status}${selectedNode === id ? ' selected' : ''}`} transform={`translate(${node.x} ${node.y})`} onClick={() => { setSelectedNode(id); setSelectedEdge(null); }}>
              <rect width="164" height="62" rx="8" /><text x="10" y="20">{node.kind}</text><text x="10" y="39">{node.key.length > 20 ? `${node.key.slice(0, 19)}…` : node.key}</text><text x="10" y="54">{sourceLabel(node.source)} · {node.versionId ?? (node.revision !== undefined ? `r${node.revision}` : '—')}</text>
            </g>;
          })}
        </svg>
      </div>
      <div className="lineage-detail" aria-live="polite">
        {selectedNodeValue ? <><strong>节点证据</strong><dl><div><dt>身份</dt><dd>{selectedNodeValue.kind} · {selectedNodeValue.key}</dd></div><div><dt>来源</dt><dd>{sourceLabel(selectedNodeValue.source)}</dd></div><div><dt>版本</dt><dd>{nodeVersion(selectedNodeValue)}</dd></div><div><dt>环境</dt><dd>{selectedNodeValue.environment}</dd></div><div><dt>状态</dt><dd>{selectedNodeValue.status}</dd></div>{selectedNodeValue.selection ? <div><dt>选择</dt><dd>{selectedNodeValue.selection}</dd></div> : null}</dl>{isNavigableDependencyNode(selectedNodeValue) ? <button className="quiet-button" type="button" onClick={() => onNavigate(selectedNodeValue.kind as AssetKind, selectedNodeValue.key)}>查看资产详情</button> : null}</> : null}
        {selectedEdgeValue ? <><strong>引用证据</strong><dl><div><dt>方向</dt><dd>{selectedEdgeValue.fromKind} · {selectedEdgeValue.fromKey} 依赖 {selectedEdgeValue.toKind} · {selectedEdgeValue.toKey}</dd></div><div><dt>路径</dt><dd>{selectedEdgeValue.path}</dd></div><div><dt>选择器</dt><dd>{selectedEdgeValue.selectorType}{selectedEdgeValue.requestedVersionId ? ` · ${selectedEdgeValue.requestedVersionId}` : ''}</dd></div><div><dt>来源</dt><dd>{sourceLabel(selectedEdgeValue.source)}</dd></div>{selectedEdgeValue.targetsInspectedVersion !== undefined ? <div><dt>指向当前检查版本</dt><dd>{selectedEdgeValue.targetsInspectedVersion ? '是' : '否'}</dd></div> : null}{selectedEdgeValue.error ? <div><dt>错误</dt><dd>{selectedEdgeValue.error}</dd></div> : null}</dl></> : null}
      </div>
      <details className="lineage-accessible" open><summary>可访问列表视图</summary><ul>{view.nodes.map((node) => {
        const id = dependencyNodeIdentity(node);
        return <NodeEvidence key={id} node={node} root={rootIds.has(id)} expanded={expanded.has(id)} expandable={connected.has(id)} selected={selectedNode === id} onSelect={() => { setSelectedNode(id); setSelectedEdge(null); }} onToggle={() => setExpanded((current) => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next; })} />;
      })}</ul><h4>可见引用</h4><ul className="dependency-list">{view.edges.map((edge) => { const id = dependencyEdgeIdentity(edge); return <EdgeEvidence key={id} edge={edge} selected={selectedEdge === id} onSelect={() => { setSelectedEdge(id); setSelectedNode(''); }} onNavigate={onNavigate} />; })}</ul></details>
    </>}
  </section>;
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
    {loading && graph ? <div className="notice warning"><strong>正在刷新</strong><span>当前仍显示上一份证据，刷新完成前不得视为最新结果。</span></div> : null}
    {error ? <div className="notice error"><strong>依赖检查失败</strong><span>{error}</span></div> : null}
    {graph ? <>
      <div className={graph.incomplete ? 'notice error' : 'notice success'}><strong>{graph.incomplete ? '检查不完整，不能判定为可发布' : '当前依赖证据完整'}</strong><span>{graph.truncated ? '结果达到边界并已截断。' : graph.cycle ? '检测到循环引用。' : graph.historyScope}</span></div>
      <div className="lineage-boundary"><span>范围：{graph.historyScope}</span><span>上限：深度 {graph.limits.maxDepth} · 节点 {graph.limits.maxNodes} · 边 {graph.limits.maxEdges}</span>{graph.counts ? <span>API 返回：{graph.counts.nodes} 节点 · {graph.counts.edges} 边</span> : null}</div>
      <LineageGraph graph={graph} canAuthor={canAuthor} onNavigate={onNavigate} />
      <details><summary>原始方向证据列表</summary>
        <section><h3>已发布依赖事实</h3>{publishedEdges.length ? <ul className="dependency-list">{publishedEdges.map((edge) => <EdgeEvidence key={dependencyEdgeIdentity(edge)} edge={edge} selected={false} onSelect={() => undefined} onNavigate={onNavigate} />)}</ul> : <p className="dependency-empty">无声明引用。</p>}</section>
        {canAuthor ? <section><h3>已保存草稿诊断</h3>{draftEdges.length ? <ul className="dependency-list">{draftEdges.map((edge) => <EdgeEvidence key={dependencyEdgeIdentity(edge)} edge={edge} selected={false} onSelect={() => undefined} onNavigate={onNavigate} />)}</ul> : <p className="dependency-empty">无声明引用。</p>}</section> : null}
      </details>
    </> : !loading && !error ? <div className="lineage-empty">尚无依赖证据。请显式刷新。</div> : null}
  </section>;
}

export function dependencyKindLabel(kind: DependencyKind): string {
  return kind;
}
