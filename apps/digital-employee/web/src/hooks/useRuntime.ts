import {useCallback,useEffect,useRef,useState} from 'react';
import {client,ApiError} from '../api/client';import {object,string,type Session,type Workflow,type RunItem,type WireView,type JsonObject} from '../api/contracts';
type Pending={id:string;kind:'start'|'action'|'stop'|'restart';runId?:string};
const errorText=(e:unknown)=>e instanceof ApiError?({RESET_REQUIRED:'配置已变化，请显式停止后重新开始。',RUN_STOPPED:'此运行已停止，卡片只读。',TRUSTED_CONTEXT_REQUIRED:'请通过受认证入口打开页面。',CAPACITY_EXHAUSTED:'执行容量已满，请稍后查看请求状态。',CONTROL_NOT_FOUND:'请求尚未分配运行，请稍后查看。'}[e.code]??'服务暂不可用（'+e.code+'）'):e instanceof Error?e.message:'服务暂不可用';
export function useRuntime(enabled:boolean) {
const [session,setSession]=useState<Session|null>(null);const [workflows,setWorkflows]=useState<Workflow[]>([]);const [runs,setRuns]=useState<RunItem[]>([]);const [view,setView]=useState<WireView|null>(null);const [runId,setRunId]=useState<string|null>(new URLSearchParams(location.search).get('run'));const [error,setError]=useState('');const [loading,setLoading]=useState(enabled);const [pending,setPending]=useState<Pending|null>(null);const [uncertain,setUncertain]=useState(false);const dispatchLock=useRef(false);
const storage=useRef<string|null>(null);const current=useRef(runId);current.current=runId;const alive=useRef(true);
useEffect(()=>{alive.current=true;return()=>{alive.current=false;};},[]);
const select=useCallback((id:string|null)=>{setView(null);setRunId(id);const url=new URL(location.href);if(id)url.searchParams.set('run',id);else url.searchParams.delete('run');history.replaceState(null,'',url);},[]);
const remember=(value:Pending|null)=>{setPending(value);if(storage.current){if(value)sessionStorage.setItem(storage.current,JSON.stringify(value));else sessionStorage.removeItem(storage.current);}};
useEffect(()=>{if(!enabled)return;const abort=new AbortController();(async()=>{try{const identity=await client.session(abort.signal);if(abort.signal.aborted)return;setSession(identity);storage.current='a2flow.pending.v1:'+identity.environment+':'+identity.userId;const saved=sessionStorage.getItem(storage.current);if(saved){try{const p=JSON.parse(saved);if(typeof p.id==='string'&&['start','action','stop','restart'].includes(p.kind))setPending(p);}catch{sessionStorage.removeItem(storage.current);}}
const [definitions,history]=await Promise.all([client.workflows(abort.signal),client.runs(undefined,abort.signal)]);if(abort.signal.aborted)return;setWorkflows(definitions);setRuns(history.items);
}catch(e){if(!abort.signal.aborted)setError(errorText(e));}finally{if(!abort.signal.aborted)setLoading(false);}})();return()=>abort.abort();},[enabled]);
useEffect(()=>{if(!enabled||!session)return;let cancelled=false;const abort=new AbortController();let timer:ReturnType<typeof setTimeout>;
const poll=async()=>{try{
if(pending){try{const receipt=await client.control(pending.id,abort.signal);if(cancelled)return;if((pending.kind==='start'||pending.kind==='restart')&&current.current!==receipt.runId)select(receipt.runId);if(receipt.delivery==='RETURNED'){remember(null);setUncertain(false);}else if(receipt.delivery==='UNCONFIRMED'){setUncertain(true);setError('请求执行结果未确认。请查看原运行，勿重复提交。');}}catch(e){if(!(e instanceof ApiError&&e.code==='NOT_FOUND'))throw e;}}
if(current.current){const id=current.current;const next=await client.view(id,abort.signal);if(!cancelled&&current.current===id)setView(next);}
}catch(e){if(!cancelled)setError(errorText(e));}finally{if(!cancelled)timer=setTimeout(poll,1500);}};void poll();return()=>{cancelled=true;abort.abort();clearTimeout(timer);};},[enabled,session,pending,select]);
const mutate=async(kind:Pending['kind'],execute:(id:string)=>Promise<unknown>)=>{if(pending||dispatchLock.current)throw new Error('上次请求尚未确认');dispatchLock.current=true;const id=crypto.randomUUID();remember({id,kind,runId:current.current??undefined});setError('');try{const response=object(await execute(id));if(!alive.current)return;const resultId=string(response.runId);if(kind==='start'||kind==='restart')select(resultId);remember(null);setUncertain(false);const next=await client.view(resultId);if(alive.current&&current.current===resultId)setView(next);const history=await client.runs();if(alive.current)setRuns(history.items);}catch(e){if(alive.current){const rejected=e instanceof ApiError&&([400,401,404,409,413].includes(e.status)||e.code==='CAPACITY_EXHAUSTED');if(rejected){remember(null);setUncertain(false);setError(errorText(e));}else{setUncertain(true);setError(errorText(e)+' 请求编号已保留，可查询原请求。');}}throw e;}finally{dispatchLock.current=false;}};
return {session,workflows,runs,view,runId,error,loading,pending,uncertain,select,
start:(key:string,inputs:JsonObject)=>mutate('start',id=>client.start(id,key,inputs)),
stop:()=>{if(!runId)throw new Error('未选择运行');return mutate('stop',id=>client.stop(runId,id));},
restart:(inputs:JsonObject)=>{if(!runId||view?.lifecycle!=='STOPPED')throw new Error('请先明确停止原运行');return mutate('restart',id=>client.restart(runId,id,inputs));},
action:(nodeId:string,interactionId:string,name:string,inputs:JsonObject)=>{if(!runId)throw new Error('未选择运行');return mutate('action',id=>client.action(runId,nodeId,id,interactionId,name,inputs));},
refresh:async()=>{if(runId)setView(await client.view(runId));},
};
}
