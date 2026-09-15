import {useEffect, useState} from 'react';

type ExampleCase = {label:string; draft:string; context:Record<string,string>};
type Example = {
  example_label:string; original_draft:string; edited_draft:string;
  explicit_instruction:string; inferred_reason:string; proposed_rule:string;
  scope:Record<string,string>; operation:Record<string,string>; cases:ExampleCase[];
};
type Event = {status:string; actor:string; at:string; detail:string};
type Rule = Omit<Example, 'cases'> & {
  id:string; status:string; word_delta:{kind:'removed'|'added'; text:string}[];
  events:Event[]; reason_authority:Record<string,string>; supersedes?:string;
};
type Attempt = ExampleCase & {
  frozen_baseline:string; result:string; changed:boolean; evidence:string;
  applied_rules:{rule_id:string; rule:string}[];
};
type Comparison = {cases:Attempt[]; claim_limit:string};

const panel = {border:'1px solid var(--helicon-line)', borderRadius:12, background:'var(--helicon-bg)'};
const muted = {color:'var(--helicon-muted)'};
const mono = {fontFamily:'var(--helicon-mono)'};
const button = 'rounded-lg px-3 py-2 text-[12px] disabled:opacity-40';

async function call<T>(path:string, body?:unknown):Promise<T> {
  const response = await fetch('/api/correction-transfer/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Helicon-Local':'1', ...(body === undefined ? {} : {'Content-Type':'application/json'})},
    ...(body === undefined ? {} : {body:JSON.stringify(body)}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || `Correction transfer failed (${response.status})`);
  return data;
}

