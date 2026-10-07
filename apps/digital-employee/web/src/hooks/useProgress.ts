import {useEffect,useState} from 'react';
import {client, type ProgressClient} from '../api/client';import {parseRecord} from '../api/contracts';import {recordLine} from '../api/adapter';import type {RecordLine} from '../presentation';
/** Two sequential Skills: max two observers; committed history always precedes SSE. */
export function useProgress(runId:string|null, transport: ProgressClient = client) {
const [state,setState]=useState<{runId:string|null;records:Record<string,RecordLine[]>;error:string}>({runId:null,records:{},error:''});
useEffect(()=>{if(!runId)return;const abort=new AbortController();let alive=true;let poll:ReturnType<typeof setTimeout>;const streams=new Map<string,EventSource>();const cursors=new Map<string,string>();const completed=new Set<string>();const reconnecting=new Set<string>();const retryTimers=new Set<ReturnType<typeof setTimeout>>();const seen=new Set<string>();
const unavailable=()=>{if(alive)setState(p=>({runId,records:p.runId===runId?p.records:{},error:'部分过程记录暂不可用，节点状态仍以服务端记录为准。'}));};
const add=(node:string,execution:string,value:unknown)=>{const r=parseRecord(value);const key=execution+':'+r.seq;if(seen.has(key))return;seen.add(key);cursors.set(execution,key);if(alive)setState(p=>{const records=p.runId===runId?p.records:{};return {runId,error:p.runId===runId?p.error:'',records:{...records,[node]:[...(records[node]??[]),recordLine(execution,r)].slice(-2000)}};});};
const connect=(node:string,execution:string)=>{if(!alive||completed.has(execution)||streams.has(execution))return;reconnecting.delete(execution);const source=new EventSource(transport.streamUrl(runId,node,execution,cursors.get(execution)),{withCredentials:true});streams.set(execution,source);
source.addEventListener('progress',e=>{try{add(node,execution,JSON.parse((e as MessageEvent).data));}catch{source.close();streams.delete(execution);unavailable();}});
source.addEventListener('capture_end',()=>{completed.add(execution);source.close();streams.delete(execution);});
source.addEventListener('capture',e=>{try{const data=JSON.parse((e as MessageEvent).data);if(data.capture?.incomplete||data.capture?.observation_outcome==='UNAVAILABLE')unavailable();}catch{unavailable();}});
source.addEventListener('error',()=>{source.close();streams.delete(execution);if(!alive)return;unavailable();if(reconnecting.has(execution))return;reconnecting.add(execution);const timer=setTimeout(()=>{retryTimers.delete(timer);connect(node,execution);},3000);retryTimers.add(timer);});
};
const discover=async()=>{try{let cursor:string|undefined;for(let page=0;page<20;page++){const catalog=await transport.catalog(runId,cursor,abort.signal);for(const segment of catalog.segments){const execution=segment.execution_id;if(seen.has('segment:'+execution))continue;if(streams.size>=2)break;let after:string|undefined;let sealed=segment.sealed;for(let i=0;i<20;i++){const history=await transport.history(runId,segment.node_id,execution,after,abort.signal);for(const r of history.records)add(segment.node_id,execution,r);after=history.nextCursor;cursors.set(execution,after);sealed=history.capture.sealed;if(history.capture.incomplete)unavailable();if(!history.hasMore)break;}
seen.add('segment:'+execution);if(sealed)completed.add(execution);else connect(segment.node_id,execution);}
if(!catalog.hasMore)break;cursor=catalog.nextCursor;}}catch{if(alive)unavailable();}finally{if(alive)poll=setTimeout(discover,2000);}};
void discover();return()=>{alive=false;abort.abort();clearTimeout(poll);for(const s of streams.values())s.close();for(const t of retryTimers)clearTimeout(t);};
},[runId,transport]);
return state.runId===runId?state:{runId,records:{},error:''};
}
