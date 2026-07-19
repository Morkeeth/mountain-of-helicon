import { useState, useMemo } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse, GovernReceipt } from '../api';

/* Govern by exception, one batch. You rule findings fast — each verdict STAGES,
   nothing is written yet — then apply the whole batch once and get a receipt that
   proves each ruling landed, with a single undo. The wall of findings collapses
   into: rule three things, apply once, trust it propagated. */

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

interface Staged {
  key: string;
  finding_id: number;
  verb: string;
  payload: Record<string, unknown>;
  why: string;
  effect: string;   // plain-language preview of what this ruling does
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
  const [batch, setBatch] = useState<Staged[]>([]);
  const [view, setView] = useState<'review' | 'batch' | 'receipt'>('review');
  const [reasonText, setReasonText] = useState('');
  const [reasoning, setReasoning] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [receipt, setReceipt] = useState<GovernReceipt | null>(null);
  const [undone, setUndone] = useState(false);

  const ambient = data?.summary?.ambient ?? 0;

  if (!data) return <div className="py-24 text-center text-[13px]" style={{ color: MUTED }}>…</div>;

  // ---- the receipt (after Apply) --------------------------------------------
  if (view === 'receipt' && receipt) {
    return <ReceiptView receipt={receipt} undone={undone}
      onUndo={() => api.undoBatch(receipt.undo_token).then(() => setUndone(true))}
      onDone={() => {
        // Only drop findings that ACTUALLY applied. Removing a failed ruling
        // optimistically would diverge the queue from the server — a stale-UI-vs-
        // reality gap the operator would otherwise catch by comparing two surfaces.
        receipt.receipt.filter(r => r.applied).forEach(r => onActed({ id: `audit-${r.finding_id}` } as Finding));
        onSeeAll();
      }} />;
  }

  // ---- the batch review (the one object you Apply) --------------------------
  if (view === 'batch') {
    return (
      <BatchReview batch={batch} applying={applying} error={applyError}
        onRemove={k => setBatch(b => b.filter(s => s.key !== k))}
        onBack={() => { setApplyError(null); setView('review'); }}
        onApply={async () => {
          setApplying(true); setApplyError(null);
          try {
            const r = await api.applyBatch(batch.map(s => ({ finding_id: s.finding_id, verb: s.verb, payload: s.payload })));
            setReceipt(r); setUndone(false); setView('receipt');
          } catch (e) {
            // The API threw — nothing was written. Say so precisely; never leave the
            // operator to infer from a frozen screen whether the batch applied.
            setApplyError(e instanceof Error ? e.message : 'Apply failed — nothing was written.');
          } finally { setApplying(false); }
        }} />
    );
  }

  const done = queue.length === 0 || i >= queue.length;

  // Staging a verdict + advancing. Nothing is written until Apply.
  const stage = (verb: string, payload: Record<string, unknown>, effect: string) => {
    const f = queue[i];
    const auditId = f.id.startsWith('audit-') ? parseInt(f.id.slice(6), 10) : NaN;
    if (!Number.isNaN(auditId)) {
      setBatch(b => [...b, { key: `${f.id}-${b.length}`, finding_id: auditId, verb, payload, why: f.why, effect }]);
    }
    setReasoning(false); setReasonText('');
    setI(x => x + 1);
  };
  const skip = () => { setReasoning(false); setReasonText(''); setI(x => x + 1); };

  // ---- the empty / all-reviewed state ---------------------------------------
  if (done) {
    return (
      <div className="max-w-lg mx-auto py-20 text-center animate-fade-in">
        {batch.length > 0 ? (
          <>
            <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[26px] leading-tight">
              {batch.length} ruling{batch.length > 1 ? 's' : ''} staged.
            </div>
            <p className="mt-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
              Nothing is written yet. Review them as one, then apply once.
            </p>
            <button onClick={() => setView('batch')} className="mt-6 px-5 py-2.5 rounded-lg text-[14px] font-medium text-[#F4EFE7]"
              style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>
              Review &amp; apply {batch.length} →
            </button>
          </>
        ) : (
          <>
            <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[30px] leading-tight">
              The record is settled.
            </div>
            <p className="mt-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
              Nothing needs your ruling.{ambient > 0 ? ` ${ambient} aging findings are auto-managed, no action needed.` : ''}
            </p>
            <button onClick={onSeeAll} className="mt-7 text-[13px] transition-colors hover:opacity-70" style={{ color: ACCENT }}>
              See all findings →
            </button>
          </>
        )}
      </div>
    );
  }

  const f = queue[i];
  const sa = f.suggested_action;