export default function CorrectionTransfer() {
  const [example, setExample] = useState<Example>();
  const [rule, setRule] = useState<Rule>();
  const [comparison, setComparison] = useState<Comparison>();
  const [scope, setScope] = useState<Record<string,string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    call<Example>('example').then(data => {setExample(data); setScope(data.scope);}).catch(e => setError(String(e)));
  }, []);

  async function perform(work:()=>Promise<void>) {
    setBusy(true); setError('');
    try { await work(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }

  async function propose(supersedes?:string, scopeOverride?:Record<string,string>) {
    if (!example) return;
    const data = await call<Rule>('proposals', {
      ...example, cases:undefined, scope:scopeOverride || scope,
      ...(supersedes ? {supersedes, example_label:'Authored supersession example, synthetic'} : {}),
    });
    setRule(data); setComparison(undefined);
  }

  async function decide(decision:'accept'|'reject') {
    if (!rule || !example) return;
    const decided = await call<Rule>(`${rule.id}/decision`, {decision});
    setRule(decided);
    if (decision === 'accept') setComparison(await call<Comparison>('compare', {cases:example.cases}));
    else setComparison(undefined);
  }

  async function saveScope() {
    if (!rule) return;
    setRule(await call<Rule>(`${rule.id}/scope`, {scope}));
  }

  async function undo() {
    if (!rule) return;
    setRule(await call<Rule>(`${rule.id}/undo`, {}));
    setComparison(undefined);
  }

  if (!example) return <div className="py-12">{error || 'Loading authored example…'}</div>;

  return <div className="max-w-5xl mx-auto px-1 py-2">
    <div className="text-[10px] uppercase tracking-[0.2em]" style={muted}>Correction transfer · local only</div>
    <h1 className="mt-2 text-[28px]" style={{fontFamily:'var(--helicon-serif)', fontWeight:300}}>Teach it once. See exactly where it carries.</h1>
    <p className="mt-2 max-w-3xl text-[13px]" style={muted}>One authored example runs draft → edit → proposed lesson → human decision → next attempts. It uses no model and no private corpus.</p>
    <div className="mt-3 inline-flex rounded-full px-3 py-1 text-[10px] uppercase tracking-[0.13em]" style={{background:'var(--helicon-panel-2)', ...muted}}>{example.example_label}</div>

    {error && <p role="alert" className="mt-4 p-3 text-[13px]" style={{...panel, color:'#b3261e'}}>{error}</p>}

    <section className="mt-5 grid gap-3 md:grid-cols-2">
      <div className="p-4" style={panel}>
        <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>1 · Agent draft</div>
        <p className="mt-3 text-[16px]">{example.original_draft}</p>
      </div>
      <div className="p-4" style={{...panel, borderColor:'var(--helicon-accent)'}}>
        <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>2 · Human-edited version</div>
        <p className="mt-3 text-[16px]">{example.edited_draft}</p>
      </div>
    </section>

    <section className="mt-3 p-4" style={panel}>
      <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>Visible word delta</div>
      <div className="mt-3 flex gap-2">
        {(rule?.word_delta || [{kind:'removed' as const,text:'shipped'}, {kind:'added' as const,text:'built'}]).map((item, i) =>
          <span key={i} className="rounded px-2 py-1 text-[13px]" style={{...mono, color:item.kind === 'removed' ? '#b3261e' : '#2e7d32', background:'var(--helicon-panel-2)'}}>{item.kind === 'removed' ? '−' : '+'} {item.text}</span>
        )}
      </div>
      <div className="mt-4 grid gap-3 md:grid-cols-2">
        <div className="rounded-lg p-3" style={{background:'var(--helicon-panel-2)'}}>
          <div className="text-[10px] uppercase tracking-[0.15em]" style={muted}>Explicit human instruction</div>
          <p className="mt-2 text-[13px]">{example.explicit_instruction}</p>
        </div>
        <div className="rounded-lg p-3" style={{background:'var(--helicon-panel-2)'}}>
          <div className="text-[10px] uppercase tracking-[0.15em]" style={muted}>Inferred reason · not an instruction</div>
          <p className="mt-2 text-[13px]">{example.inferred_reason}</p>
        </div>
      </div>
    </section>

    <section className="mt-3 p-4" style={panel}>
      <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>3 · Proposed scoped rule</div>
      <p className="mt-3 text-[15px]">{example.proposed_rule}</p>
      <div className="mt-3 flex flex-wrap gap-3">
        {Object.entries(scope).map(([key, value]) =>
          <label key={key} className="text-[11px]" style={muted}>{key}
            <input className="block mt-1 rounded px-2 py-1.5 text-[12px]" style={{...mono, border:'1px solid var(--helicon-line)', background:'var(--helicon-bg)', color:'var(--helicon-ink)'}} value={value} disabled={busy || !!rule && rule.status !== 'proposed'} onChange={e=>setScope({...scope,[key]:e.target.value})}/>
          </label>
        )}
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {!rule && <button className={button} style={{border:'1px solid var(--helicon-accent)'}} disabled={busy} onClick={()=>void perform(()=>propose())}>Propose this lesson</button>}
        {rule?.status === 'proposed' && <>
          <button className={button} style={{border:'1px solid var(--helicon-line)'}} disabled={busy} onClick={()=>void perform(saveScope)}>Save scope change</button>
          <button className={button} style={{background:'var(--helicon-ink)', color:'var(--helicon-bg)'}} disabled={busy} onClick={()=>void perform(()=>decide('accept'))}>Accept rule</button>
          <button className={button} style={{border:'1px solid var(--helicon-line)'}} disabled={busy} onClick={()=>void perform(()=>decide('reject'))}>Reject rule</button>
        </>}
        {rule && ['accepted','rejected'].includes(rule.status) && <button className={button} style={{border:'1px solid var(--helicon-line)'}} disabled={busy} onClick={()=>void perform(undo)}>Undo decision</button>}
        {rule?.status === 'accepted' && <button className={button} style={{border:'1px solid var(--helicon-line)'}} disabled={busy} onClick={()=>void perform(async()=>{const narrower={...scope, channel:'internal-status'};setScope(narrower);await propose(rule.id,narrower);})}>Propose narrower supersession</button>}
      </div>
      {rule && <div className="mt-3 text-[11px]" style={{...mono, ...muted}}>rule {rule.id} · <b>{rule.status}</b>{rule.supersedes ? ` · supersedes ${rule.supersedes}` : ''}</div>}
    </section>

    {comparison && <section className="mt-3 p-4" style={panel}>
      <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>4 · Next-attempt comparison</div>
      <div className="mt-3 grid gap-3 md:grid-cols-2">
        {comparison.cases.map(item => <div key={item.label} className="rounded-lg p-3" style={{border:`1px solid ${item.changed ? '#2e7d32' : 'var(--helicon-line)'}`}}>
          <div className="text-[11px] uppercase tracking-[0.1em]" style={muted}>{item.label}</div>
          <div className="mt-3 text-[10px] uppercase" style={muted}>Frozen uncorrected baseline</div>
          <p className="mt-1 text-[13px]" style={mono}>{item.frozen_baseline}</p>
          <div className="mt-3 text-[10px] uppercase" style={muted}>Next attempt</div>
          <p className="mt-1 text-[13px]" style={mono}>{item.result}</p>
          <div className="mt-3 text-[11px]" style={{color:item.changed ? '#2e7d32' : 'var(--helicon-muted)'}}>{item.changed ? 'RULE APPLIED' : 'NOT TRANSFERRED'} · {item.evidence}</div>
        </div>)}
      </div>
      <p className="mt-3 text-[11px]" style={muted}>{comparison.claim_limit}</p>
    </section>}

    {rule && <details className="mt-3 p-4 text-[12px]" style={panel}>
      <summary className="cursor-pointer">Inspectable decision history</summary>
      {rule.events.map((event, i)=><div key={i} className="mt-2" style={{...mono, ...muted}}>{event.status} · {event.actor} · {event.at}<br/>{event.detail}</div>)}
    </details>}

    <p className="mt-4 text-[11px]" style={muted}>Private corpus remains local. Run <code style={mono}>helicon teach trial /path/to/case.json --decision accept --state ~/.helicon/correction-transfer</code> on the machine that holds the drafts.</p>
  </div>;
}
