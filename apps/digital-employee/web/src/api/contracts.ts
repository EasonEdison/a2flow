/** mvp08.1 wire supplied by Runtime owner. No browser-authored identity. */
export type Json = null | boolean | number | string | Json[] | { [key:string]:Json };
export type JsonObject = { [key:string]:Json };
export type Session = {userId:string;environment:string};
export type Workflow = {definitionKey:string;title:string;inputSchema:JsonObject;nodes:{nodeId:string;title:string;order:number}[]};
export type RunItem = {runId:string;definitionKey:string;title:string;lifecycle:string;createdAt:string};
export type WireNode = {nodeId:string;title:string;order:number;status:'PENDING'|'RUNNING'|'WAITING'|'SUCCEEDED'|'UNCONFIRMED'|'STOPPED';summary:string|null};
export type WireCard = {cardId:string;nodeId:string;interactionId:string;applicationKey:string;applicationVersion:string;protocolProfile:string;componentCatalogRef:string;rootId:string;components:Json;data:JsonObject;inputSchema:JsonObject;actions:{actionName:string;inputSchema:JsonObject}[];state:'WAITING'|'READ_ONLY'|'INVALIDATED';actionEligibility:'REVALIDATION_REQUIRED'|'NOT_OPERABLE'};
export type WireView = {schemaVersion:'mvp08.1';runId:string;definitionKey:string;title:string;definitionVersion:string;createdAt:string;lifecycle:string;revision:string;observedAt:string;nodes:WireNode[];cards:WireCard[];outputs:{nodeId:string;kind:'MODEL_TEXT'|'ACTION_RESULT';content:Json}[];availability:'AVAILABLE'|'UNCONFIRMED'};
export type ProgressRecord = {seq:number;kind:string;observedAt:string;payload:JsonObject};
export type Segment = {node_id:string;execution_id:string;sealed:boolean;incomplete:boolean;observation_outcome:string};
export type History = {runId:string;nodeId:string;executionId:string;records:ProgressRecord[];nextCursor:string;hasMore:boolean;capture:{sealed:boolean;incomplete:boolean;observation_outcome?:string}};
export class ContractError extends Error {constructor(){super('服务返回了不支持的数据格式');}}
export function object(value:unknown):Record<string,unknown>{if(!value||typeof value!=='object'||Array.isArray(value))throw new ContractError();return value as Record<string,unknown>;}
export function string(value:unknown):string{if(typeof value!=='string')throw new ContractError();return value;}
export function list(value:unknown):unknown[]{if(!Array.isArray(value)||value.length>2000)throw new ContractError();return value;}
export function jsonObject(value:unknown):JsonObject {return object(value) as JsonObject;}
export function parseSession(v:unknown):Session {const x=object(v);return {userId:string(x.userId),environment:string(x.environment)};}
export function parseWorkflows(v:unknown):Workflow[]{return list(object(v).items).map(value=>{const x=object(value);return {definitionKey:string(x.definitionKey),title:string(x.title),inputSchema:jsonObject(x.inputSchema),nodes:list(x.nodes).map(n=>{const y=object(n);if(typeof y.order!=='number')throw new ContractError();return {nodeId:string(y.nodeId),title:string(y.title),order:y.order};})};});}
export function parseView(v:unknown):WireView {
const x=object(v);if(x.schemaVersion!=='mvp08.1'||!['AVAILABLE','UNCONFIRMED'].includes(string(x.availability)))throw new ContractError();
for(const key of ['runId','definitionKey','title','definitionVersion','createdAt','lifecycle','observedAt'])string(x[key]);
if(typeof x.revision!=='string')throw new ContractError();
list(x.nodes).forEach(n=>{const y=object(n);string(y.nodeId);string(y.title);if(typeof y.order!=='number'||!['PENDING','RUNNING','WAITING','SUCCEEDED','UNCONFIRMED','STOPPED'].includes(string(y.status))||(y.summary!==null&&typeof y.summary!=='string'))throw new ContractError();});
const cards=list(x.cards);if(cards.length>16)throw new ContractError();cards.forEach(c=>{const y=object(c);for(const key of ['cardId','nodeId','interactionId','applicationKey','applicationVersion','protocolProfile','componentCatalogRef','rootId'])string(y[key]);jsonObject(y.data);jsonObject(y.inputSchema);if(!['WAITING','READ_ONLY','INVALIDATED'].includes(string(y.state))||!['REVALIDATION_REQUIRED','NOT_OPERABLE'].includes(string(y.actionEligibility)))throw new ContractError();list(y.actions).forEach(a=>{const z=object(a);string(z.actionName);jsonObject(z.inputSchema);});});
const outputs=list(x.outputs);if(outputs.length>8)throw new ContractError();outputs.forEach(o=>{const y=object(o);string(y.nodeId);if(!['MODEL_TEXT','ACTION_RESULT'].includes(string(y.kind)))throw new ContractError();});
return x as unknown as WireView;
}
export function parseHistory(v:unknown):History {const x=object(v);for(const k of ['runId','nodeId','executionId','nextCursor'])string(x[k]);if(typeof x.hasMore!=='boolean')throw new ContractError();object(x.capture);list(x.records).forEach(parseRecord);return x as unknown as History;}
export function parseRecord(v:unknown):ProgressRecord {const x=object(v);if(!Number.isSafeInteger(x.seq)||Number(x.seq)<1)throw new ContractError();string(x.kind);string(x.observedAt);object(x.payload);return x as unknown as ProgressRecord;}
