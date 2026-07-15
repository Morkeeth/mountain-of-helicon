import { useCallback, useEffect, useState } from 'react';
import { api, type RotCheck, type RotExam } from '../api';

/* THE EXAM — ROT.md as an executable test suite, rendered.
   Twelve named failure classes, each checked live against the real store, each
   verdict carrying the number it came from. This is the CLI's `helicon rot`
   with the same honesty contract, not a prettier summary of it:

   - UNMEASURED is not CLEAN. A gap gets its own verdict, its own colour and its
     own line in the headline. The one thing this surface may never do is let a
     class that was never checked read as a class that passed.
   - Every ROT FOUND names the next step. An exam that finds rot and names no
     move leaves the loop open, which is the failure the CLI just fixed.
   - The receipt is always visible. No hover, no drawer: the evidence sits under
     the verdict, because a verdict without its number is a vibe. */

type Verdict = RotCheck['verdict'];

const VERDICT_INK: Record<Verdict, string> = {
  // judgment red, a whisper: the brand reserves it for genuine alarms, and rot is one
  'ROT FOUND': 'var(--helicon-critical)',
  // calm slate-blue. The world is blue here; "clean" is never vibe-code green.
  CLEAN: 'var(--helicon-good)',
  // amber = a gap you own, deliberately NOT the clean blue and NOT the rot red
  UNMEASURED: 'var(--helicon-stale)',
};

/* What to DO about each class, and it has to be true. Every command below is a
   real command (verified against `helicon <cmd> --help`), and `queue: true`
   only where that class actually surfaces a finding in Needs Ruling. */
const NEXT_STEP: Record<string, { queue: boolean; cmd?: string; how: string }> = {
  R1: { queue: true, cmd: 'helicon resolve --list', how: 'Rule the contradiction: one value is the truth, the other becomes law.' },
  R2: { queue: false, how: 'The receipt names each doc and the claim that drifted. Fix the doc, then re-run the exam.' },
  R3: { queue: true, how: 'Age, in bulk. Retire what is past its half-life or reinforce what still holds.' },
  R4: { queue: true, cmd: 'helicon alias --scan', how: 'Dead names in current claims. History keeps the old name; a live claim must not.' },
  R5: { queue: false, cmd: 'helicon consolidate', how: 'The same content stored twice. Merge the echoes.' },
  R6: { queue: true, how: 'Stubs with no substance to retrieve. Ground them or retire them.' },
  R7: { queue: true, how: 'Retrieval keeps wanting these back. The kill was wrong; restore what earned it.' },
  R8: { queue: false, cmd: 'helicon snapshot check', how: 'Retrieval moved against its baseline. Check the drift, re-baseline only if the new answer is better.' },
  R9: { queue: false, how: 'A non-human review reached rule learning. The guard is one predicate (db.human_evidence_sql) and it must hold.' },
  R10: { queue: true, how: 'A rules or skills section drifted from its file. Reconcile it against source.' },
  R11: { queue: true, cmd: 'helicon resolve --list', how: 'One name, two incompatible definitions. Name the canonical one.' },
  R12: { queue: true, how: 'A relation only one speculative source asserts. Ground it or drop it.' },
};

function VerdictChip({ verdict }: { verdict: Verdict }) {
  const ink = VERDICT_INK[verdict];
  const rot = verdict === 'ROT FOUND';
  const unmeasured = verdict === 'UNMEASURED';
  return (
    <span
      className="inline-flex items-center shrink-0 whitespace-nowrap"
      style={{
        fontFamily: 'var(--helicon-mono)', fontSize: 9.5, letterSpacing: '0.1em',
        color: ink, padding: '3px 7px', borderRadius: 5,
        fontWeight: rot ? 600 : 500,
        background: rot ? 'rgba(169,74,61,0.08)' : unmeasured ? 'rgba(198,150,63,0.10)' : 'transparent',
        // the gap wears a dashed edge: legible as "not checked" even in grayscale,
        // so the status never rides on colour alone
        border: unmeasured ? '1px dashed rgba(198,150,63,0.5)'
          : rot ? '1px solid rgba(169,74,61,0.22)' : '1px solid var(--helicon-line)',
      }}
    >
      {verdict}
    </span>
  );
}

