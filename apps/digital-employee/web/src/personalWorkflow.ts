export type PersonalWorkflowNode = {
  nodeId: string;
  displayName?: string;
} & ({ type: 'SKILL'; skillKey: string } | { type: 'BUSINESS_CAPABILITY'; abilityKey: string });

export type PersonalWorkflow = {
  definitionKey: string;
  name: string;
  source: 'PERSONAL';
  defaultRequirement: string;
  nodes: PersonalWorkflowNode[];
};

const object = (value: unknown): Record<string, unknown> => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
  return value as Record<string, unknown>;
};
const text = (value: unknown): string => {
  if (typeof value !== 'string' || !value.trim()) throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
  return value;
};

export function parsePersonalWorkflow(value: unknown): PersonalWorkflow {
  const row = object(value);
  if (row.source !== 'PERSONAL' || typeof row.defaultRequirement !== 'string' || row.defaultRequirement.length > 2000
    || !Array.isArray(row.nodes) || row.nodes.length < 1 || row.nodes.length > 8) {
    throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
  }
  const ids = new Set<string>();
  const nodes = row.nodes.map((value): PersonalWorkflowNode => {
    const node = object(value);
    const nodeId = text(node.nodeId);
    if (ids.has(nodeId)) throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
    ids.add(nodeId);
    if (node.displayName !== undefined && typeof node.displayName !== 'string') throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
    const base = { nodeId, ...(node.displayName === undefined ? {} : { displayName: node.displayName as string }) };
    if (node.type === 'SKILL') return { ...base, type: 'SKILL', skillKey: text(node.skillKey) };
    if (node.type === 'BUSINESS_CAPABILITY') return { ...base, type: 'BUSINESS_CAPABILITY', abilityKey: text(node.abilityKey) };
    throw new Error('PERSONAL_WORKFLOW_CONTRACT_INVALID');
  });
  return { definitionKey: text(row.definitionKey), name: text(row.name), source: 'PERSONAL',
    defaultRequirement: row.defaultRequirement, nodes };
}
