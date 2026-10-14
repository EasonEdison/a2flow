# Design

## Authoring and publication

A workflow has one to eight business nodes plus an optional summary. Management graph capability nodes use nodeType BUSINESS_CAPABILITY, nodeCode, displayName, abilityKey and optional nodePrompt. abilityKey is the stable published action code; management dependencies resolve the internal asset identity server-side. Capability nodes do not add skip controls or parameter mappings. Existing Skill contracts stay valid.

WORKFLOW_CAPABILITY_CANDIDATES(workflowCode) returns abilityKey, displayName, description and draftId from existing published directories. Candidate discovery can aggregate environments; publication must resolve uniquely within its actual target environment and reject missing or ambiguous dependencies. A candidate is not runtime authorization.

Runtime nodes use type BUSINESS_CAPABILITY, nodeId, abilityKey and optional displayName/nodePrompt. Legacy skillKey nodes with no type remain valid. Runtime dependencies include ABILITY identities. Both manual authoring and management conversation tools use the same validation, compilation and publication services.

## Execution

Resolve the current effective capability under trusted invocation context. Only a closed empty business-argument schema skips the model and uses {}. Optional business fields still require consideration. For other schemas, reuse the existing model/Agent infrastructure to propose complete arguments or identify required missing information.

Missing information uses the existing temporary interaction generator, persistence and native interrupt/resume. The interaction's input schema is separate from the capability schema: supported question, selection and explanation fields collect user facts without pretending every nested business schema is a flat form. After submission, model continuation uses the original task, saved arguments/context and the actual submitted facts to produce complete arguments. Latest explicit submissions update earlier missing-information statements; already supplied values are facts, not examples to ask for again. Required-field absence enters collection with partial arguments retained; other schema failures remain explicit. This is normal task continuation, not automatic repair after a failed validation or business call.

Validate the final arguments against the real capability contract before the fixed capability is invoked through the existing controlled execution boundary. Do not fabricate Skill admission. For registered RPC capabilities, enforce the published contract, trusted identity, environment, argument schema and registered method policy. Do not impose the unrelated legacy local OperationSpec MODEL field on that RPC contract; existing applicable authorization restrictions remain enforced. Unknown outcomes cannot be retried automatically.

Persist generated parameters, interaction facts, execution state and true structured results. Downstream nodes and summary receive causal structured facts, not only assistant prose. Historical reads must not replay model or business calls. Stop and terminal-state gates apply equally to new nodes and their cards.

## Implementation ownership and rollout

Java owns graph parsing/compiler, capability candidates, publication dependencies and management-tool authoring contracts. Python owns shared validation, runtime execution, missing-input continuation, structural result context and necessary B backend compatibility. Frontend owns the management editor and any necessary B rendering adapters. The coordinator owns integration and reversible deployment.

Build frontend and Java off-host. Deploy readers before enabling new published node definitions; preserve prior images/configuration and static assets. Validate both a capability-only workflow and a Skill/capability mix through real PRT execution, using registered read-only synthetic demonstration data.
