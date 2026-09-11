import {object,string,list,ContractError,type WireCard,type WireView,type ProgressRecord} from './contracts';
import type {CardView,NodeStatus,RecordLine,RunView} from '../presentation';
const allowedKeys=(x:Record<string,unknown>,keys:string[])=>{if(Object.keys(x).some(k=>!keys.includes(k)))throw new ContractError();};
const binding=(v:unknown,path:string)=>{const x=object(v);allowedKeys(x,['path']);if(x.path!==path)throw new ContractError();};
export function cardView(card:WireCard,active:boolean):CardView {
if(card.protocolProfile!=='a2flow.mvp08.v1')throw new ContractError();
const components=list(card.components).map(object);
if(components.length!==4||new Set(components.map(c=>string(c.id))).size!==4)throw new ContractError();
const root=components.find(c=>c.id===card.rootId);if(!root||root.component!=='Column')throw new ContractError();allowedKeys(root,['id','component','children']);
const children=list(root.children).map(string);if(children.length!==3||new Set(children).size!==3)throw new ContractError();
const parts=children.map(id=>{const c=components.find(x=>x.id===id);if(!c)throw new ContractError();return c;});
const [text,choice,button]=parts;
if(text.component!=='Text'||choice.component!=='ChoicePicker'||button.component!=='Button')throw new ContractError();
allowedKeys(text,['id','component','text']);binding(text.text,'/prompt');
allowedKeys(choice,['id','component','options','value','variant']);binding(choice.options,'/options');binding(choice.value,'/optionId');if(choice.variant!=='mutuallyExclusive')throw new ContractError();
allowedKeys(button,['id','component','label','action']);const action=object(button.action);allowedKeys(action,['event']);const event=object(action.event);allowedKeys(event,['name','context']);const name=string(event.name);const context=object(event.context);allowedKeys(context,['optionId','confirmed']);binding(context.optionId,'/optionId');const confirmation=object(context.confirmed);allowedKeys(confirmation,['literal']);if(confirmation.literal!==true)throw new ContractError();
if(card.actions.length!==1||card.actions[0].actionName!==name)throw new ContractError();
const choices=list(card.data.options).map(item=>{const x=object(item);allowedKeys(x,['label','value']);return {label:string(x.label),value:string(x.value)};});
if(!choices.length||choices.length>20||new Set(choices.map(c=>c.value)).size!==choices.length)throw new ContractError();
const selected=card.data.optionId===undefined?undefined:string(card.data.optionId);if(selected!==undefined&&!choices.some(c=>c.value===selected))throw new ContractError();
return {id:card.cardId,title:string(card.data.prompt),choices,selected,operable:active&&card.state==='WAITING'&&card.actionEligibility==='REVALIDATION_REQUIRED',actionName:name,interactionId:card.interactionId,inputKey:'optionId'};
}
export function recordLine(execution:string,r:ProgressRecord):RecordLine {
const p=r.payload;const labels:Record<string,string>={MODEL_STARTED:'模型开始处理',MODEL_RETURNED:'模型调用返回',MODEL_UNCONFIRMED:'模型调用结果未确认',TOOL_STARTED:'能力调用开始',TOOL_RETURNED:'能力调用返回',TOOL_INTERRUPTED:'能力等待交互',TOOL_UNCONFIRMED:'能力调用结果未确认',NODE_STARTED:'节点开始执行',NODE_RETURNED:'节点调用返回',NODE_INTERRUPTED:'节点等待交互',NODE_UNCONFIRMED:'节点执行结果未确认',CAPTURE_INCOMPLETE:'过程记录不完整'};
return {id:execution+':'+r.seq,kind:r.kind==='REASONING_DELTA'?'reasoning':r.kind==='TEXT_DELTA'?'text':'operation',text:['REASONING_DELTA','TEXT_DELTA'].includes(r.kind)?string(p.text):(labels[r.kind]??'已记录执行事件')+(typeof p.toolName==='string'?' · '+p.toolName:'')};
}
export function toView(w:WireView,records:Record<string,RecordLine[]>):RunView {
const status=(s:string):NodeStatus=>['PENDING','RUNNING','WAITING','SUCCEEDED','STOPPED'].includes(s)?s as NodeStatus:'UNKNOWN';
return {id:w.runId,title:w.title,lifecycle:status(w.lifecycle),nodes:[...w.nodes].sort((a,b)=>a.order-b.order).map(n=>{
const cards=w.cards.filter(c=>c.nodeId===n.nodeId);if(cards.length>1)throw new ContractError();
return {id:n.nodeId,title:n.title,status:status(n.status),summary:n.summary??undefined,records:records[n.nodeId]??[],card:cards[0]?cardView(cards[0],w.lifecycle==='RUNNING'&&n.status==='WAITING'):undefined,output:w.outputs.filter(o=>o.nodeId===n.nodeId).map(o=>(o.kind==='MODEL_TEXT'?'模型输出\n':'已保存的交互结果\n')+(typeof o.content==='string'?o.content:JSON.stringify(o.content,null,2))).join('\n\n')||undefined,incomplete:w.availability==='UNCONFIRMED'};
})};
}
