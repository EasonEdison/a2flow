import { useId, useState } from 'react';
import type { CardView } from '../presentation';
export function ChoiceCard({card, busy, onSubmit}: {card:CardView;busy:boolean;onSubmit:(value:string)=>Promise<void>}) {
const group=useId(); const [choice,setChoice]=useState(card.selected ?? ''); const [error,setError]=useState('');
return <section className="choice-card" aria-label={card.title}>
<div className="card-heading"><h3>{card.title}</h3><span className={'badge '+(card.operable?'waiting':'neutral')}>{card.operable?'需要你的确认':'只读记录'}</span></div>
{card.description?<p>{card.description}</p>:null}
<form onSubmit={async e=>{e.preventDefault();if(!choice||!card.operable||busy)return;setError('');try{await onSubmit(choice);}catch{setError('提交未确认，请查看请求状态后再操作。');}}}>
<fieldset disabled={!card.operable||busy}><legend className="sr-only">选择活动方案</legend><div className="choices">{card.choices.map(item=><label key={item.value} className={'choice '+(choice===item.value?'selected':'')}><input type="radio" name={group} value={item.value} checked={choice===item.value} onChange={()=>setChoice(item.value)}/><span><strong>{item.label}</strong>{item.description?<small>{item.description}</small>:null}</span></label>)}</div></fieldset>
{card.operable?<button className="primary full" disabled={!choice||busy} type="submit">{busy?'正在提交…':'确认方案并继续'}</button>:<p className="readonly-note">此卡片保留供查看，无法继续操作。</p>}
{error?<p role="alert" className="inline-error">{error}</p>:null}
</form></section>;
}
