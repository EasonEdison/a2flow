import type {RunView,NodeStatus} from '../presentation';
export type FixtureState='RUNNING'|'WAITING'|'SUCCEEDED'|'UNCONFIRMED'|'STOPPED';
export function fixture(state:FixtureState, requirement='为 12 位同事策划一场周末活动，预算 2,400 元。'):RunView {
const ended=state==='SUCCEEDED'; const status:NodeStatus=state==='UNCONFIRMED'?'UNKNOWN':state;
return {id:'fixture-run',title:'周末活动策划',lifecycle:status,requirement,nodes:[
{id:'planning',title:'活动策划',status:ended?'SUCCEEDED':status,summary:ended?'活动方案已确认':state==='WAITING'?'方案已生成，请选择你喜欢的安排':state==='UNCONFIRMED'?'执行结果未确认，请查看运行记录':'结合活动需求，准备适合大家的方案',records:[{id:'r1',kind:'reasoning',text:'这是一条开发示例：结合人数与预算，比较室内工作坊和户外交流两种安排。'},{id:'r2',kind:'operation',text:'示例执行记录：读取活动需求。'},{id:'r3',kind:'text',text:'示例方案已准备，可在卡片中选择。'}],
card:state==='RUNNING'||state==='UNCONFIRMED'?undefined:{id:'fixture-card',title:'选择活动方案',description:'选择后将用于下一步宣传文案。这里的数据仅用于页面开发。',choices:[{value:'indoor',label:'方案 A · 室内工作坊',description:'12 人 / 预算 ¥2,400'},{value:'outdoor',label:'方案 B · 户外交流',description:'12 人 / 预算 ¥2,200'}],operable:state==='WAITING',actionName:'confirm_activity',interactionId:'fixture-interaction',inputKey:'optionId'},output:ended?'开发示例：室内工作坊。主题分享、分组交流与轻松互动。':undefined},
{id:'copy',title:'宣传文案',status:ended?'SUCCEEDED':state==='STOPPED'?'STOPPED':'PENDING',summary:ended?'宣传文案已生成':'使用确认后的活动方案生成文案',records:ended?[{id:'c1',kind:'text',text:'开发示例：已根据选择生成文案。'}]:[],output:ended?'周末，给彼此一点相聚的时间。\n一起分享灵感、交流想法，在轻松的工作坊中发现新的连接。\n本段为开发示例，未发送或发布到任何外部平台。':undefined}]};
}
