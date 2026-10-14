# Workflow capability nodes

Approved 2026-10-14. Add fixed business capability nodes alongside Skills, including pure capability workflows, management UI authoring, conversational creation and PRT publication. Required missing information is collected in a node-bound temporary interaction; submission automatically resumes that node.

The model generates business arguments from the user's task and causal predecessor facts. It cannot choose a different capability or supply host identity, environment or credentials. Strictly parameter-free capabilities skip parameter generation. Keep the existing serial topology, shared execution policies and native LangGraph persistence.

No new business backend, parameter-mapping editor, automatic repair/retry, approval policy or ONLINE publication is included. Existing execution restrictions remain in force. Source, deployment and actual runtime acceptance are separate gates.
