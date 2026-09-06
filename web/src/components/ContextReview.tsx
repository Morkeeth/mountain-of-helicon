import { useEffect, useState } from 'react';
import ContextPacketPanel from './ContextPacketPanel';
import MemoryJourney from './MemoryJourney';

type Project = {id: string; name: string; path: string};
type Evidence = {source_id: string; path: string; sha256: string; line_start: number; line_end: number; quote: string};
type Finding = {id: string; title: string; consequence: string; action: string; kind: string; evidence: Evidence[]; probe?: {verdict: string; object: unknown; command: unknown; output: unknown; observed_at: string}};
type Source = {id: string; path: string; harness: string; status: string; sha256: string; mtime?: string; configuration?: {state: string; basis: string}; loading?: {state: string}};
type Report = {project: string; observed_at: string; sources: Source[]; findings: Finding[]; coverage: Record<string, unknown>};
type Snapshot = {id: string; observed_at: string; findings: number};
type Correction = {id: string; status: string; path: string; reason?: string; diff: string; actor: string; created_at: string; events: {status: string; actor?: string; at?: string}[]};
type Preview = {id: string; hash: string; diff: string};
type Comparison = {groups: {label: string; items: {id: string; title: string; reason?: string}[]}[]};

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/context-review/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Helicon-Local': '1', ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Review failed (${response.status}). Your source has not been approved by this message.`);
  return data;
}

const buttonClass = 'text-sm px-3 py-2 rounded border disabled:opacity-40';
const inputStyle = {background: 'var(--helicon-bg)', border: '1px solid var(--helicon-line)', color: 'var(--helicon-ink)'};

