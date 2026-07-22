import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArtifactView } from './ArtifactView';

/* GOVERNED RUNS (V2.2) — the atomic unit of the control plane.
   Forward runs freeze their contract before work. Imported sessions preserve
   their retrospective provenance and show repository artifacts as observations,
   not as proven session output. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const GOOD = 'var(--helicon-good)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';

type Tokens = { input?: number; output?: number; cache_read?: number; cache_creation?: number; total?: number };
type Prompt = { ts?: string; text: string; source?: string };
type Artifact = { path: string; content_hash?: string; observed_at?: string; state?: string };
type Governed = { objective?: string; acceptance_test?: string; verification_outcome?: string };
type Run = {
  id: string; task_run_id?: string; provenance: string; repo: string; branch?: string;
  start_commit?: string; model?: string; harness?: string; tokens: Tokens; cost_status?: string;
  duration_min?: number; prompt_chain: Prompt[]; prompt_count?: number; artifact_manifest: Artifact[];
  status: string; human_acceptance?: string | null; needs_human: boolean; governed?: Governed | null;
  events?: { ts: string; kind: string; actor: string; detail: string }[]; receipt?: string;
};
type Session = { session_id: string; path: string; repo: string; branch?: string; model?: string; total_tokens?: number; duration_min?: number; harness?: string };

const fmtInt = (n?: number) => (n == null ? '—' : n.toLocaleString());
const repoName = (p: string) => (p || '').split('/').filter(Boolean).pop() || p;

export default function GovernedRuns() {
  const [data, setData] = useState<{ runs: Run[]; needs_you: number; total: number } | null>(null);
  const [sel, setSel] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch('/api/run/list').then(r => r.json()).then(d => {
      setData(d);
      setSel(prev => prev ?? d.runs.find((r: Run) => r.needs_human)?.id ?? d.runs[0]?.id ?? null);
    }).catch(e => setErr(String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const selected = useMemo(() => data?.runs.find(r => r.id === sel) || null, [data, sel]);
  if (err) return <div className="py-16 text-center text-[13px]" style={{ color: MUTED }}>Backend unreachable: {err}</div>;
  if (!data) return <div className="py-16 text-center text-[13px]" style={{ color: MUTED }}>Reading your runs…</div>;

  if (data.total === 0) return <CaptureFlow onDone={load} />;

  return (
    <div>
      <div className="flex items-center justify-between border-b pb-4 mb-5" style={{ borderColor: 'var(--helicon-line)' }}>
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] mb-1" style={{ color: MUTED }}>Governed Runs</div>
          <h1 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[22px] md:text-[27px] leading-tight">
            {data.total} run{data.total === 1 ? '' : 's'} · {data.needs_you === 0 ? <span style={{ color: GOOD }}>none need you</span> : <span>{data.needs_you} need your verdict</span>}
          </h1>
        </div>
        <CaptureButton onDone={load} />
      </div>
      <div className="md:flex md:gap-8">
        <div className={`md:w-[300px] md:shrink-0 ${selected ? 'hidden md:block' : 'block'}`}>
          <div className="space-y-2">
            {data.runs.map(r => <RunRow key={r.id} r={r} active={r.id === sel} onClick={() => setSel(r.id)} />)}
          </div>
        </div>
        <div className={`flex-1 min-w-0 ${selected ? 'block' : 'hidden md:block'}`}>
          {selected ? <RunDetail key={selected.id} run={selected} onBack={() => setSel(null)} onRuled={load} /> : null}
        </div>
      </div>
    </div>
  );
}

function RunRow({ r, active, onClick }: { r: Run; active: boolean; onClick: () => void }) {
  const acc = r.human_acceptance;
  const dot = acc === 'accepted' ? GOOD : acc === 'rework' || acc === 'rollback' ? 'var(--helicon-critical)' : r.needs_human ? 'var(--helicon-stale)' : FAINT;
  return (
    <button onClick={onClick} className="w-full text-left p-3.5 rounded-xl transition-all"
      style={{ background: active ? 'var(--helicon-panel-2)' : 'var(--helicon-panel)', border: `1px solid ${active ? 'var(--helicon-line-2)' : 'var(--helicon-line)'}` }}>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: dot }} />
        <span className="text-[14px] font-medium truncate" style={{ color: INK, fontFamily: SERIF }}>{r.governed?.objective || `${repoName(r.repo)} session`}</span>
      </div>
      <div className="mt-1 text-[11px] truncate" style={{ color: FAINT, fontFamily: MONO }}>{repoName(r.repo)} · {r.branch} · {r.model || '—'}</div>
      <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-[10.5px]" style={{ color: FAINT, fontFamily: MONO }}>
        <span>{fmtInt(r.tokens?.total)} tok</span>
        <span>{r.prompt_count ?? r.prompt_chain?.length ?? 0} prompt(s)</span>
        <span style={{ color: r.provenance === 'imported' ? 'var(--helicon-stale)' : GOOD }}>{r.provenance}</span>
        <span>{acc || r.status}</span>
      </div>
    </button>
  );
}

function Field({ label, children, mono }: { label: string; children: React.ReactNode; mono?: boolean }) {
  return (
    <div>
      <div className="text-[9.5px] uppercase tracking-[0.14em]" style={{ color: MUTED }}>{label}</div>
      <div className="text-[12.5px] mt-0.5" style={{ color: INK, fontFamily: mono ? MONO : undefined }}>{children}</div>
    </div>
  );
}

function RunDetail({ run, onBack, onRuled }: { run: Run; onBack: () => void; onRuled: () => void }) {
  const [art, setArt] = useState<Artifact | null>(run.artifact_manifest?.[0] || null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const t = run.tokens || {};

  const rule = async (verdict: 'accepted' | 'rework' | 'rollback') => {
    if (!run.task_run_id) { setMsg('This run is imported — govern it first to record a verdict.'); return; }
    setBusy(true); setMsg(null);
    try {
      const r = await fetch('/api/run/accept', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ task_run_id: run.task_run_id, verdict, note: '' }) }).then(x => x.json());
      if (!r.ok) { setMsg(r.error || 'failed'); return; }
      setMsg(verdict === 'accepted' ? (r.promotion?.ok ? 'Accepted — prompt promoted to the reusable library.' : 'Accepted.') : verdict === 'rework' ? 'Sent back for rework (prompt not promoted).' : 'Rolled back (prompt not promoted).');
      setTimeout(onRuled, 900);
    } finally { setBusy(false); }
  };

  return (
    <div className="animate-fade-in">
      <button onClick={onBack} className="md:hidden text-[12px] mb-3" style={{ color: ACCENT }}>← all runs</button>
      <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[20px] md:text-[24px] leading-snug">{run.governed?.objective || `${repoName(run.repo)} session`}</h2>
      {run.governed?.acceptance_test && (
        <div className="mt-2 p-2.5 rounded-lg" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
          <span className="text-[9.5px] uppercase tracking-[0.14em]" style={{ color: MUTED }}>
            {run.provenance === 'imported' ? 'Acceptance recorded retrospectively ' : 'Acceptance contract (frozen before work) '}
          </span>
          <span className="text-[12.5px]" style={{ color: INK }}>{run.governed.acceptance_test}</span>
        </div>
      )}

      {/* execution envelope */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
        <Field label="model" mono>{run.model || '—'}</Field>
        <Field label="harness" mono>{run.harness || '—'}</Field>
        <Field label="repo · branch" mono>{repoName(run.repo)} · {run.branch}</Field>
        <Field label="commit" mono>{(run.start_commit || '').slice(0, 8) || '—'}</Field>
        <Field label="total tokens" mono>{fmtInt(t.total)}</Field>
        <Field label="out / in" mono>{fmtInt(t.output)} / {fmtInt(t.input)}</Field>
        <Field label="cost" mono>{run.cost_status === 'unknown' ? 'unknown' : run.cost_status}</Field>
        <Field label="provenance" mono>{run.provenance}</Field>
      </div>

      {/* prompt chain */}
      <section className="mt-6">
        <div className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>Prompt chain ({run.prompt_chain?.length || 0}) — verbatim</div>
        <div className="space-y-1.5 max-h-52 overflow-y-auto">
          {(run.prompt_chain || []).map((p, i) => (
            <div key={i} className="p-2.5 rounded-lg text-[12px] leading-relaxed" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', color: INK }}>
              <span style={{ color: FAINT, fontFamily: MONO }} className="text-[10px]">{i + 1}. </span>{p.text.length > 300 ? p.text.slice(0, 300) + '…' : p.text}
            </div>
          ))}
          {(run.prompt_chain || []).length === 0 && <p className="text-[12px]" style={{ color: FAINT }}>No user prompts captured for this session.</p>}
        </div>
      </section>

      {/* artifact */}
      <section className="mt-6">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: MUTED }}>Artifact ({run.artifact_manifest?.length || 0})</div>
          <div className="flex gap-1.5 ml-auto flex-wrap">
            {(run.artifact_manifest || []).slice(0, 6).map(a => (
              <button key={a.path} onClick={() => setArt(a)} className="text-[10.5px] px-2 py-0.5 rounded-lg" style={{ color: art?.path === a.path ? 'var(--helicon-on-dark)' : MUTED, background: art?.path === a.path ? ACCENT : 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', fontFamily: MONO }}>{a.path.split('/').pop()}</button>
            ))}
          </div>
        </div>
        {run.provenance === 'imported' && (
          <p className="mb-2 text-[11px]" style={{ color: FAINT }}>
            Repository state observed when this session was imported; attribution to the session is unverified.
          </p>
        )}
        <div className="p-3 rounded-xl" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', maxHeight: 320, overflowY: 'auto' }}>
          {art ? <ArtifactView repoPath={run.repo} art={{ type: 'markdown', label: art.path, ref: art.path, content_hash: art.content_hash }} /> : <p className="text-[12px]" style={{ color: FAINT }}>No artifact captured.</p>}
        </div>
        {art?.content_hash && <p className="mt-1 text-[10px]" style={{ color: FAINT, fontFamily: MONO }}>sha256:{art.content_hash} · {art.state}</p>}
      </section>

      {/* verdict */}
      <section className="mt-7">
        <div className="text-[10px] uppercase tracking-[0.16em] mb-1" style={{ color: MUTED }}>Your verdict</div>
        <p className="text-[11.5px] mb-2.5" style={{ color: FAINT }}>Did this run achieve the intended outcome, or only complete the mechanical implementation?</p>
        {run.human_acceptance && run.human_acceptance !== 'pending' ? (
          <div className="text-[13px]" style={{ color: run.human_acceptance === 'accepted' ? GOOD : 'var(--helicon-critical)' }}>Ruled: {run.human_acceptance}</div>
        ) : (
          <div className="flex flex-wrap gap-2">
            <button disabled={busy} onClick={() => rule('accepted')} className="px-4 py-2 rounded-lg text-[13px] font-medium disabled:opacity-40" style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Accept</button>
            <button disabled={busy} onClick={() => rule('rework')} className="px-4 py-2 rounded-lg text-[13px] bg-white disabled:opacity-40" style={{ border: '1px solid var(--helicon-line-2)', color: INK }}>Rework</button>
            <button disabled={busy} onClick={() => rule('rollback')} className="px-4 py-2 rounded-lg text-[13px] bg-white disabled:opacity-40" style={{ border: '1px solid var(--helicon-line-2)', color: 'var(--helicon-critical)' }}>Reject</button>
          </div>
        )}
        {msg && <p className="mt-2.5 text-[12px]" style={{ color: INK }}>{msg}</p>}
      </section>

      {/* receipt + events */}
      {run.events && run.events.length > 0 && (
        <section className="mt-6 pt-4" style={{ borderTop: '1px solid var(--helicon-line)' }}>
          <div className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>Receipt (append-only)</div>
          <div className="text-[11px] space-y-0.5" style={{ color: MUTED, fontFamily: MONO }}>
            {run.events.map((e, i) => <div key={i}>{e.kind} · {e.actor}{e.detail ? ` · ${e.detail.slice(0, 60)}` : ''}</div>)}
          </div>
        </section>
      )}
    </div>
  );
}

