import {useEffect, useState} from 'react';

// WHAT CHANGED MY MIND? One page: dated instruction -> returned work -> later
// correction -> an editable next prompt. The selected item, window and question
// survive every switch, so the lesson is carried without losing context.

type Passage = {id:string; origin:string; file:string; path:string; line:number; heading:string; date:string; date_source:string; text:string; score?:number; redacted?:boolean};
type Work = {path:string; state:string; sha256?:string; excerpt?:string; entries?:string[]; cited_by:string; cited_date:string};
type Decoy = {id:string; file:string; line:number; date:string; score:number; current_score:number; superseded_by:string};
type Item = {topic:string; chain:string[]; instruction:Passage|null; current:Passage[]; superseded:Passage[]; changed_in_window:boolean; returned_work:Work[]; decoys:Decoy[]; lesson:string; next_prompt:string};
type ServedBy = {repo:string; branch:string; head:string; dirty:boolean; module_sha256:string; pid:number; process_started:string};
type Result = {question:string; window_days:number; since:string; as_of:string; items:Item[]; gap:null|{reason:string}; redactions:Record<string,number>; sources:{memory_dir:string; rulings:string; passages_read:number}; served_by:ServedBy};

const card = {border:'1px solid var(--helicon-line)', background:'var(--helicon-bg)', borderRadius:12, padding:16};
const muted = {color:'var(--helicon-muted)'};
const mono = {fontFamily:'var(--helicon-mono)', fontSize:11};
const EXAMPLE = 'can agents create and update SLASK-style Apple Notes boards';

function Quote({p, label, tone}:{p:Passage; label:string; tone?:string}) {
  return (
    <div style={{...card, borderLeft:`3px solid ${tone || 'var(--helicon-line)'}`, marginTop:8}}>
      <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>{label} · {p.date}{p.date_source !== 'text' && p.date_source !== 'ts' ? ` (date from ${p.date_source})` : ''}</div>
      <pre className="mt-2 whitespace-pre-wrap text-[12.5px] leading-relaxed" style={{fontFamily:'inherit', color:'var(--helicon-ink)'}}>{p.text}</pre>
      <div className="mt-2" style={{...mono, ...muted}}>{p.file}:{p.line}{p.heading ? ` · ${p.heading}` : ''}{p.redacted ? ' · paragraph redacted on screen' : ''}</div>
    </div>
  );
}