function ClassRow({ c, onRule }: { c: RotCheck; onRule: () => void }) {
  const rot = c.verdict === 'ROT FOUND';
  const step = NEXT_STEP[c.id];
  return (
    <div
      className="py-3.5"
      style={{
        borderTop: '1px solid var(--helicon-line)',
        // the rotten classes carry a weight the clean ones don't
        background: rot ? 'rgba(169,74,61,0.022)' : 'transparent',
      }}
    >
      <div className="flex items-baseline gap-2.5 px-1">
        <span
          style={{ fontFamily: 'var(--helicon-mono)', fontSize: 10.5, color: 'var(--helicon-faint)', minWidth: 26 }}
        >
          {c.id}
        </span>
        <span
          className="flex-1 min-w-0"
          style={{ fontSize: 13.5, color: 'var(--helicon-ink)', fontWeight: rot ? 600 : 500 }}
        >
          {c.name}
        </span>
        <VerdictChip verdict={c.verdict} />
      </div>

      {/* the receipt: the number, and where it came from */}
      <div
        className="mt-1.5 pl-[36px] pr-1"
        style={{ fontSize: 11.5, lineHeight: 1.55, color: 'var(--helicon-muted)', overflowWrap: 'anywhere' }}
      >
        {c.receipt}
      </div>

      {c.coverage !== 'TESTED' && (
        <div className="mt-1 pl-[36px]" style={{ fontSize: 10.5, color: 'var(--helicon-stale)' }}>
          partial coverage — the gap is named in ROT.md
        </div>
      )}

      {/* An exam that finds rot and names no next step leaves the loop open. */}
      {rot && step && (
        <div className="mt-2.5 pl-[36px] pr-1 flex flex-wrap items-center gap-2">
          <span style={{ fontSize: 11, color: 'var(--helicon-ink-70)' }}>{step.how}</span>
          {step.queue && (
            <button
              onClick={onRule}
              className="h-auto"
              style={{
                fontFamily: 'var(--helicon-mono)', fontSize: 10, letterSpacing: '0.06em',
                color: 'var(--helicon-on-dark)', background: 'var(--helicon-accent)',
                border: 'none', borderRadius: 5, padding: '5px 9px', cursor: 'pointer',
              }}
            >
              RULE ON IT →
            </button>
          )}
          {step.cmd && (
            <code
              style={{
                fontFamily: 'var(--helicon-mono)', fontSize: 10, color: 'var(--helicon-muted)',
                background: 'var(--helicon-bg-2)', borderRadius: 5, padding: '4px 7px',
              }}
            >
              {step.cmd}
            </code>
          )}
        </div>
      )}
    </div>
  );
}