/* Capture a real session into a governed Run (empty state + button share this). */
function CaptureFlow({ onDone }: { onDone: () => void }) {
  return (
    <div className="py-16 text-center max-w-md mx-auto">
      <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[24px] leading-tight">No governed runs yet.</div>
      <p className="mt-2 text-[13px] leading-relaxed" style={{ color: MUTED }}>Capture one of your real Claude Code sessions — Helicon reads its prompts, model, tokens and artifact, and you rule the outcome. Nothing is hand-copied.</p>
      <div className="mt-6"><CaptureButton onDone={onDone} big /></div>
    </div>
  );
}

function CaptureButton({ onDone, big }: { onDone: () => void; big?: boolean }) {
  const [open, setOpen] = useState(false);
  const [sessions, setSessions] = useState<Session[] | null>(null);
  const [pick, setPick] = useState<Session | null>(null);
  const [objective, setObjective] = useState('');
  const [acceptance, setAcceptance] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const openSheet = async () => {
    setOpen(true); setErr(null);
    const d = await fetch('/api/run/sessions?limit=15').then(r => r.json()).catch(() => ({ sessions: [] }));
    setSessions(d.sessions || []);
  };
  const capture = async () => {
    if (!pick || !objective.trim() || !acceptance.trim()) { setErr('pick a session and set objective + acceptance'); return; }
    setBusy(true); setErr(null);
    try {
      const cap = await fetch('/api/run/capture', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ path: pick.path }) }).then(x => x.json());
      if (!cap.ok) { setErr(cap.error || 'capture failed'); return; }
      const g = await fetch('/api/run/govern', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ capture_id: cap.capture_id, objective: objective.trim(), acceptance: acceptance.trim() }) }).then(x => x.json());
      if (!g.ok) { setErr(g.error || 'govern failed'); return; }
      setOpen(false); setPick(null); setObjective(''); setAcceptance(''); onDone();
    } finally { setBusy(false); }
  };

  return (
    <>
      <button onClick={openSheet} className={`rounded-lg font-medium ${big ? 'px-5 py-2.5 text-[14px]' : 'px-3.5 py-1.5 text-[12.5px]'}`} style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Capture a session</button>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end md:items-center justify-center" style={{ background: 'rgba(23,40,58,0.32)' }} onClick={() => setOpen(false)}>
          <div onClick={e => e.stopPropagation()} className="w-full md:max-w-lg rounded-t-2xl md:rounded-2xl p-5 max-h-[85vh] overflow-y-auto" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)' }}>
            <div className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>Pick a real safe session</div>
            <div className="space-y-1.5 max-h-52 overflow-y-auto">
              {sessions == null ? <p className="text-[12px]" style={{ color: FAINT }}>Discovering…</p> : sessions.length === 0 ? <p className="text-[12px]" style={{ color: FAINT }}>No safe sessions found.</p> : sessions.map(s => (
                <button key={s.session_id} onClick={() => setPick(s)} className="w-full text-left p-2.5 rounded-lg text-[12px]" style={{ background: pick?.session_id === s.session_id ? 'var(--helicon-accent-dim)' : 'var(--helicon-panel-2)', border: `1px solid ${pick?.session_id === s.session_id ? ACCENT : 'var(--helicon-line)'}`, color: INK }}>
                  <span style={{ fontFamily: MONO }}>{repoName(s.repo)} · {s.branch} · {s.model || '—'} · {fmtInt(s.total_tokens)} tok</span>
                </button>
              ))}
            </div>
            <div className="mt-4 space-y-2.5">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] mb-1" style={{ color: MUTED }}>Objective</div>
                <input value={objective} onChange={e => setObjective(e.target.value)} placeholder="what was this run for?" className="w-full px-3 py-2 rounded-lg text-[13px] outline-none" style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] mb-1" style={{ color: MUTED }}>Acceptance contract (what does "accepted" mean?)</div>
                <input value={acceptance} onChange={e => setAcceptance(e.target.value)} placeholder="the run is accepted when…" className="w-full px-3 py-2 rounded-lg text-[13px] outline-none" style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
              </div>
            </div>
            {err && <p className="mt-2 text-[12px]" style={{ color: 'var(--helicon-critical)' }}>{err}</p>}
            <div className="mt-4 flex items-center gap-3">
              <button disabled={busy} onClick={capture} className="px-4 py-2 rounded-lg text-[13px] font-medium disabled:opacity-40" style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>{busy ? 'Capturing…' : 'Capture + govern'}</button>
              <button onClick={() => setOpen(false)} className="text-[13px]" style={{ color: MUTED }}>Cancel</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
