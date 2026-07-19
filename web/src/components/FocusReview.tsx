import { useState, useMemo } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse, GovernReceipt } from '../api';

/* Govern by exception, one tap. A finding, its evidence, your ruling — and it
   applies immediately: propagated into the law, enforced by the guard, with a
   receipt that proves it and one Undo. No staging, no batch screen: ruling one
   confusion is one action, not three. */

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
  const queue = useMemo(() =>
    (data?.findings || [])
      .filter(f => f.lane === 'decision')
      .sort((a, b) => (SEV[a.severity] ?? 9) - (SEV[b.severity] ?? 9)),
    [data]);

  const [i, setI] = useState(0);
  const [applying, setApplying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<GovernReceipt | null>(null);
  const [undone, setUndone] = useState(false);
  const [reasoning, setReasoning] = useState(false);
  const [reasonText, setReasonText] = useState('');

  if (!data) return <div className="py-24 text-center text-[13px]" style={{ color: MUTED }}>…</div>;

  const advance = () => { setReceipt(null); setUndone(false); setReasoning(false); setReasonText(''); setError(null); setI(x => x + 1); };

  // ---- the receipt (immediately after a ruling applies) ---------------------
  if (receipt) {
    return <ReceiptView receipt={receipt} undone={undone}
      onUndo={() => api.undoBatch(receipt.undo_token).then(() => setUndone(true))}
      onDone={() => { receipt.receipt.filter(r => r.applied).forEach(r => onActed({ id: `audit-${r.finding_id}` } as Finding)); advance(); }} />;
  }

  const done = queue.length === 0 || i >= queue.length;
  const ambient = data?.summary?.ambient ?? 0;
  if (done) {
    return (
      <div className="max-w-lg mx-auto py-24 text-center animate-fade-in">
        <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[30px] leading-tight">
          The record is settled.
        </div>
        <p className="mt-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
          Nothing needs your ruling.{ambient > 0 ? ` ${ambient} aging findings are auto-managed, no action needed.` : ''}
        </p>
        <button onClick={onSeeAll} className="mt-7 text-[13px] transition-colors hover:opacity-70" style={{ color: ACCENT }}>
          See all findings →
        </button>
      </div>
    );
  }

  const f = queue[i];
  const auditId = f.id.startsWith('audit-') ? parseInt(f.id.slice(6), 10) : NaN;
  const sa = f.suggested_action;

  // One ruling, applied immediately: rule → propagate → enforce → receipt.
  const applyNow = async (verb: string, payload: Record<string, unknown>) => {
    if (Number.isNaN(auditId)) return advance();
    setApplying(true); setError(null);
    try {
      const r = await api.applyBatch([{ finding_id: auditId, verb, payload }]);
      setReceipt(r); setUndone(false);
    } catch (e) {
      // The API threw — nothing was written. Say so; never a frozen screen.
      setError(e instanceof Error ? e.message : 'Ruling failed — nothing was written.');
    } finally { setApplying(false); }
  };
  const skip = () => advance();
  const busy = applying;

  return (
    <div className="max-w-xl mx-auto">
      <div className="flex items-center gap-2.5 md:gap-3 mb-8 md:mb-12">
        <span className="tabular-nums text-[13px] shrink-0" style={{ color: INK, fontFamily: MONO }}>
          {i + 1}<span style={{ color: FAINT }}> / {queue.length}</span>
        </span>
        <div className="h-[3px] w-16 md:w-28 rounded-full overflow-hidden shrink-0" style={{ background: MIST }}>
          <div className="h-full rounded-full" style={{ width: `${(i / queue.length) * 100}%`, background: ACCENT, transition: 'width 300ms ease-out' }} />
        </div>
        <button onClick={onSeeAll} className="ml-auto text-[12px] transition-colors hover:opacity-70 shrink-0" style={{ color: MUTED }}>see all →</button>
      </div>

      <div key={f.id} className="animate-fade-in">
        <div className="text-[10px] uppercase tracking-[0.15em] mb-3 md:mb-4" style={{ color: sevColor(f.severity) }}>
          {f.severity} · {(f.kind || '').replace(/_/g, ' ')}
        </div>
        {(() => {
          const why = f.why || '';
          const q = why.indexOf('?');
          const question = q >= 0 ? why.slice(0, q + 1) : why;
          const consequence = q >= 0 ? why.slice(q + 1).trim() : '';
          return (
            <>
              <div className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>The question</div>
              <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[20px] md:text-[25px] leading-snug break-words">
                {question}
              </h2>
              {consequence && (
                <>
                  <div className="text-[10px] uppercase tracking-[0.16em] mt-6 md:mt-7 mb-2" style={{ color: MUTED }}>If you get it wrong</div>
                  <p className="text-[14px] md:text-[15px] leading-relaxed break-words" style={{ color: INK }}>{consequence}</p>
                </>
              )}
            </>
          );
        })()}

        {f.evidence_preview && <Receipt text={f.evidence_preview} src={`${f.source || ''}${f.source_ref ? ' · ' + f.source_ref : ''}`} />}

        <div className="mt-7 md:mt-9">
          {reasoning ? (
            <ReasonStage value={reasonText} onChange={setReasonText}
              onApply={() => applyNow('precedent', { reason: reasonText.trim() })}
              busy={busy} onCancel={() => { setReasoning(false); setReasonText(''); }} />
          ) : sa === 'rule_truth' && f.options && f.options.length >= 2 ? (
            <div>
              <p className="text-[12px] mb-2.5" style={{ color: MUTED }}>Which is current? One tap rules it and enforces it.</p>
              <div className="flex flex-wrap gap-2.5">
                {f.options.map(opt => (
                  <Primary key={opt} disabled={busy} onClick={() => applyNow('rule_truth', { truth: opt })}>It&apos;s: {opt}</Primary>
                ))}
                <Later onClick={skip} />
              </div>
            </div>
          ) : sa === 'rule_truth' ? (
            <TruthStage busy={busy} onApply={(t) => applyNow('rule_truth', { truth: t })} onSkip={skip} />
          ) : sa === 'resolve_identity' ? (
            <IdentityStage busy={busy} onApply={(c) => applyNow('rule_identity', { canonical: c })} onSkip={skip} />
          ) : sa === 'resolve_relation' ? (
            <div className="flex flex-wrap gap-2.5">
              <Primary disabled={busy} onClick={() => applyNow('resolve_relation', { verdict: 'phantom' })}>Confirm phantom</Primary>
              <Ghost disabled={busy} onClick={() => applyNow('resolve_relation', { verdict: 'real' })}>It&apos;s real</Ghost>
              <Later onClick={skip} />
            </div>
          ) : (sa === 'fix_skill' || sa === 'reconcile') ? (
            <div className="flex flex-wrap gap-2.5">
              <Primary disabled={busy} onClick={() => setReasoning(true)}>Rule it</Primary>
              <Later onClick={skip} />
            </div>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              <Primary disabled={busy} onClick={() => setReasoning(true)}>Keep (rule why)</Primary>
              <Ghost disabled={busy} onClick={() => applyNow('confirm', { decision: 'acted' })}>Retire</Ghost>
              <Later onClick={skip} />
            </div>
          )}
          {error && (
            <p className="mt-4 text-[12.5px] leading-relaxed px-3 py-2 rounded-lg"
              style={{ color: 'var(--helicon-critical)', background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
              {error} Your ruling wasn't written — try again.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

function ReceiptView({ receipt, undone, onUndo, onDone }: {
  receipt: GovernReceipt; undone: boolean; onUndo: () => Promise<void>; onDone: () => void;
}) {
  const [undoing, setUndoing] = useState(false);
  const [undoErr, setUndoErr] = useState<string | null>(null);
  const enforced = receipt.receipt.some(r => r.verify?.guard_blocks_the_wrong_claim);
  return (
    <div className="max-w-xl mx-auto animate-fade-in">
      <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[24px] leading-tight mb-1">
        {undone ? 'Reversed.' : enforced ? 'Ruled and enforced.' : 'Ruled.'}
      </div>
      <p className="text-[12.5px] mb-6" style={{ color: MUTED }}>
        {undone ? 'The ruling was undone; the record is back to before.'
          : 'Compiled into the law your agent reads before it writes.'}
      </p>
      <div className="space-y-2.5">
        {receipt.receipt.map((r, k) => (
          <div key={k} className="p-3 rounded-lg" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
            <div className="flex items-start gap-2.5">
              <span className="mt-0.5 text-[14px]" style={{ color: r.applied ? ACCENT : 'var(--helicon-critical)' }}>{r.applied ? '✓' : '✗'}</span>
              <div className="min-w-0 flex-1">
                <p className="text-[13px] leading-snug" style={{ color: INK }}>{r.effect}</p>
                {r.applied && <p className="text-[11.5px] mt-1 leading-relaxed" style={{ color: MUTED }}>{r.protection}</p>}
                {r.applied && (
                  <div className="flex flex-wrap gap-3 mt-1.5 text-[10px]" style={{ color: FAINT }}>
                    <span>{r.verify.recorded_in_audit_log ? '● recorded' : '○ not recorded'}</span>
                    <span>{r.verify.compiled_into_law ? '● in GOLDEN_RULES' : '○ queue-only'}</span>
                    {r.verify.guard_blocks_the_wrong_claim !== undefined && (
                      <span style={{ color: r.verify.guard_blocks_the_wrong_claim ? ACCENT : FAINT, fontWeight: 600 }}>
                        {r.verify.guard_blocks_the_wrong_claim ? '● guard now enforces it' : '○ not enforced'}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
      <div className="mt-7 flex items-center gap-3">
        <button onClick={onDone} className="px-5 py-2.5 rounded-lg text-[14px] font-medium text-[#F4EFE7] transition-all hover:brightness-110"
          style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Next</button>
        {!undone && (
          <button onClick={async () => { setUndoing(true); setUndoErr(null); try { await onUndo(); } catch (e) { setUndoErr(e instanceof Error ? e.message : 'undo failed'); } finally { setUndoing(false); } }}
            disabled={undoing} className="text-[13px] transition-colors hover:opacity-70 disabled:opacity-40" style={{ color: MUTED }}>
            {undoing ? 'Undoing…' : undoErr ? 'Retry undo' : 'Undo'}
          </button>
        )}
      </div>
      {undoErr && <p className="mt-3 text-[12px]" style={{ color: 'var(--helicon-critical)' }}>Undo failed: {undoErr} — the ruling is still applied.</p>}
    </div>
  );
}

function ReasonStage({ value, onChange, onApply, onCancel, busy }: {
  value: string; onChange: (v: string) => void; onApply: () => void; onCancel: () => void; busy: boolean;
}) {
  return (
    <div className="w-full animate-fade-in">
      <p className="text-[13px]" style={{ color: INK, fontWeight: 600 }}>Why does this stand? Your reason becomes law.</p>
      <textarea value={value} onChange={e => onChange(e.target.value)} autoFocus rows={3}
        placeholder="e.g. the branch is merged; the unmerged claims predate the merge"
        className="mt-2.5 w-full px-3 py-2.5 rounded-lg text-[14px] leading-relaxed outline-none resize-y"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)', minHeight: 72 }} />
      <div className="mt-3 flex items-center gap-2.5">
        <Primary onClick={onApply} disabled={busy || !value.trim()}>{busy ? 'Applying…' : 'Rule it'}</Primary>
        <button onClick={onCancel} className="text-[13px] transition-colors hover:opacity-70" style={{ color: MUTED }}>Back</button>
      </div>
    </div>
  );
}

function TruthStage({ onApply, onSkip, busy }: { onApply: (truth: string) => void; onSkip: () => void; busy: boolean }) {
  const [truth, setTruth] = useState('');
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <input value={truth} onChange={e => setTruth(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && truth.trim()) onApply(truth.trim()); }}
        placeholder="the current truth… e.g. eats chicken"
        className="px-3 py-2 rounded-lg text-[13px] outline-none w-64"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
      <Primary onClick={() => truth.trim() && onApply(truth.trim())} disabled={busy || !truth.trim()}>{busy ? 'Applying…' : 'Rule it'}</Primary>
      <Later onClick={onSkip} />
    </div>
  );
}

function IdentityStage({ onApply, onSkip, busy }: { onApply: (canonical: string) => void; onSkip: () => void; busy: boolean }) {
  const [canon, setCanon] = useState('');
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <input value={canon} onChange={e => setCanon(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && canon.trim()) onApply(canon.trim()); }}
        placeholder="the canonical definition…"
        className="px-3 py-2 rounded-lg text-[13px] outline-none w-64"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
      <Primary onClick={() => canon.trim() && onApply(canon.trim())} disabled={busy || !canon.trim()}>{busy ? 'Applying…' : 'Rule it'}</Primary>
      <Later onClick={onSkip} />
    </div>
  );
}

function Receipt({ text, src }: { text: string; src: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5">
      <button onClick={() => setOpen(o => !o)} className="text-[12px] transition-colors hover:opacity-70" style={{ color: ACCENT }}>
        {open ? 'hide the evidence' : 'show the evidence'}
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
