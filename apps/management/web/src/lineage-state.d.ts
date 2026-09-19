import type { DependencyEdge, DependencyGraph, DependencyNode } from './contracts';

export type LineageDirection = 'both' | 'upstream' | 'downstream';
export type LineageSource = 'all' | DependencyNode['source'];
export interface LineageFilters { direction: LineageDirection; source: LineageSource }
export interface PositionedDependencyNode extends DependencyNode { x: number; y: number }
export interface LineageView { nodes: PositionedDependencyNode[]; edges: DependencyEdge[] }

export function dependencyNodeIdentity(node: DependencyNode): string;
export function dependencyEdgeIdentity(edge: DependencyEdge): string;
export function dependencyEdgeNodes(edge: DependencyEdge): [DependencyNode, DependencyNode];
export function initialExpandedNodes(roots: DependencyNode[]): Set<string>;
export function isNavigableDependencyNode(node: DependencyNode): boolean;
export function buildLineageView(graph: DependencyGraph, filters: LineageFilters, expanded: Set<string>): LineageView;
