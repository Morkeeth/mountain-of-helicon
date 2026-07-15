import { useState, useMemo } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse } from '../api';
import { PrecedentReason } from './PrecedentReason';

/* Zen review — one thing at a time. The wall of findings collapses into a single
   calm question: rule this, it advances, breathe. The full dashboard stays one
   click away ("see all"). Only what a human must rule on enters the queue; the
   aging pile is auto-managed and never shown here. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const MIST = 'var(--helicon-mist)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';

const SEV: Record<string, number> = { critical: 0, high: 1, warning: 2, medium: 3, info: 4 };
function sevColor(s: string) {
  return s === 'critical' || s === 'high' ? ACCENT : s === 'warning' || s === 'medium' ? 'var(--helicon-stale)' : FAINT;
}

export default function FocusReview({ data, onActed, onSeeAll }: {
  data: FindingsResponse | null;
  onActed: (f: Finding) => void;
  onSeeAll: () => void;
}) {
  /* The queue is the decision LANE, which is what this screen has always claimed
     to be ("the aging pile is auto-managed and never shown here") and what the
     header counts as needs_you. Filtering on severity instead pulled in all 298
     ambient rows because they are severity 'warning', so the queue read 1/312
     and "~156 min" of ruling against 19 real decisions, while dropping the
     'high'/'medium' decisions that the severity filter never named. Lane is the
     server's own split; severity only orders what is already yours to rule. */
  const queue = useMemo(() =>
    (data?.findings || [])
      .filter(f => f.lane === 'decision')
      .sort((a, b) => (SEV[a.severity] ?? 9) - (SEV[b.severity] ?? 9)),
    [data]);

  const [i, setI] = useState(0);
  const [acting, setActing] = useState(false);
  // 'reason' asks why before a dismissal, so the ruling can become a precedent
  const [step, setStep] = useState<'rule' | 'reason'>('rule');
  // set from the server's own answer, never assumed
  const [filed, setFiled] = useState<'precedent' | 'quiet' | null>(null);
  const ambient = data?.summary?.ambient ?? 0;
  const advance = (f?: Finding) => {
    if (f) onActed(f);
    setStep('rule');
    setI(x => x + 1);
  };

  if (!data) return <div className="py-24 text-center text-[13px]" style={{ color: MUTED }}>…</div>;

  if (queue.length === 0 || i >= queue.length) {
    return (
      <div className="max-w-lg mx-auto py-24 text-center animate-fade-in">
        <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[30px] leading-tight">
          The record is settled.
        </div>
        <p className="mt-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
          Nothing needs your ruling.{ambient > 0 ? ` ${ambient} aging findings are auto-managed, no action needed.` : ''}
        </p>
        <button onClick={onSeeAll} className="mt-7 text-[13px] transition-colors hover:opacity-70"
          style={{ color: ACCENT }}>See all findings →</button>
      </div>
    );
  }

  const f = queue[i];
  const auditId = f.id.startsWith('audit-') ? parseInt(f.id.slice(6), 10) : null;
  const confirmAudit = async (d: string) => {
    if (auditId === null) return advance(f);
    setActing(true);
    try { await api.confirmAudit(auditId, d); } finally { setActing(false); }
    advance(f);
  };
  const review = async (d: string) => {
    if (!f.cube_id) return advance(f);
    setActing(true);
    try { await api.submitReview(f.cube_id, d, `via focus: ${f.kind}`, 0); } finally { setActing(false); }
    advance(f);
  };
  const resolveRel = async (verdict: string) => {
    if (auditId === null) return advance(f);
    setActing(true);
    try { await api.resolveRelation(auditId, verdict); } finally { setActing(false); }
    advance(f);
  };

  /* A dismissal is the "not rot" verdict, and it only becomes law with a reason,
     so on an audit finding it routes through the reason step instead of posting
     bare. Cube reviews keep going straight through: their notes land in
     `reviews`, which gold.py never compiles, so pretending otherwise would
     promise law this path cannot write. */
  const askReason = auditId !== null && !f.cube_id;
  const pinned = step === 'rule' && !filed;

  return (
    <div className="max-w-xl mx-auto">
      {/* quiet progress + escape */}
      <div className="flex items-center justify-between gap-3 mb-8 md:mb-12">
        <div className="flex items-center gap-2.5 md:gap-3 min-w-0">
          <span className="tabular-nums text-[13px] shrink-0" style={{ color: INK, fontFamily: MONO }}>
            {i + 1}<span style={{ color: FAINT }}> / {queue.length}</span>
          </span>
          <div className="h-[3px] w-16 md:w-28 rounded-full overflow-hidden shrink-0" style={{ background: MIST }}>
            <div className="h-full rounded-full" style={{ width: `${(i / queue.length) * 100}%`, background: ACCENT, transition: 'width 300ms ease-out' }} />
          </div>
          <span className="text-[11px] whitespace-nowrap" style={{ color: FAINT }}>~{Math.max(1, Math.ceil((queue.length - i) * 0.5))} min</span>
        </div>
        <button onClick={onSeeAll} className="text-[12px] transition-colors hover:opacity-70 shrink-0 h-auto" style={{ color: MUTED }}>see all →</button>
      </div>

      {/* the one thing */}
      <div key={f.id} className="animate-fade-in">
        <div className="text-[10px] uppercase tracking-[0.15em] mb-3 md:mb-4" style={{ color: sevColor(f.severity) }}>
          {f.severity} · {(f.kind || '').replace(/_/g, ' ')}
        </div>
        {/* the finding leads, but a 23px serif paragraph filled a whole phone
            screen before the verdict was even in view */}
        <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[19px] md:text-[23px] leading-snug break-words">
          {f.why}
        </h2>
        <p className="mt-2.5 text-[12.5px] md:text-[13px] break-words" style={{ color: MUTED }}>{f.title}</p>

        {f.evidence_preview && <Receipt text={f.evidence_preview} src={`${f.source || ''}${f.source_ref ? ' · ' + f.source_ref : ''}`} />}

        {/* The verdict rides the bottom of the screen on a phone: a queue is a
            thumb loop, and hunting for the buttons under a long receipt is how
            a wrong ruling gets filed. Static from md up.

            Only the short button row pins. The reason step is taller than the
            space above the nav, and pinning it pushed "File as precedent" to
            y=859 in an 844px viewport: the primary action, off-screen, with the
            sticky container fighting the scroll that would reveal it. It flows
            and scrolls instead. */}
        <div
          className={`mt-7 md:mt-9 z-30 -mx-4 px-4 md:mx-0 md:px-0 pt-3 pb-3 md:pt-0 md:pb-0 ${pinned ? 'sticky md:static' : ''}`}
          style={pinned ? { bottom: 'calc(56px + env(safe-area-inset-bottom))' } : undefined}
        >
          {pinned && <div className="md:hidden absolute inset-0 -z-10" style={{ background: 'var(--helicon-bg)', borderTop: '1px solid var(--helicon-line)' }} />}
          {filed ? (
            <FiledNote kind={filed} onNext={() => { setFiled(null); advance(f); }} />
          ) : step === 'reason' && auditId !== null ? (
            <PrecedentReason
              auditId={auditId}
              findingWhy={f.why}
              onCancel={() => setStep('rule')}
              onFiled={precedent => { setFiled(precedent ? 'precedent' : 'quiet'); }}
            />
          ) : (
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-2.5 sm:flex-wrap">
            {f.suggested_action === 'fix_skill' ? (
              <><CmdChip cmd="helicon fix-skills --apply" /><Later onClick={() => advance(f)} /></>
            ) : f.suggested_action === 'reconcile' ? (
              <><CmdChip cmd="helicon reconcile --apply" /><Later onClick={() => advance(f)} /></>
            ) : f.suggested_action === 'kill_stale' && auditId !== null ? (
              <><Primary disabled={acting} onClick={() => (askReason ? setStep('reason') : confirmAudit('dismissed'))}>Keep</Primary>
                <Ghost disabled={acting} onClick={() => confirmAudit('acted')}>Retire</Ghost>
                <Later onClick={() => advance(f)} /></>
            ) : f.suggested_action === 'resolve_relation' && auditId !== null ? (
              <><Primary disabled={acting} onClick={() => resolveRel('phantom')}>Confirm phantom</Primary>
                <Ghost disabled={acting} onClick={() => resolveRel('real')}>It&apos;s real</Ghost></>
            ) : f.suggested_action === 'resolve_identity' && auditId !== null ? (
              <IdentityResolveFocus auditId={auditId} onDone={() => advance(f)} />
            ) : (
              <><Primary disabled={acting} onClick={() => (f.cube_id ? review('approved') : askReason ? setStep('reason') : confirmAudit('dismissed'))}>Confirm, still true</Primary>
                <Ghost disabled={acting} onClick={() => (f.cube_id ? review('killed') : confirmAudit('acted'))}>Retire</Ghost>
                <Later onClick={() => advance(f)} /></>
            )}
          </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* What the server actually did with the ruling. `precedent` comes back from
   /api/audit/confirm, so this reports law that exists rather than congratulating
   the operator on a write that may not have happened. */
function FiledNote({ kind, onNext }: { kind: 'precedent' | 'quiet'; onNext: () => void }) {
  return (
    <div className="animate-fade-in">
      <p className="text-[13px]" style={{ color: INK }}>
        {kind === 'precedent' ? 'Filed as precedent.' : 'Ruling recorded.'}
      </p>
      <p className="mt-1 text-[11.5px] leading-relaxed" style={{ color: MUTED }}>
        {kind === 'precedent'
          ? 'It compiles into GOLDEN_RULES on the next build, and this finding will not alarm again.'
          : 'Closed without a reason, so no rule was written.'}
      </p>
      <button
        onClick={onNext}
        className="mt-3 px-4 py-2.5 rounded-lg text-[13px] font-medium text-[#F4EFE7] transition-all hover:brightness-110 active:scale-[0.98] w-full sm:w-auto"
        style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)', minHeight: 44 }}
      >
        Next finding
      </button>
    </div>
  );
}

function Receipt({ text, src }: { text: string; src: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5">
      <button onClick={() => setOpen(o => !o)} className="text-[12px] transition-colors hover:opacity-70" style={{ color: ACCENT }}>
        {open ? 'hide the receipt' : 'show the receipt'}
      </button>
      {open && (
        <div className="mt-2.5 animate-fade-in">
          <pre className="text-[11px] p-3.5 rounded-lg whitespace-pre-wrap leading-relaxed max-h-52 overflow-auto"
            style={{ color: MUTED, background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>{text}</pre>
          {src && <p className="text-[10px] mt-1.5" style={{ color: FAINT }}>{src}</p>}
        </div>
      )}
    </div>
  );
}

function Primary({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="px-4 py-2 rounded-lg text-[13px] font-medium text-[#F4EFE7] transition-all hover:brightness-110 active:scale-95 disabled:opacity-40"
      style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>{children}</button>
  );
}
function Ghost({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="px-4 py-2 rounded-lg text-[13px] transition-all active:scale-95 disabled:opacity-40 bg-white"
      style={{ border: '1px solid var(--helicon-line-2)', color: INK }}>{children}</button>
  );
}
function Later({ onClick }: { onClick: () => void }) {
  return <button onClick={onClick} className="px-3 py-2 text-[13px] transition-colors hover:opacity-70" style={{ color: FAINT }}>Later</button>;
}
function CmdChip({ cmd }: { cmd: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard?.writeText(cmd); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
      className="px-3 py-2 rounded-lg text-[12px] transition-colors hover:opacity-80"
      style={{ fontFamily: MONO, color: INK, background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
      {copied ? 'copied ✓' : `${cmd}  ⧉`}
    </button>
  );
}


function IdentityResolveFocus({ auditId, onDone }: { auditId: number; onDone: () => void }) {
  const [canon, setCanon] = useState('');
  const [busy, setBusy] = useState(false);
  const resolve = async () => {
    if (!canon.trim()) return;
    setBusy(true);
    try { await api.resolveIdentity(auditId, canon.trim()); } finally { setBusy(false); }
    onDone();
  };
  const dismiss = async () => {
    setBusy(true);
    try { await api.confirmAudit(auditId, 'dismissed'); } finally { setBusy(false); }
    onDone();
  };
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <input value={canon} onChange={e => setCanon(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') resolve(); }}
        placeholder="the canonical definition…"
        className="px-3 py-2 rounded-lg text-[13px] outline-none w-64"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
      <Primary disabled={busy || !canon.trim()} onClick={resolve}>Set canonical</Primary>
      <Ghost disabled={busy} onClick={dismiss}>Not a fork</Ghost>
    </div>
  );
}
