import { useCallback, useEffect, useMemo, useState } from 'react';
import { ArtifactView, type ArtifactRef } from './ArtifactView';

/* THE COCKPIT — the V2 opening experience.
   Five agents ran. See what each produced, catch the wrong claim before it
   spreads, correct it once, and know the next run received the correction.
   ORIENT (this queue) -> INSPECT (native artifact) -> COMPARE (claim vs
   reality) -> RULE (keep/revise/reject) -> APPLY (receipt + undo) -> PROVE. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';

type Verdict = 'verified' | 'unverified' | 'contradicted';
type Claim = { kind: string; text: string; origin: string; verdict: Verdict; receipt: string; pair_key: string; ruled: boolean };
type Change = { commits: string[]; commit_count: number; files_changed: number; insertions: number; deletions: number; upstream: string; ahead: string; merged: boolean };
type Terminal = {
  terminal: string; repo: string; repo_path: string; branch: string; objective: string;
  change: Change; artifacts: ArtifactRef[]; claims: Claim[]; open_claim_count: number;
  needs_human: boolean; state: 'contradicted' | 'unverified' | 'clean';
};
type CockpitResp = { terminals: Terminal[]; needs_you: number; total: number; safe_set: string[] };

type Receipt = { ok: boolean; error?: string; finding_id?: number; decision?: string; correction_captured?: string; correction_cube?: string; continuity?: { included: boolean | null; note?: string; why?: string; context_size?: number }; receipt?: { applied: boolean; effect: string; detail: string }[] };
type Prop = { ok: boolean; sandbox_dir: string; files: Record<string, number>; corrections_written: number; contains_correction: boolean; real_target: string; gate: string; distinction: string };

const stateColor: Record<string, string> = {
  contradicted: 'var(--helicon-critical)',
  unverified: 'var(--helicon-stale)',
  clean: 'var(--helicon-good)',
};
const verdictLabel: Record<Verdict, string> = { contradicted: 'contradicted by reality', unverified: 'unverified', verified: 'verified' };

export default function Cockpit() {
  const [data, setData] = useState<CockpitResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [sel, setSel] = useState<string | null>(null);

  const load = useCallback(() => {
    fetch('/api/cockpit').then(r => r.json()).then((d: CockpitResp) => {
      setData(d);
      // Desktop two-pane opens the first terminal that needs you; the phone
      // lands on the queue itself (the ORIENT overview) and taps in.
      const isMobile = typeof window !== 'undefined' && window.matchMedia('(max-width: 767px)').matches;
      const firstPick = d.terminals.find(t => t.needs_human)?.terminal ?? d.terminals[0]?.terminal ?? null;
      setSel(prev => prev ?? (isMobile ? null : firstPick));
    }).catch(e => setErr(String(e)));
  }, []);
  useEffect(() => { load(); }, [load]);

  const selected = useMemo(() => data?.terminals.find(t => t.terminal === sel) || null, [data, sel]);

  if (err) return <Center>Could not reach the cockpit backend: {err}</Center>;
  if (!data) return <Center>Reading your terminals…</Center>;
  if (data.total === 0) return <Center>No recent agent runs found across your safe terminals. The board is clear.</Center>;

  return (
    <div className="max-w-6xl mx-auto">
      <Brief total={data.total} needs={data.needs_you} />
      <div className="md:flex md:gap-8 mt-6">
        {/* ORIENT — the queue */}
        <div className={`md:w-[320px] md:shrink-0 ${selected ? 'hidden md:block' : 'block'}`}>
          <div className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: MUTED }}>Every terminal · needs-you first</div>
          <div className="space-y-2">
            {data.terminals.map(t => (
              <TerminalRow key={t.terminal} t={t} active={t.terminal === sel} onClick={() => setSel(t.terminal)} />
            ))}
          </div>
        </div>
        {/* INSPECT + COMPARE + RULE */}
        <div className={`flex-1 min-w-0 ${selected ? 'block' : 'hidden md:block'}`}>
          {selected
            ? <Detail key={selected.terminal} t={selected} onBack={() => setSel(null)} onRuled={load} />
            : <Center>Select a terminal to review what it produced.</Center>}
        </div>
      </div>
    </div>
  );
}