export default function ContextReview() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState('');
  const [report, setReport] = useState<Report>();
  const [revision, setRevision] = useState('');
  const [snapshotId, setSnapshotId] = useState('');
  const [history, setHistory] = useState<Snapshot[]>();
  const [historyError, setHistoryError] = useState('');
  const [corrections, setCorrections] = useState<Correction[]>([]);
  const [comparison, setComparison] = useState<Comparison>();
  const [baseline, setBaseline] = useState('');
  const [findingId, setFindingId] = useState('');
  const [evidenceIndex, setEvidenceIndex] = useState(0);
  const [replacement, setReplacement] = useState('');
  const [reason, setReason] = useState('');
  const [preview, setPreview] = useState<Preview>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const selected = report?.findings.find(f => f.id === findingId);
  const evidence = selected?.evidence[evidenceIndex];
  const project = projects.find(p => p.id === projectId);
  // This is a display hint only. The server enforces real-path scope and revision.
  const editable = evidence && project && evidence.path.startsWith(project.path + '/');

  useEffect(() => {
    request<{projects: Project[]}>('projects').then(data => {
      setProjects(data.projects); setProjectId(data.projects[0]?.id ?? '');
    }).catch(e => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    let current = true;
    setHistory(undefined); setHistoryError('');
    request<{snapshots: Snapshot[]; corrections: Correction[]}>(`history?project_id=${encodeURIComponent(projectId)}`).then(data => {
      if (current) {setHistory(data.snapshots); setCorrections(data.corrections);}
    }).catch(e => {if (current) setHistoryError(String(e));});
    return () => {current = false;};
  }, [projectId]);

  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await action(); } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function refreshHistory() {
    const data = await request<{snapshots: Snapshot[]; corrections: Correction[]}>(`history?project_id=${encodeURIComponent(projectId)}`);
    setHistory(data.snapshots); setCorrections(data.corrections); setHistoryError('');
  }
  async function read() {
    const data = await request<{report: Report; revision: string}>('read', {project_id: projectId});
    setReport(data.report); setRevision(data.revision); setSnapshotId(''); setPreview(undefined);
    setFindingId('');
    setComparison(undefined); await refreshHistory();
  }
  function chooseFinding(f: Finding) {
    setFindingId(f.id); setEvidenceIndex(0); setReplacement(f.evidence[0]?.quote ?? '');
    setReason(''); setPreview(undefined);
  }

  return <section className="mb-7" aria-label="Project context review">
    <details open>
      <summary className="cursor-pointer text-lg">Memory history and project instructions</summary>
      <p className="text-sm my-3" style={{color: 'var(--helicon-muted)'}}>Inspect a disagreement, review a correction, and check whether it holds next time. Global instructions are read-only here.</p>
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-sm">Project <select aria-label="Context project" disabled={busy} className="p-2 rounded ml-2 max-w-full" style={inputStyle} value={projectId} onChange={e => {
          setProjectId(e.target.value); setReport(undefined); setFindingId(''); setSnapshotId(''); setPreview(undefined); setHistory([]); setCorrections([]); setComparison(undefined); setBaseline('');
        }}>{projects.map(p => <option value={p.id} key={p.id}>{p.name}</option>)}</select></label>
        <button className={buttonClass} disabled={busy || !projectId} onClick={() => void perform(read)}>{busy ? 'Working…' : 'Review sources'}</button>
      </div>
      {error && <p className="text-sm my-4" role="alert">{error}</p>}
      {notice && <p className="text-sm my-4" role="status">{notice}</p>}
        <MemoryJourney projectId={projectId} revision={revision + snapshotId + corrections.map(c=>c.id+c.status).join()} />
      {report && <>
        <p className="text-xs mt-4 break-words" style={{color: 'var(--helicon-muted)'}}>Read {new Date(report.observed_at).toLocaleString()}. {report.project}</p>
        <div className="my-5">
          {report.findings.length ? report.findings.map(f => <div className="py-3" key={f.id}>
            <button disabled={busy} className="text-left text-sm underline underline-offset-4" onClick={() => chooseFinding(f)}>{f.title}</button>
            <p className="text-sm mt-1">{f.consequence}</p>
          </div>) : <p className="text-sm">No disagreement found by these checks. This does not establish that all instructions are correct or loaded.</p>}
        </div>
        <button className={buttonClass} disabled={busy || !!snapshotId} onClick={() => void perform(async () => {
          const saved = await request<{id: string}>('snapshots', {project_id: projectId, revision});
          setSnapshotId(saved.id); await refreshHistory(); setNotice('Review saved with its source versions. No instructions changed.');
        })}>{snapshotId ? 'Review saved' : 'Save this review'}</button>
        {selected && <div className="my-6 pt-4" style={{borderTop: '1px solid var(--helicon-line)'}}>
          <h3 className="text-lg">{selected.title}</h3>
          <p className="text-sm my-2">{selected.action}</p>
          {selected.evidence.map((item, i) => <div key={`${item.source_id}-${i}`} className="my-4">
            <p className="text-xs break-words" style={{color: 'var(--helicon-muted)'}}>{item.path} · lines {item.line_start}–{item.line_end}</p>
            <pre className="text-sm whitespace-pre-wrap break-words my-2 p-3" style={{borderLeft: '2px solid var(--helicon-line)'}}>{item.quote}</pre>
            <button disabled={busy} className="text-sm underline" onClick={() => { setEvidenceIndex(i); setReplacement(item.quote); setPreview(undefined); }}>Review this source text</button>
          </div>)}
          {selected.probe && <details className="text-sm my-3"><summary>Object check: {selected.probe.verdict}</summary><dl className="mt-2 break-words">{Object.entries(selected.probe).map(([k,v]) => <div key={k}><dt className="inline">{k}: </dt><dd className="inline">{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>)}</dl></details>}
          {evidence && (editable ? <div className="my-4">
            <p className="text-sm mb-3 break-words">Correction for {evidence.path}. Your reason records the ruling; the tool does not decide unsettled intent.</p>
            <label className="block text-sm">Replacement text<textarea disabled={busy} aria-label="Replacement text" className="block w-full mt-2 p-3 rounded" style={inputStyle} rows={4} value={replacement} onChange={e => {setReplacement(e.target.value); setPreview(undefined);}} /></label>
            <label className="block text-sm mt-3">Why this is correct<input disabled={busy} aria-label="Correction reason" className="block w-full mt-2 p-2 rounded" style={inputStyle} value={reason} onChange={e => {setReason(e.target.value); setPreview(undefined);}} /></label>
            {!snapshotId && <p className="text-sm my-3">Save this review before proposing a correction.</p>}
            <button className={`${buttonClass} mt-3`} disabled={busy || !snapshotId || !reason.trim() || replacement === evidence.quote} onClick={() => void perform(async () => {
              const data = await request<Preview>('preview', {project_id: projectId, snapshot_id: snapshotId, finding_id: selected.id, evidence_index: evidenceIndex, replacement, reason});
              setPreview(data);
            })}>Preview correction</button>
            {preview && <div className="mt-4"><pre className="text-xs whitespace-pre-wrap break-words p-3" style={inputStyle}>{preview.diff}</pre><button className={`${buttonClass} mt-3`} disabled={busy} onClick={() => void perform(async () => {
              await request('apply', {project_id: projectId, preview_id: preview.id, preview_hash: preview.hash});
              await read(); setNotice('Correction applied and its source revision verified. Review the new findings below; agent delivery is still unproven.');
            })}>Apply this correction</button></div>}
          </div> : <p className="text-sm my-4">This source is outside the selected project. It is read-only in this review.</p>)}
        </div>}
        <details className="text-sm my-5"><summary className="cursor-pointer">Sources and coverage limits</summary>
          {report.sources.map(s => <div key={s.id} className="my-4 break-words"><p>{s.harness}: {s.path}</p><p className="mt-1">File: {s.status}. Configuration: {s.configuration?.state ?? 'unknown'}. Loading: {s.loading?.state ?? 'unknown'}.</p><p className="text-xs mt-1">{s.configuration?.basis}</p><p className="text-xs">Revision: {s.sha256 || 'Unavailable'}{s.mtime ? ` · source modified ${s.mtime}` : ''}</p></div>)}
          <dl>{Object.entries(report.coverage).map(([k,v]) => <div className="my-2 break-words" key={k}><dt>{k.replaceAll('_',' ')}</dt><dd style={{color:'var(--helicon-muted)'}}>{typeof v === 'string' ? v : JSON.stringify(v)}</dd></div>)}</dl>
        </details>
      </>}
        <ContextPacketPanel projectId={projectId} projectPath={project?.path} snapshotId={snapshotId} sources={report?.sources} disabled={busy} onBusyChange={setBusy} />
        <details className="text-sm my-5"><summary className="cursor-pointer">Earlier reviews and corrections</summary>
          {historyError && <p role="alert">Saved history is unavailable. {historyError}</p>}
          {history?.length ? <div className="my-4"><label>Compare with <select disabled={busy} aria-label="Earlier review" className="p-2 ml-2 rounded max-w-full" style={inputStyle} value={baseline} onChange={e => {setBaseline(e.target.value); setComparison(undefined);}}><option value="">Choose a saved review</option>{history.map(s => <option key={s.id} value={s.id}>{new Date(s.observed_at).toLocaleString()} · {s.findings} findings</option>)}</select></label><button className={`${buttonClass} mt-3`} disabled={busy || !baseline} onClick={() => void perform(async () => {
            setComparison(await request<Comparison>('compare', {project_id: projectId, baseline_id: baseline}));
          })}>Check what changed</button></div> : <p className="my-3">{history ? 'No saved review for this project yet.' : historyError ? 'No empty-history claim can be made.' : 'Loading saved reviews…'}</p>}
          {comparison?.groups.filter(g => g.items.length).map(g => <div className="my-4" key={g.label}><p className="font-medium">{g.label}</p>{g.items.map(item => <p className="my-2" key={item.id}>{item.title}{item.reason ? ` — ${item.reason}` : ''}</p>)}</div>)}
          {comparison && comparison.groups.every(g => !g.items.length) && <p className="my-3">No findings changed in this comparison. Coverage limits still apply.</p>}
          {corrections.map(c => <div className="my-4" key={c.id}><p className="break-words">{c.path} · {c.status}</p><p className="mt-1">{c.reason}</p><details className="mt-2"><summary>Inspect correction</summary><p className="my-2">Declared actor: {c.actor}. Created {new Date(c.created_at).toLocaleString()}.</p><pre className="whitespace-pre-wrap break-words text-xs">{c.diff}</pre>{c.events.map((event,i) => <p className="text-xs mt-2" key={i}>{event.status} · {event.actor} · {event.at}</p>)}{c.status === 'applied' && <button className={`${buttonClass} mt-2`} disabled={busy} onClick={() => void perform(async () => {
            await request('undo', {project_id: projectId, correction_id: c.id}); await read(); setNotice('Correction undone. Earlier text restored; history retained.');
          })}>Undo correction</button>}</details></div>)}
        </details>
    </details>
  </section>;
}