export default function ExamView({ onGoToFindings }: { onGoToFindings: () => void }) {
  const [data, setData] = useState<RotExam | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback((fresh = false) => {
    setBusy(true);
    api.getRot(fresh).then(d => { setData(d); setErr(null); })
      .catch(e => setErr(String(e)))
      .finally(() => setBusy(false));
  }, []);
  useEffect(() => { load(false); }, [load]);

  if (err) return <div style={{ fontSize: 12, color: 'var(--helicon-critical)' }}>The exam did not run: {err}</div>;
  if (!data) {
    return (
      <div style={{ fontSize: 12, color: 'var(--helicon-muted)', lineHeight: 1.6 }}>
        Running the exam…
        <div style={{ fontSize: 11, color: 'var(--helicon-faint)', marginTop: 4 }}>
          Twelve classes against the live store. R8 replays every captured snapshot, so a cold run takes a moment.
        </div>
      </div>
    );
  }

  const rot = data.rot_found;
  const clean = data.checks.filter(c => c.verdict === 'CLEAN').length;

  return (
    <div className="animate-fade-in">
      <div
        className="rounded-2xl overflow-hidden"
        style={{ background: 'var(--helicon-panel)', boxShadow: 'var(--helicon-shadow)' }}
      >
        {/* Headline. The number is the hero: Fraunces, big, coloured by meaning. */}
        <div className="px-5 pt-5 pb-4 sm:px-7 sm:pt-7">
          <div className="flex items-start justify-between gap-3">
            <div
              style={{ fontSize: 9.5, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}
            >
              the rot exam · ROT.md, executable
            </div>
            <button
              onClick={() => load(true)}
              disabled={busy}
              className="h-auto shrink-0"
              style={{
                fontFamily: 'var(--helicon-mono)', fontSize: 10, color: 'var(--helicon-muted)',
                background: 'transparent', border: '1px solid var(--helicon-line)',
                borderRadius: 5, padding: '4px 8px', cursor: busy ? 'default' : 'pointer',
                opacity: busy ? 0.5 : 1,
              }}
            >
              {busy ? 'RUNNING…' : 'RE-RUN'}
            </button>
          </div>

          <div className="flex items-end gap-3 mt-3 flex-wrap">
            <span
              style={{
                fontFamily: 'var(--helicon-serif)', fontSize: 60, lineHeight: 0.86, fontWeight: 300,
                fontVariationSettings: "'opsz' 144", letterSpacing: '-0.02em',
                color: rot > 0 ? 'var(--helicon-critical)' : 'var(--helicon-good)',
              }}
            >
              {rot}<span style={{ color: 'var(--helicon-faint)' }}>/{data.classes}</span>
            </span>
            <span style={{ fontSize: 13, color: 'var(--helicon-ink)', paddingBottom: 4 }}>
              {rot === 1 ? 'class shows rot right now' : 'classes show rot right now'}
            </span>
          </div>

          {/* The coverage line. It exists so "12/12 fully tested" can never be
              inferred from silence — and so an UNMEASURED class is counted out
              loud rather than folded into the clean side of the headline. */}
          <div className="mt-3 flex flex-wrap items-center gap-x-2.5 gap-y-1" style={{ fontSize: 11.5 }}>
            <span style={{ color: 'var(--helicon-muted)' }}>
              <b style={{ color: 'var(--helicon-ink)', fontWeight: 600 }}>{data.tested}/{data.classes}</b> fully tested
            </span>
            <span style={{ color: 'var(--helicon-faint)' }}>·</span>
            <span style={{ color: 'var(--helicon-good)' }}>{clean} clean</span>
            <span style={{ color: 'var(--helicon-faint)' }}>·</span>
            <span style={{ color: rot ? 'var(--helicon-critical)' : 'var(--helicon-muted)' }}>{rot} rot found</span>
            <span style={{ color: 'var(--helicon-faint)' }}>·</span>
            <span style={{ color: data.unmeasured ? 'var(--helicon-stale)' : 'var(--helicon-muted)' }}>
              {data.unmeasured} unmeasured
            </span>
            {data.unmeasured > 0 && (
              <span style={{ color: 'var(--helicon-stale)', fontSize: 10.5 }}>(not a pass)</span>
            )}
          </div>

          <div className="mt-2.5" style={{ fontSize: 11, color: 'var(--helicon-muted)', lineHeight: 1.55 }}>
            Twelve documented failure classes, each checked against this store. Zero LLM calls:
            the exam is deterministic, so the same store gives the same verdict every time.
          </div>

          {/* When it ran, always. R8 replays real retrieval so the result is
              held for a few minutes; a held verdict that looked live would be
              the exact rot this exam exists to catch. */}
          <div className="mt-1.5" style={{ fontFamily: 'var(--helicon-mono)', fontSize: 9.5, color: 'var(--helicon-faint)' }}>
            ran {new Date(data.ran_at).toLocaleTimeString()} · took {data.took_s}s
            {data.cached && ' · held result, RE-RUN for a fresh one'}
          </div>
        </div>

        <div className="px-4 pb-3 sm:px-6">
          {data.checks.map(c => (
            <ClassRow key={c.id} c={c} onRule={onGoToFindings} />
          ))}
        </div>
      </div>
    </div>
  );
}