export default function MindChanges() {
  const [question, setQuestion] = useState(() => new URLSearchParams(location.hash.split('?')[1] || '').get('q') ?? '');
  const [draft, setDraft] = useState(question);
  const [windowDays, setWindowDays] = useState(7);
  const [asOf, setAsOf] = useState('');
  const [result, setResult] = useState<Result>();
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(0);
  const [prompt, setPrompt] = useState('');
  const [saved, setSaved] = useState<{path:string; sha256:string; note:string; pointer:string; packet:{packet_id:string; recipient:{run_id:string}; state:string}}>();
  const [receipt, setReceipt] = useState('');

  useEffect(() => {
    let live = true;
    setError('');
    const qs = new URLSearchParams({q: question, window: String(windowDays), ...(asOf ? {as_of: asOf} : {})});
    fetch('/api/mind-changes?' + qs, {headers: {'X-Helicon-Local': '1'}})
      .then(r => {
        if (!r.ok) return r.text().then(t => Promise.reject(new Error(t)));
        // An older server answers unknown /api paths with the dashboard HTML and 200.
        if (!(r.headers.get('content-type') || '').includes('json'))
          return Promise.reject(new Error(`The server at ${location.host} has no /api/mind-changes route. It is running older code. Restart it from this checkout.`));
        return r.json();
      })
      .then((r: Result) => { if (!live) return; setResult(r); setSelected(0); setSaved(undefined); setPrompt(r.items[0]?.next_prompt ?? ''); })
      .catch(e => live && setError(String(e.message || e)));
    return () => { live = false; };
  }, [question, windowDays, asOf]);

  const item = result?.items[selected];
  const redacted = result ? Object.entries(result.redactions) : [];

  async function checkReceipt() {
    if (!saved) return;
    const qs = new URLSearchParams({packet_id: saved.packet.packet_id, run_id: saved.packet.recipient.run_id});
    const r = await fetch('/api/mind-changes/packet?' + qs, {headers: {'X-Helicon-Local': '1'}});
    if (!r.ok) { setReceipt('unknown: ' + (await r.text())); return; }
    const p = await r.json();
    setReceipt(p.state === 'consumed' ? `consumed ${p.consumption?.consumed_at} over ${p.consumption?.transport}` : `${p.state}, not consumed yet`);
  }

  async function useLesson() {
    if (!item) return;
    const sources = [...item.current, ...(item.instruction ? [item.instruction] : [])].map(p => ({path: p.path, line: p.line, date: p.date}));
    const r = await fetch('/api/mind-changes/lesson', {method: 'POST', headers: {'X-Helicon-Local': '1', 'Content-Type': 'application/json'}, body: JSON.stringify({lesson: item.lesson, prompt, sources})});
    if (r.ok) { setReceipt(''); setSaved(await r.json()); } else setError(await r.text());
  }

  return (
    <div className="max-w-5xl mx-auto px-4 md:px-6 py-6">
      <h1 className="text-[26px]" style={{fontFamily:'var(--helicon-serif)', fontWeight:300, color:'var(--helicon-ink)'}}>What changed my mind?</h1>
      <p className="mt-1 text-[12.5px]" style={muted}>Dated memory content, resolved against later corrections. Lexical match picks the thread; the latest dated ruling wins.</p>

      <form className="mt-4 flex flex-wrap gap-2 items-center" onSubmit={e => { e.preventDefault(); setQuestion(draft.trim()); }}>
        <input value={draft} onChange={e => setDraft(e.target.value)} placeholder="Ask, or leave empty to list every correction in the window" className="flex-1 min-w-[16rem] rounded-lg px-3 py-2 text-[13px]" style={{border:'1px solid var(--helicon-line)', background:'var(--helicon-bg)'}} aria-label="Question" />
        <button type="submit" className="rounded-lg px-3 py-2 text-[12px]" style={{border:'1px solid var(--helicon-line)'}}>Ask</button>
        <button type="button" className="rounded-lg px-3 py-2 text-[12px]" style={{border:'1px solid var(--helicon-line)'}} onClick={() => { setDraft(EXAMPLE); setQuestion(EXAMPLE); }}>Example</button>
        {[7, 30].map(w => (
          <button key={w} type="button" aria-pressed={windowDays === w} onClick={() => setWindowDays(w)} className="rounded-lg px-3 py-2 text-[12px]" style={{border:'1px solid var(--helicon-line)', background: windowDays === w ? 'var(--helicon-ink)' : 'transparent', color: windowDays === w ? 'var(--helicon-bg)' : 'inherit'}}>{w === 7 ? 'Past week' : 'Past month'}</button>
        ))}
        <label className="text-[11px]" style={muted}>as of <input type="date" value={asOf} onChange={e => setAsOf(e.target.value)} className="ml-1 rounded px-1" style={{border:'1px solid var(--helicon-line)'}} /></label>
      </form>

      {result && (
        <div className="mt-3" style={{...mono, ...muted}}>
          served by {result.served_by.repo} · {result.served_by.branch}@{result.served_by.head}{result.served_by.dirty ? '+dirty' : ''} · module {result.served_by.module_sha256} · pid {result.served_by.pid} since {result.served_by.process_started}
          <br />window {result.since} → {result.as_of} · {result.sources.passages_read} passages read from {result.sources.memory_dir} and {result.sources.rulings}
          {redacted.length > 0 && <><br />redacted on screen: {redacted.map(([k, v]) => `${v} ${k}`).join(', ')}</>}
        </div>
      )}
      {error && <div className="mt-3" style={{...card, color:'#b3261e'}}>{error}</div>}

      {result?.gap && (
        <div className="mt-5" style={{...card, borderLeft:'3px solid #b58900'}}>
          <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>Evidence gap</div>
          <p className="mt-2 text-[13px]">{result.gap.reason}</p>
          <p className="mt-1 text-[12px]" style={muted}>No lesson is offered without a dated source.</p>
        </div>
      )}

      {result && result.items.length > 0 && (
        <div className="mt-5 grid gap-4 md:grid-cols-[16rem_1fr]">
          <ol className="flex flex-col gap-2">
            {result.items.map((it, i) => (
              <li key={i}>
                <button onClick={() => { setSelected(i); setPrompt(it.next_prompt); setSaved(undefined); }} className="w-full text-left rounded-lg px-3 py-2 text-[12.5px]" style={{border:'1px solid var(--helicon-line)', background: i === selected ? 'var(--helicon-panel-2)' : 'transparent'}}>
                  <div>{it.current[0].date} · {it.topic.replace(/[_-]/g, ' ')}</div>
                  <div className="text-[11px]" style={muted}>{it.changed_in_window ? `overturned ${it.instruction?.date}` : 'ruling, no earlier instruction found'}</div>
                </button>
              </li>
            ))}
          </ol>

          {item && (
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em]" style={muted}>1 · The instruction</div>
              {item.instruction ? <Quote p={item.instruction} label="Dated instruction" /> : <p className="mt-2 text-[12.5px]" style={muted}>No earlier dated instruction in this thread.</p>}

              <div className="mt-5 text-[10px] uppercase tracking-[0.18em]" style={muted}>2 · The returned work</div>
              {item.returned_work.length === 0 && <p className="mt-2 text-[12.5px]" style={muted}>Gap: no returned-work path is cited in this thread.</p>}
              {item.returned_work.map(w => (
                <div key={w.path} style={{...card, marginTop:8}}>
                  <div style={mono}>{w.path} · <b>{w.state}</b>{w.sha256 ? ` · sha256 ${w.sha256.slice(0, 12)}` : ''}</div>
                  <div className="text-[11px]" style={muted}>cited by {w.cited_by} on {w.cited_date}</div>
                  {w.excerpt && <pre className="mt-2 whitespace-pre-wrap text-[11.5px]" style={mono}>{w.excerpt}</pre>}
                  {w.entries && <div className="mt-2" style={mono}>{w.entries.join('  ')}</div>}
                </div>
              ))}

              <div className="mt-5 text-[10px] uppercase tracking-[0.18em]" style={muted}>3 · The correction that decides it now</div>
              {item.current.map(p => <Quote key={p.id} p={p} label="Current ruling" tone="#2e7d32" />)}
              {item.decoys.map(d => (
                <div key={d.id} className="mt-2 text-[12px]" style={{...card, borderLeft:'3px solid #b3261e'}}>
                  Lexically stronger but older: {d.file}:{d.line} ({d.date}) scored {d.score} against {d.current_score}. It loses to the {d.superseded_by} ruling.
                </div>
              ))}
              {item.superseded.length > 0 && (
                <details className="mt-2"><summary className="text-[12px]" style={muted}>{item.superseded.length} superseded passage(s)</summary>
                  {item.superseded.map(p => <Quote key={p.id} p={p} label="Superseded" tone="#b3261e" />)}
                </details>
              )}

              <div className="mt-5 text-[10px] uppercase tracking-[0.18em]" style={muted}>4 · Use this lesson in the next prompt</div>
              <textarea value={prompt} onChange={e => setPrompt(e.target.value)} rows={9} className="mt-2 w-full rounded-lg p-3 text-[12px]" style={{...mono, border:'1px solid var(--helicon-line)', background:'var(--helicon-bg)'}} aria-label="Next prompt" />
              <div className="mt-2 flex gap-2 items-center">
                <button onClick={useLesson} className="rounded-lg px-3 py-2 text-[12px]" style={{border:'1px solid var(--helicon-line)'}}>Use this lesson in the next prompt</button>
                <button onClick={() => navigator.clipboard?.writeText(prompt)} className="rounded-lg px-3 py-2 text-[12px]" style={{border:'1px solid var(--helicon-line)'}}>Copy</button>
              </div>
              {saved && (
                <div className="mt-2" style={{...card}}>
                  <div style={{...mono, ...muted}}>saved {saved.path} · sha256 {saved.sha256.slice(0, 12)}</div>
                  <div className="mt-1" style={mono}>packet {saved.packet.packet_id.slice(0, 16)} · run {saved.packet.recipient.run_id} · {receipt || saved.packet.state}</div>
                  <div className="mt-1 text-[11.5px]" style={muted}>{saved.note} Give the receiving session this pointer. It carries no lesson text:</div>
                  <pre className="mt-1 whitespace-pre-wrap" style={mono}>{saved.pointer}</pre>
                  <div className="mt-2 flex gap-2">
                    <button onClick={() => navigator.clipboard?.writeText(saved.pointer)} className="rounded-lg px-3 py-1.5 text-[12px]" style={{border:'1px solid var(--helicon-line)'}}>Copy pointer</button>
                    <button onClick={checkReceipt} className="rounded-lg px-3 py-1.5 text-[12px]" style={{border:'1px solid var(--helicon-line)'}}>Check delivery</button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
