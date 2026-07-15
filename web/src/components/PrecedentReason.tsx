import { useState } from 'react';
import { api } from '../api';

/* The reason step (Jul 15).

   A dismissal is Helicon's "this is not rot" verdict, and gold.py only emits a
   precedent for `human_decision == 'dismissed' AND details.dismiss_reason`
   (gold.py:182). The dashboard posted the decision and never the reason, so a
   ruling made here died in audit_log while the identical ruling from the CLI
   compiled into GOLDEN_RULES. The API now carries `notes` and answers
   `precedent: true` when a reason made law; this is the surface that finally
   sends one.

   So the reason is not a nicety to be skipped, it IS the law. This screen says
   what the reason buys before asking for it, and reports back what the server
   actually did rather than assuming it worked. */

// gold.py clips dismiss_reason at 140 chars on a word boundary. Say so here
// rather than let the compiler silently truncate the operator's sentence.
export const REASON_CLIP = 140;
// ...and the finding itself at 118 in the same rule.
const FINDING_CLIP = 118;

/* The compiled rule is "NOT rot: " + clip(audit_log.finding, 118), but the
   findings API hands us `why` as f"{check}: {finding}" (findings.py:132). The
   check name is prepended for the human sentence. Showing `why` verbatim would
   preview a rule with a prefix the compiler never writes, which is exactly the
   kind of small confident wrongness this whole app exists to catch. The check
   is always the first ": "-delimited segment, so drop it to recover the finding
   as gold.py will see it. Only ever called for audit-* findings, which is the
   branch that format comes from. */
function compiledRule(why: string): string {
  const cut = why.indexOf(': ');
  const finding = cut > -1 ? why.slice(cut + 2) : why;
  const flat = finding.split(/\s+/).join(' ');
  return flat.length <= FINDING_CLIP ? flat : flat.slice(0, FINDING_CLIP).replace(/\s\S*$/, '') + '…';
}

export interface PrecedentResult {
  finding_id: number;
  decision: string;
  precedent?: boolean;
}

export function PrecedentReason({ auditId, findingWhy, compact, onFiled, onCancel }: {
  auditId: number;
  findingWhy: string;
  compact?: boolean;
  onFiled: (precedent: boolean) => void;
  onCancel: () => void;
}) {
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const trimmed = reason.trim();
  const over = trimmed.length > REASON_CLIP;

  const file = async (withReason: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const res = await api.confirmAudit<PrecedentResult>(
        auditId, 'dismissed', withReason ? trimmed : undefined,
      );
      onFiled(res?.precedent === true);
    } catch (e) {
      // dismiss_finding refuses a finding that is already decided, and the
      // dashboard used to advance anyway, so the operator believed a ruling
      // landed that never did. Say it plainly and keep the finding on screen.
      setError(e instanceof Error ? e.message : 'could not file this ruling');
      setBusy(false);
    }
  };

  return (
    <div className={compact ? 'w-full' : 'w-full animate-fade-in'} onClick={e => e.stopPropagation()}>
      <p className="text-[13px]" style={{ color: 'var(--helicon-ink)', fontWeight: 600 }}>
        Why is this not rot?
      </p>
      <p className="mt-1 text-[12px] leading-relaxed" style={{ color: 'var(--helicon-muted)' }}>
        Your reason becomes law. Helicon files it under the precedents in GOLDEN_RULES, with a
        receipt, so this never alarms again. Rule without one and the finding closes quietly,
        compiling to nothing.
      </p>

      <textarea
        value={reason}
        onChange={e => setReason(e.target.value)}
        autoFocus
        rows={compact ? 2 : 3}
        placeholder="selector false positive: place-as-person, fixed same hour"
        className="mt-2.5 w-full px-3 py-2.5 rounded-lg text-[14px] leading-relaxed outline-none resize-y"
        style={{
          background: 'var(--helicon-panel-2)', color: 'var(--helicon-ink)',
          border: '1px solid var(--helicon-line)', minHeight: 72,
        }}
      />

      <div className="mt-1 flex items-baseline justify-between gap-2">
        <span className="text-[10.5px] tabular-nums" style={{ color: over ? 'var(--helicon-stale)' : 'var(--helicon-faint)' }}>
          {over
            ? `${trimmed.length}/${REASON_CLIP}, the compiled rule clips at ${REASON_CLIP}`
            : `${trimmed.length}/${REASON_CLIP}`}
        </span>
      </div>

      {/* What the finding becomes. The shape is gold.py's, so the operator can
          see the rule they are writing before they write it. */}
      {trimmed && (
        <div
          className="mt-2 px-3 py-2 rounded-lg animate-fade-in"
          style={{ background: 'var(--helicon-accent-dim)', border: '1px solid var(--helicon-line)' }}
        >
          <p className="text-[9.5px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-faint)' }}>
            Compiles to
          </p>
          <p className="mt-1 text-[11.5px] leading-relaxed" style={{ color: 'var(--helicon-ink)' }}>
            <b style={{ fontWeight: 600 }}>NOT rot:</b> {compiledRule(findingWhy)}
          </p>
          <p className="mt-0.5 text-[11.5px] italic leading-relaxed" style={{ color: 'var(--helicon-muted)' }}>
            why: {trimmed.slice(0, REASON_CLIP)}{over ? '…' : ''}
          </p>
        </div>
      )}

      {error && (
        <p className="mt-2 text-[11.5px]" style={{ color: 'var(--helicon-critical)' }}>
          Not filed: {error}
        </p>
      )}

      <div className="mt-3 flex flex-col sm:flex-row gap-2 sm:items-center">
        <button
          onClick={() => file(true)}
          disabled={busy || !trimmed}
          className="px-4 py-2.5 rounded-lg text-[13px] font-medium text-[#F4EFE7] transition-all hover:brightness-110 active:scale-[0.98] disabled:opacity-40 w-full sm:w-auto"
          style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)', minHeight: 44 }}
        >
          {busy ? 'Filing…' : 'File as precedent'}
        </button>
        <button
          onClick={onCancel}
          disabled={busy}
          className="px-3 py-2.5 text-[13px] transition-colors hover:opacity-70 disabled:opacity-40"
          style={{ color: 'var(--helicon-muted)', minHeight: 44 }}
        >
          Back
        </button>
        <button
          onClick={() => file(false)}
          disabled={busy}
          title="Closes the finding without writing a rule"
          className="sm:ml-auto px-3 py-2.5 text-[12px] transition-colors hover:opacity-70 disabled:opacity-40 text-left"
          style={{ color: 'var(--helicon-faint)', minHeight: 44 }}
        >
          Dismiss without a reason
        </button>
      </div>
    </div>
  );
}