function Brief({ total, needs }: { total: number; needs: number }) {
  return (
    <div className="border-b pb-5" style={{ borderColor: 'var(--helicon-line)' }}>
      <div className="text-[10px] uppercase tracking-[0.18em] mb-2" style={{ color: MUTED }}>The Cockpit</div>
      <h1 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[26px] md:text-[32px] leading-tight">
        {total} terminal{total === 1 ? '' : 's'} ran.{' '}
        {needs === 0
          ? <span style={{ color: 'var(--helicon-good)' }}>Nothing needs your ruling.</span>
          : <span style={{ color: INK }}>{needs} need{needs === 1 ? 's' : ''} your ruling.</span>}
      </h1>
      <p className="mt-2 text-[13px]" style={{ color: MUTED }}>
        What did each produce, what changed, which claim is unverified or wrong — and did the next run receive your correction.
      </p>
    </div>
  );
}

function TerminalRow({ t, active, onClick }: { t: Terminal; active: boolean; onClick: () => void }) {
  const open = t.claims.filter(c => !c.ruled);
  const bad = open.filter(c => c.verdict !== 'verified').length;
  return (
    <button onClick={onClick}
      className="w-full text-left p-3.5 rounded-xl transition-all hover:brightness-[0.99] active:scale-[0.995]"
      style={{ background: active ? 'var(--helicon-panel-2)' : 'var(--helicon-panel)', border: `1px solid ${active ? 'var(--helicon-line-2)' : 'var(--helicon-line)'}`, boxShadow: active ? 'var(--helicon-shadow-sm)' : 'none' }}>
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full shrink-0" style={{ background: stateColor[t.state] }} />
        <span className="text-[14px] font-medium truncate" style={{ color: INK, fontFamily: SERIF }}>{t.terminal}</span>
        {t.needs_human && <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded-full shrink-0" style={{ color: 'var(--helicon-on-dark)', background: ACCENT }}>needs you</span>}
      </div>
      <div className="mt-1 text-[11px] truncate" style={{ color: FAINT, fontFamily: MONO }}>{t.repo} · {t.branch}</div>
      <div className="mt-1.5 text-[12.5px] leading-snug line-clamp-2" style={{ color: MUTED }}>{t.objective}</div>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10.5px]" style={{ color: FAINT, fontFamily: MONO }}>
        <span>{t.change.commit_count} commit{t.change.commit_count === 1 ? '' : 's'}</span>
        {(t.change.insertions > 0 || t.change.deletions > 0) && <span>+{t.change.insertions} −{t.change.deletions}</span>}
        <span>{bad > 0 ? `${bad} to check` : `${open.length} claim${open.length === 1 ? '' : 's'}`}</span>
      </div>
    </button>
  );
}

