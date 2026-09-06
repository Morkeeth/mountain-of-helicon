import {useEffect, useState} from 'react';

type Observation = {snapshot_id:string; observed_at:string; value:unknown; source_state:string; source:{path:string; sha256:string; quote:string; line_start:number; line_end:number}};
type Correction = {id:string; path:string; status:string; reason:string; expected_text:string; replacement:string; before_sha256:string; after_sha256:string; created_at:string; events:{status:string; actor:string; at:string}[]};
type Consumer = {packet_id:string; recipient:{run_id:string; provider:string}; issued_at:string; source_status:string; sources:{path:string;sha256:string}[]; consumption:null|{consumed_at:string;transport:string}; behavior:{verdict:string;evidence:string;artifact:string;artifact_sha256:string;artifact_current:boolean;artifact_preview:string|null;preview_truncated:boolean;reviewer:string;observed_at:string}[]};
type Journey = {id:string;subject:string;predicate:string;state:string;current_values:string[];observations:Observation[];corrections:Correction[];consumers:Consumer[]};
type Report = {checked_at:string; journeys:Journey[]; scope:string;receipt_errors:{id:string;error:string}[]};
const card = {border:'1px solid var(--helicon-line)',background:'var(--helicon-bg)',borderRadius:12,padding:16};
const date = (s:string) => new Date(s).toLocaleString();
const muted = {color:'var(--helicon-muted)'};