  return (
    <div className="max-w-xl mx-auto">
      {/* progress + staged count */}
      <div className="flex items-center justify-between gap-3 mb-8 md:mb-12">
        <div className="flex items-center gap-2.5 md:gap-3 min-w-0">
          <span className="tabular-nums text-[13px] shrink-0" style={{ color: INK, fontFamily: MONO }}>
            {i + 1}<span style={{ color: FAINT }}> / {queue.length}</span>
          </span>
          <div className="h-[3px] w-16 md:w-28 rounded-full overflow-hidden shrink-0" style={{ background: MIST }}>
            <div className="h-full rounded-full" style={{ width: `${(i / queue.length) * 100}%`, background: ACCENT, transition: 'width 300ms ease-out' }} />
          </div>
        </div>
        {batch.length > 0 && (
          <button onClick={() => setView('batch')} className="text-[12px] transition-colors hover:opacity-80 shrink-0"
            style={{ color: ACCENT, fontWeight: 600 }}>
            {batch.length} staged · Review &amp; apply →
          </button>
        )}
      </div>

      {/* the one thing */}
      <div key={f.id} className="animate-fade-in">
        <div className="text-[10px] uppercase tracking-[0.15em] mb-3 md:mb-4" style={{ color: sevColor(f.severity) }}>
          {f.severity} · {(f.kind || '').replace(/_/g, ' ')}
        </div>
        <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[19px] md:text-[23px] leading-snug break-words">
          {f.why}
        </h2>
        <p className="mt-2.5 text-[12.5px] md:text-[13px] break-words" style={{ color: MUTED }}>{f.title}</p>

        {f.evidence_preview && <Receipt text={f.evidence_preview} src={`${f.source || ''}${f.source_ref ? ' · ' + f.source_ref : ''}`} />}

        <div className="mt-7 md:mt-9">
          {reasoning ? (
            <ReasonStage value={reasonText} onChange={setReasonText}
              onStage={() => stage('precedent', { reason: reasonText.trim() }, `ruled not-rot: ${reasonText.trim().slice(0, 60)}`)}
              onCancel={() => { setReasoning(false); setReasonText(''); }} />
          ) : sa === 'rule_truth' ? (
            <TruthStage onStage={(t) => stage('rule_truth', { truth: t }, `ruled current: ${t} — the other value becomes enforceable-wrong`)} onSkip={skip} />
          ) : sa === 'resolve_identity' ? (
            <IdentityStage onStage={(canon) => stage('rule_identity', { canonical: canon }, `'${entityOf(f)}' ruled: ${canon}`)} onSkip={skip} />
          ) : sa === 'resolve_relation' ? (
            <div className="flex flex-wrap gap-2.5">
              <Primary onClick={() => stage('resolve_relation', { verdict: 'phantom' }, `'${entityOf(f)}' relation ruled ungrounded`)}>Confirm phantom</Primary>
              <Ghost onClick={() => stage('resolve_relation', { verdict: 'real' }, `'${entityOf(f)}' relation ruled real`)}>It&apos;s real</Ghost>
              <Later onClick={skip} />
            </div>
          ) : (sa === 'fix_skill' || sa === 'reconcile') ? (
            <div className="flex flex-wrap gap-2.5">
              <Primary onClick={() => setReasoning(true)}>Rule it</Primary>
              <Later onClick={skip} />
            </div>
          ) : sa === 'kill_stale' ? (
            <div className="flex flex-wrap gap-2.5">
              <Primary onClick={() => setReasoning(true)}>Keep (rule why)</Primary>
              <Ghost onClick={() => stage('confirm', { decision: 'acted' }, 'retired — acted on and closed')}>Retire</Ghost>
              <Later onClick={skip} />
            </div>
          ) : (
            <div className="flex flex-wrap gap-2.5">
              <Primary onClick={() => setReasoning(true)}>Keep (rule why)</Primary>
              <Ghost onClick={() => stage('confirm', { decision: 'acted' }, 'retired — acted on and closed')}>Retire</Ghost>
              <Later onClick={skip} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// The entity name for an effect preview, pulled from the finding text.
function entityOf(f: Finding): string {
  const m = (f.why || '').match(/'([^']+)'/);
  return m ? m[1] : 'this';
}

function BatchReview({ batch, applying, error, onApply, onBack, onRemove }: {
  batch: Staged[]; applying: boolean; error: string | null; onApply: () => void; onBack: () => void; onRemove: (k: string) => void;
}) {
  return (
    <div className="max-w-xl mx-auto animate-fade-in">
      <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[24px] leading-tight mb-1">
        Apply {batch.length} ruling{batch.length > 1 ? 's' : ''}
      </div>
      <p className="text-[12.5px] mb-6" style={{ color: MUTED }}>
        One action. Each becomes durable law your agent obeys next time — with an undo.
      </p>
      <div className="space-y-2.5">
        {batch.map(s => (
          <div key={s.key} className="flex items-start gap-3 p-3 rounded-lg" style={{ background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
            <span className="mt-0.5 text-[15px]" style={{ color: ACCENT }}>✓</span>
            <div className="min-w-0 flex-1">
              <p className="text-[13px] leading-snug" style={{ color: INK }}>{s.effect}</p>
              <p className="text-[11px] mt-0.5 truncate" style={{ color: FAINT }}>{s.why}</p>
            </div>
            <button onClick={() => onRemove(s.key)} className="text-[11px] shrink-0 transition-opacity hover:opacity-70" style={{ color: FAINT }}>remove</button>
          </div>
        ))}
      </div>
      {error && (
        <p className="mt-4 text-[12.5px] leading-relaxed px-3 py-2 rounded-lg"
          style={{ color: 'var(--helicon-critical)', background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
          Not applied: {error} — nothing was written; your staged rulings are intact. Retry.
        </p>
      )}
      <div className="mt-7 flex items-center gap-3">
        <button onClick={onApply} disabled={applying || batch.length === 0}
          className="px-5 py-2.5 rounded-lg text-[14px] font-medium text-[#F4EFE7] disabled:opacity-40 transition-all hover:brightness-110 active:scale-[0.98]"
          style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>
          {applying ? 'Applying…' : error ? `Retry · Apply ${batch.length}` : `Apply ${batch.length}`}
        </button>
        <button onClick={onBack} className="text-[13px] transition-colors hover:opacity-70" style={{ color: MUTED }}>Back</button>
      </div>
    </div>
  );
}

function ReceiptView({ receipt, undone, onUndo, onDone }: {
  receipt: GovernReceipt; undone: boolean; onUndo: () => Promise<void>; onDone: () => void;
}) {
  const [undoing, setUndoing] = useState(false);
  const [undoErr, setUndoErr] = useState<string | null>(null);
  return (
    <div className="max-w-xl mx-auto animate-fade-in">
      <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[24px] leading-tight mb-1">
        {undone ? 'Reversed.' : `Applied. ${receipt.applied} propagated${receipt.failed ? `, ${receipt.failed} held back` : ''}.`}
      </div>
      <p className="text-[12.5px] mb-6" style={{ color: MUTED }}>
        {undone ? 'The rulings were undone; the record is back to before.'
          : `${receipt.rules_compiled} compiled into the law your agent reads before it writes.`}
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
          style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>Done</button>
        {!undone && (
          <button onClick={async () => { setUndoing(true); setUndoErr(null); try { await onUndo(); } catch (e) { setUndoErr(e instanceof Error ? e.message : 'undo failed'); } finally { setUndoing(false); } }}
            disabled={undoing} className="text-[13px] transition-colors hover:opacity-70 disabled:opacity-40" style={{ color: MUTED }}>
            {undoing ? 'Undoing…' : undoErr ? 'Retry undo' : 'Undo all'}
          </button>
        )}
      </div>
      {undoErr && <p className="mt-3 text-[12px]" style={{ color: 'var(--helicon-critical)' }}>Undo failed: {undoErr} — the rulings are still applied.</p>}
    </div>
  );
}

function ReasonStage({ value, onChange, onStage, onCancel }: {
  value: string; onChange: (v: string) => void; onStage: () => void; onCancel: () => void;
}) {
  return (
    <div className="w-full animate-fade-in">
      <p className="text-[13px]" style={{ color: INK, fontWeight: 600 }}>Why does this stand? Your reason becomes law.</p>
      <textarea value={value} onChange={e => onChange(e.target.value)} autoFocus rows={3}
        placeholder="e.g. the branch is merged; the unmerged claims predate the merge"
        className="mt-2.5 w-full px-3 py-2.5 rounded-lg text-[14px] leading-relaxed outline-none resize-y"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)', minHeight: 72 }} />
      <div className="mt-3 flex items-center gap-2.5">
        <Primary onClick={onStage} disabled={!value.trim()}>Stage ruling</Primary>
        <button onClick={onCancel} className="text-[13px] transition-colors hover:opacity-70" style={{ color: MUTED }}>Back</button>
      </div>
    </div>
  );
}

function TruthStage({ onStage, onSkip }: { onStage: (truth: string) => void; onSkip: () => void }) {
  const [truth, setTruth] = useState('');
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <input value={truth} onChange={e => setTruth(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && truth.trim()) onStage(truth.trim()); }}
        placeholder="the current truth… e.g. eats chicken"
        className="px-3 py-2 rounded-lg text-[13px] outline-none w-64"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
      <Primary onClick={() => truth.trim() && onStage(truth.trim())} disabled={!truth.trim()}>Stage ruling</Primary>
      <Later onClick={onSkip} />
    </div>
  );
}

function IdentityStage({ onStage, onSkip }: { onStage: (canonical: string) => void; onSkip: () => void }) {
  const [canon, setCanon] = useState('');
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      <input value={canon} onChange={e => setCanon(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter' && canon.trim()) onStage(canon.trim()); }}
        placeholder="the canonical definition…"
        className="px-3 py-2 rounded-lg text-[13px] outline-none w-64"
        style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }} />
      <Primary onClick={() => canon.trim() && onStage(canon.trim())} disabled={!canon.trim()}>Stage ruling</Primary>
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
