import {object,string,list,parseSession,parseWorkflows,parseView,parseHistory, type JsonObject,type RunItem,type Segment} from './contracts';
export class ApiError extends Error {constructor(public code:string,public status:number){super(code);}}
const encoded=encodeURIComponent;
export async function request(path:string,body?:unknown,signal?:AbortSignal,maxBytes=1024*1024):Promise<unknown> {
const response=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:body===undefined?{Accept:'application/json'}:{Accept:'application/json','Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal,cache:'no-store'});
const text=await response.text();if(text.length>maxBytes)throw new ApiError('OUTPUT_TOO_LARGE',507);
let data:unknown;try{data=JSON.parse(text);}catch{throw new ApiError('INVALID_RESPONSE',response.status);}
if(!response.ok){const error=object(object(data).error);throw new ApiError(string(error.code),response.status);}return data;
}
const runPath=(id:string)=>'/runtime/runs/'+encoded(id);
export function createProgressClient(path: (id: string) => string) {
  return {
    catalog: async (id: string, after?: string, signal?: AbortSignal) => {
      const url = path(id) + '/progress?limit=100' + (after ? '&after=' + encoded(after) : '');
      const value = object(await request(url, undefined, signal));
      const segments = list(value.segments).map(item => {
        const segment = object(item);
        string(segment.node_id);
        string(segment.execution_id);
        return segment as unknown as Segment;
      });
      return { segments, nextCursor: string(value.nextCursor), hasMore: value.hasMore === true };
    },
    history: async (id: string, node: string, execution: string, after?: string, signal?: AbortSignal) => {
      const url = path(id) + '/nodes/' + encoded(node) + '/executions/' + encoded(execution)
        + '/history?limit=100' + (after ? '&after=' + encoded(after) : '');
      return parseHistory(await request(url, undefined, signal));
    },
    streamUrl: (id: string, node: string, execution: string, after?: string) => (
      path(id) + '/nodes/' + encoded(node) + '/executions/' + encoded(execution)
      + '/stream' + (after ? '?after=' + encoded(after) : '')
    ),
  };
}
export type ProgressClient = ReturnType<typeof createProgressClient>;
export const productProgress = createProgressClient(id => '/api/runs/' + encoded(id));
export const client={
session:async(signal?:AbortSignal)=>parseSession(await request('/runtime/session',undefined,signal)),
workflows:async(signal?:AbortSignal)=>parseWorkflows(await request('/runtime/workflows',undefined,signal)),
runs:async(after?:string,signal?:AbortSignal)=>{const x=object(await request('/runtime/runs?limit=20'+(after?'&after='+encoded(after):''),undefined,signal));const items=list(x.items).map(v=>{const y=object(v);for(const k of ['runId','definitionKey','title','lifecycle','createdAt'])string(y[k]);return y as unknown as RunItem;});return {items,nextCursor:x.nextCursor===null?null:string(x.nextCursor)};},
view:async(id:string,signal?:AbortSignal)=>parseView(await request(runPath(id)+'/view',undefined,signal,192*1024)),
control:async(id:string,signal?:AbortSignal)=>{const x=object(await request('/runtime/controls/'+encoded(id),undefined,signal));return {runId:string(x.runId),delivery:string(x.delivery)};},
start:(controlRequestId:string,definitionKey:string,inputs:JsonObject)=>request('/runtime/runs',{controlRequestId,definitionKey,inputs}),
stop:(id:string,controlRequestId:string)=>request(runPath(id)+'/stop',{controlRequestId}),
restart:(id:string,controlRequestId:string,inputs:JsonObject)=>request(runPath(id)+'/restart',{controlRequestId,inputs}),
action:(id:string,nodeId:string,controlRequestId:string,interactionId:string,actionName:string,inputs:JsonObject)=>request(runPath(id)+'/nodes/'+encoded(nodeId)+'/actions',{controlRequestId,interactionId,actionName,inputs}),
...createProgressClient(runPath)
};