export default function MemoryJourney({projectId, revision}:{projectId:string;revision:string}) {
  const [report,setReport]=useState<Report>();
  const [error,setError]=useState('');
  const [selected,setSelected]=useState('');
  const [search,setSearch]=useState('');
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    if(!projectId)return;
    let active=true;setError('');setReport(undefined);
    fetch('/api/context-review/journey?project_id='+encodeURIComponent(projectId),{headers:{'X-Helicon-Local':'1'}})
      .then(async response=>{const data=await response.json();if(!response.ok)throw new Error(data.detail || 'History unavailable');return data;})
      .then(data=>{if(active)setReport(data);}).catch(e=>{if(active)setError(String(e));});
    return()=>{active=false;};
  },[projectId,revision,refresh]);
  const rows=report?.journeys.filter(j=>(j.subject+' '+j.predicate+' '+j.current_values.join(' ')).toLowerCase().includes(search.toLowerCase())) ?? [];
  const journey=rows.find(j=>j.id===selected) ?? rows[0];
  return <section aria-label="Memory journey" className="my-8" style={{borderTop:'1px solid var(--helicon-line)',paddingTop:24}}>
    <p className="text-xs uppercase tracking-widest" style={muted}>Memory · from source to consequence</p>
    <h3 className="text-2xl mt-2">Why do we believe this?</h3>
    <p className="text-sm my-3" style={muted}>Follow an assertion through its source, corrections and receiving runs. What was recorded, what was read, and what happened are separate questions.</p>
    <div className="flex flex-wrap gap-3 my-4">
      <input aria-label="Find a memory" placeholder="Find a project, belief or value…" value={search} onChange={e=>setSearch(e.target.value)} className="p-3 rounded border min-w-0 flex-1" style={card}/>
      <button className="px-3 py-2 border rounded" onClick={()=>setRefresh(n=>n+1)}>Refresh journey</button>
    </div>
    {error && <p role="alert">History unavailable: {error}. No empty-history conclusion.</p>}
    {!report&&!error&&<p>Reading saved evidence…</p>}
    {report&&<>
      <p className="text-xs my-3" style={muted}>Checked {date(report.checked_at)} · this is the inspection time, not the age of a belief.</p>
      {!!report.receipt_errors.length&&<p role="alert">{report.receipt_errors.length} packet record(s) unavailable. Consumer coverage is incomplete.</p>}
      {!rows.length&&<p className="my-5">{report.journeys.length?'No matching saved assertion.':'No saved explicit assertion yet. Review sources and save a review below to begin this history.'}</p>}
      {!!rows.length&&<label className="block my-4 text-sm">Inspect belief<select aria-label="Inspect belief" className="block w-full p-3 mt-2 rounded border" style={card} value={journey?.id} onChange={e=>setSelected(e.target.value)}>{rows.map(j=><option key={j.id} value={j.id}>{j.subject} · {j.predicate}</option>)}</select></label>}
      {journey&&<div className="space-y-5">
        <div style={card}><p className="text-xs uppercase tracking-widest" style={muted}>01 · What the source says now</p><h4 className="text-xl my-3 break-words">{journey.subject} · {journey.predicate}</h4>
          <p className="text-lg break-words">{journey.current_values.join(' / ') || 'Current state unverified'}</p>
          <p className="text-sm mt-3">{journey.state==='disagreement'?'Sources disagree. There is no single established value.':journey.state==='source_assertion'?'The current file matches this saved assertion. Matching bytes do not establish factual truth.':'The saved source changed or disappeared. Its old text remains evidence of history.'}</p>
        </div>
        <div style={card}><p className="text-xs uppercase tracking-widest" style={muted}>02 · Open the evidence</p>
          {journey.observations.map((o,i)=><details key={o.snapshot_id+'-'+i} className="my-4" open={i===journey.observations.length-1}><summary className="cursor-pointer break-words">{String(o.value)} · {date(o.observed_at)} · {o.source_state.replaceAll('_',' ')}</summary><blockquote className="my-3 p-3 border-l-2 whitespace-pre-wrap break-words">{o.source.quote}</blockquote><p className="text-xs break-all">{o.source.path} · lines {o.source.line_start}–{o.source.line_end}</p><p className="text-xs mt-2 break-all">Source SHA256 {o.source.sha256}</p><p className="text-xs mt-2 break-all">Saved review {o.snapshot_id}</p></details>)}
        </div>
        <div style={card}><p className="text-xs uppercase tracking-widest" style={muted}>03 · What changed, and why</p>
          {!journey.corrections.length&&<p className="text-sm mt-3">No correction bound to this assertion’s source span. A new snapshot alone does not prove a correction.</p>}
          {journey.corrections.map(c=><article key={c.id} className="mt-4"><p className="text-sm">Recorded correction · {c.status} · {date(c.created_at)}</p><p className="my-3">{c.reason}</p><div className="grid gap-3 sm:grid-cols-2"><div><p className="text-xs" style={muted}>Earlier assertion</p><pre className="text-sm mt-2 whitespace-pre-wrap break-words">{c.expected_text}</pre></div><div><p className="text-xs" style={muted}>Proposed replacement · status above controls whether applied</p><pre className="text-sm mt-2 whitespace-pre-wrap break-words">{c.replacement}</pre></div></div><details className="text-xs mt-3"><summary>Revision and event trail</summary><p className="break-all my-2">{c.before_sha256} → {c.after_sha256}</p>{c.events.map((e,i)=><p key={i}>{e.status} · {e.actor} · {date(e.at)}</p>)}</details></article>)}
        </div>
        <div style={card}><p className="text-xs uppercase tracking-widest" style={muted}>04 · Did a consumer receive it? Did anything change?</p>
          {!journey.consumers.length&&<p className="text-sm mt-3">No receiving-run packet matches these exact source revisions. Delivery, acknowledgment and behavior remain unproven.</p>}
          {journey.consumers.map(c=><article key={c.packet_id} className="my-4 border-t pt-4"><h5 className="break-words">{c.recipient.provider} · {c.recipient.run_id}</h5>
            <p className="text-sm mt-3"><strong>Prepared:</strong> {date(c.issued_at)}. Source revision: {c.source_status}.</p>
            <p className="text-sm mt-2"><strong>Read / delivery:</strong> {c.consumption?`Interface returned bytes at ${date(c.consumption.consumed_at)} (${c.consumption.transport}).`:'Not observed. Preparation is not delivery.'}</p>
            <p className="text-sm mt-2"><strong>Acknowledgment:</strong> not recorded by this contract. Receipt is not comprehension.</p>
            {!c.behavior.length&&<p className="text-sm mt-2"><strong>Behavior:</strong> not verified.</p>}
            {c.behavior.map((b,i)=><div key={i} className="my-3"><p className="text-sm"><strong>Packet-level behavior review:</strong> {b.verdict} · {b.artifact_current?'reviewed artifact still matches':'artifact changed or unavailable — current behavior unverified'}</p><p className="text-sm mt-2">{b.evidence}</p><p className="text-xs mt-2">This review covers the packet and artifact; it does not establish use of every assertion. Attributed reviewer: {b.reviewer} · {date(b.observed_at)}. This does not prove that memory caused the result.</p><details className="text-xs mt-2"><summary>Open the reviewed result</summary>{b.artifact_preview!==null?<><pre className="whitespace-pre-wrap break-words my-3">{b.artifact_preview}</pre>{b.preview_truncated&&<p>Preview limited to the first 4,000 bytes; hash binds the full file.</p>}</>:<p className="my-3">The exact reviewed bytes are no longer available. No current preview is substituted.</p>}<p className="break-all my-2">{b.artifact}</p><p className="break-all">{b.artifact_sha256}</p></details></div>)}
          </article>)}
        </div>
      </div>}
      <p className="text-xs mt-5" style={muted}>{report.scope}</p>
    </>}
  </section>;
}