function Detail({ t, onBack, onRuled }: { t: Terminal; onBack: () => void; onRuled: () => void }) {
  const [art, setArt] = useState<ArtifactRef | null>(t.artifacts[0] || null);
  useEffect(() => { setArt(t.artifacts[0] || null); }, [t.terminal]);
  const open = t.claims.filter(c => !c.ruled);

  return (
    <div className="animate-fade-in">
      <button onClick={onBack} className="md:hidden text-[12px] mb-3" style={{ color: ACCENT }}>← all terminals</button>
      <div className="flex items-start gap-2.5">
        <span className="w-2.5 h-2.5 rounded-full mt-1.5 shrink-0" style={{ background: stateColor[t.state] }} />
        <div className="min-w-0">
          <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[22px] md:text-[26px] leading-snug">{t.objective}</h2>
          <div className="mt-1 text-[11.5px]" style={{ color: FAINT, fontFamily: MONO }}>
            {t.terminal} · {t.repo} · {t.branch}
            {t.change.upstream ? '' : ' · no upstream (local only)'}
            {t.change.merged ? ' · merged' : ''}
          </div>
        </div>
      </div>

      {/* INSPECT — the artifact is the visual center */}
      <section className="mt-6">
        <div className="flex items-center gap-2 mb-2.5 flex-wrap">
          <div className="text-[10px] uppercase tracking-[0.16em]" style={{ color: MUTED }}>Inspect what it produced</div>
          <div className="flex gap-1.5 ml-auto">
            {t.artifacts.map(a => (
              <button key={a.type + a.ref} onClick={() => setArt(a)}
                className="text-[11px] px-2.5 py-1 rounded-lg transition-colors"
                style={{ color: art?.ref === a.ref ? 'var(--helicon-on-dark)' : MUTED, background: art?.ref === a.ref ? ACCENT : 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', fontFamily: MONO }}>
                {a.label}
              </button>
            ))}
          </div>
        </div>
        <div className="p-4 rounded-xl overflow-hidden" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', minHeight: 120, maxHeight: 460, overflowY: 'auto' }}>
          {art ? <ArtifactView repoPath={t.repo_path} art={art} /> : <p className="text-[12.5px]" style={{ color: FAINT }}>No inspectable artifact for this terminal.</p>}
        </div>
        {art?.note && <p className="mt-1.5 text-[10.5px]" style={{ color: FAINT }}>{art.note}</p>}
      </section>

      {/* COMPARE + RULE */}
      <section className="mt-8">
        <div className="text-[10px] uppercase tracking-[0.16em] mb-3" style={{ color: MUTED }}>The claim beside reality</div>
        {open.length === 0
          ? <p className="text-[13.5px] py-3" style={{ color: 'var(--helicon-good)' }}>Every claim this terminal made is verified against git. Nothing to rule.</p>
          : <div className="space-y-3">{open.map((c, i) => <ClaimCard key={c.pair_key + i} t={t} claim={c} onRuled={onRuled} />)}</div>}
      </section>
    </div>
  );
}

function ClaimCard({ t, claim, onRuled }: { t: Terminal; claim: Claim; onRuled: () => void }) {
  const [stage, setStage] = useState<'idle' | 'revise' | 'busy' | 'done'>('idle');
  const [correction, setCorrection] = useState('');
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [undone, setUndone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [prop, setProp] = useState<Prop | null>(null);
  const [propBusy, setPropBusy] = useState(false);
  const vcolor = claim.verdict === 'contradicted' ? 'var(--helicon-critical)' : claim.verdict === 'unverified' ? 'var(--helicon-stale)' : 'var(--helicon-good)';

  const rule = async (decision: 'keep' | 'revise' | 'reject', text = '') => {
    setStage('busy'); setError(null);
    try {
      const r: Receipt = await fetch('/api/cockpit/rule', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ terminal: t.terminal, pair_key: claim.pair_key, decision, correction: text }),
      }).then(x => x.json());
      if (!r.ok) { setError(r.error || 'ruling failed'); setStage(decision === 'revise' ? 'revise' : 'idle'); return; }
      setReceipt(r); setStage('done');
    } catch (e) { setError(e instanceof Error ? e.message : 'ruling failed — nothing written'); setStage('idle'); }
  };
  const undo = async () => {
    if (!receipt?.finding_id) return;
    const r = await fetch('/api/cockpit/undo', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ finding_id: receipt.finding_id }) }).then(x => x.json()).catch(() => ({ ok: false }));
    if (r.ok) setUndone(true); else setError(r.error || 'undo failed — the ruling is still applied');
  };
  const propagate = async () => {
    setPropBusy(true);
    try {
      const p: Prop = await fetch('/api/cockpit/propagate', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ correction_cube: receipt?.correction_cube || '' }) }).then(x => x.json());
      setProp(p);
    } finally { setPropBusy(false); }
  };

  if (stage === 'done' && receipt) {
    return (
      <div className="p-4 rounded-xl animate-fade-in" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line-2)' }}>
        <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[19px] leading-tight">
          {undone ? 'Reversed.' : receipt.decision === 'revise' ? 'Corrected once.' : receipt.decision === 'reject' ? 'Rejected.' : 'Kept.'}
        </div>
        {!undone && receipt.correction_captured && (
          <p className="mt-1.5 text-[12.5px] leading-relaxed pl-3" style={{ color: INK, borderLeft: '2px solid var(--helicon-line-2)' }}>“{receipt.correction_captured}”</p>
        )}
        {!undone && (
          <div className="mt-3 text-[11.5px] leading-relaxed" style={{ color: MUTED }}>
            {receipt.receipt?.map((r, i) => <div key={i}>✓ {r.detail}</div>)}
            {receipt.correction_cube && (
              <div className="mt-3 pt-3" style={{ borderTop: '1px solid var(--helicon-line)' }}>
                {!prop ? (
                  <>
                    <div className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>Prove the next run receives it</div>
                    <button disabled={propBusy} onClick={propagate}
                      className="px-3.5 py-1.5 rounded-lg text-[12px] font-medium disabled:opacity-40"
                      style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>
                      {propBusy ? 'Propagating…' : 'Send to agent context →'}
                    </button>
                  </>
                ) : (
                  <div className="animate-fade-in">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[10px] px-1.5 py-0.5 rounded-full" style={{ color: 'var(--helicon-on-dark)', background: prop.contains_correction ? 'var(--helicon-good)' : FAINT }}>
                        {prop.contains_correction ? '● staged into the next agent’s context files' : '○ not found in context files'}
                      </span>
                      <span className="text-[10px]" style={{ color: FAINT, fontFamily: MONO }}>{Object.keys(prop.files).length} files written</span>
                    </div>
                    <p className="mt-1.5 text-[10.5px] leading-relaxed" style={{ color: FAINT }}>{prop.distinction}</p>
                    <p className="mt-1 text-[10.5px] leading-relaxed" style={{ color: FAINT }}>Written to a sandbox — your live <span style={{ fontFamily: MONO }}>~/.claude/skills</span> stays untouched until you approve it.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
        <div className="mt-4 flex items-center gap-3">
          <button onClick={onRuled} className="px-4 py-2 rounded-lg text-[13px] font-medium" style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Next</button>
          {!undone && <button onClick={undo} className="text-[12.5px] hover:opacity-70" style={{ color: MUTED }}>Undo</button>}
        </div>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-xl" style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)' }}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-[9.5px] uppercase tracking-[0.14em] px-1.5 py-0.5 rounded" style={{ color: vcolor, border: `1px solid ${vcolor}`, opacity: 0.9 }}>{verdictLabel[claim.verdict]}</span>
        <span className="text-[10px]" style={{ color: FAINT, fontFamily: MONO }}>{claim.kind} · from {claim.origin}</span>
      </div>
      <p className="text-[13.5px] leading-relaxed" style={{ color: INK }}>{claim.text}</p>
      <div className="mt-2 flex items-start gap-1.5">
        <span className="text-[11px] shrink-0 mt-0.5" style={{ color: FAINT }}>reality:</span>
        <p className="text-[12px] leading-relaxed" style={{ color: MUTED, fontFamily: MONO }}>{claim.receipt}</p>
      </div>

      {stage === 'revise' ? (
        <div className="mt-3.5">
          <p className="text-[12px] mb-1.5" style={{ color: INK, fontWeight: 600 }}>What is actually true? Your words become the correction the next agent reads.</p>
          <textarea autoFocus rows={2} value={correction} onChange={e => setCorrection(e.target.value)}
            placeholder="e.g. the branch was never pushed; it is local-only, not in production"
            className="w-full px-3 py-2 rounded-lg text-[13.5px] leading-relaxed outline-none resize-y"
            style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)', minHeight: 60 }} />
          <div className="mt-2.5 flex items-center gap-2.5">
            <button disabled={!correction.trim()} onClick={() => rule('revise', correction.trim())}
              className="px-4 py-2 rounded-lg text-[13px] font-medium disabled:opacity-40" style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Correct it once</button>
            <button onClick={() => setStage('idle')} className="text-[12.5px] hover:opacity-70" style={{ color: MUTED }}>Back</button>
          </div>
        </div>
      ) : (
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          <button disabled={stage === 'busy'} onClick={() => rule('keep', 'verified against reality')}
            className="px-3.5 py-1.5 rounded-lg text-[12.5px] bg-white disabled:opacity-40" style={{ border: '1px solid var(--helicon-line-2)', color: INK }}>Keep — it's true</button>
          <button disabled={stage === 'busy'} onClick={() => setStage('revise')}
            className="px-3.5 py-1.5 rounded-lg text-[12.5px] font-medium disabled:opacity-40" style={{ color: 'var(--helicon-on-dark)', backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Revise — correct it</button>
          <button disabled={stage === 'busy'} onClick={() => rule('reject', 'claim is false')}
            className="px-3.5 py-1.5 rounded-lg text-[12.5px] bg-white disabled:opacity-40" style={{ border: '1px solid var(--helicon-line-2)', color: 'var(--helicon-critical)' }}>Reject</button>
          {stage === 'busy' && <span className="text-[12px]" style={{ color: FAINT }}>applying…</span>}
        </div>
      )}
      {error && <p className="mt-2.5 text-[12px] px-3 py-2 rounded-lg" style={{ color: 'var(--helicon-critical)', background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>{error} — nothing was written.</p>}
    </div>
  );
}

function Center({ children }: { children: React.ReactNode }) {
  return <div className="py-24 text-center text-[13px] max-w-md mx-auto leading-relaxed" style={{ color: MUTED }}>{children}</div>;
}
