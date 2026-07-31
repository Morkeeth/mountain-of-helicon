import { useEffect, useState } from 'react';

/* BRIEF — the calm morning glance. One number (how many things need YOU), the
   few things that do, and everything else reduced to a single quiet line. No
   section labels, no nested lists, no tables. Reads /api/brief. Alpine Wash. */

type DayRun = { id: string; objective: string; model: string; outcome: string; artifacts: number };
type Today = {
  day: string | null;
  has_activity: boolean;
  runs: DayRun[];
  totals: { runs: number; accepted: number; rework: number; rollback: number; needs_verdict: number; known_tokens: number; unknown_cost_runs: number };
  scored: { cards: number; output_tokens: number; avg_score: number | null; total_cost: number | null };
  rulings_applied: number;
  headline: string;
};
type Brief = {
  truth: { headline: string };
  continuity: { headline: string };
  direction: { headline: string };
  reflection: { headline: string; today?: Today };
  calm: { headline: string; worth_your_judgment: { id: number; finding: string; severity: string }[] };
};

const OUTCOME_COLOR: Record<string, string> = {
  accepted: 'var(--good, #4a7c59)',
  needs_verdict: 'var(--stale, #b07d2b)',
  rework: 'var(--regress, #b4472e)',
  rollback: 'var(--regress, #b4472e)',
};

const SERIF = { fontFamily: '"Fraunces", serif' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;

export default function BriefView() {
  const [b, setB] = useState<Brief | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/brief').then(r => r.json()).then(d => alive && setB(d)).catch(e => alive && setErr(String(e)));
    return () => { alive = false; };
  }, []);

  if (err) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>brief unavailable — {err}</div>;
  if (!b) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>…</div>;

  const need = b.calm.worth_your_judgment;
  const today = b.reflection.today;

  return (
    <div style={{ maxWidth: 620, margin: '0 auto', padding: '64px 24px' }}>
      {/* the one thing that matters */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
        <span style={{ ...NUM, fontSize: 88, lineHeight: 1, fontWeight: 300,
                       color: need.length ? 'var(--regress, #b4472e)' : 'var(--text-muted)' }}>
          {need.length}
        </span>
        <span style={{ ...SERIF, fontSize: 22, color: 'var(--text-primary)' }}>
          {need.length === 1 ? 'thing worth your judgment' : 'things worth your judgment'}
        </span>
      </div>

      {/* the few things — just the words, calm */}
      <div style={{ marginTop: 28 }}>
        {need.length === 0 && (
          <div style={{ ...SERIF, fontSize: 17, color: 'var(--text-muted)' }}>Nothing needs you right now.</div>
        )}
        {need.map(e => (
          <div key={e.id} style={{ display: 'flex', gap: 14, alignItems: 'baseline', padding: '11px 0',
                                   borderTop: '1px solid var(--border, rgba(0,0,0,.08))' }}>
            <span style={{ width: 7, height: 7, borderRadius: 7, flexShrink: 0, marginTop: 7,
                           background: e.severity === 'critical' ? 'var(--regress, #b4472e)' : 'var(--text-muted)' }} />
            <span style={{ ...SERIF, fontSize: 16, lineHeight: 1.5, color: 'var(--text-primary)' }}>{e.finding}</span>
          </div>
        ))}
      </div>

      {/* everything else — four quiet lines, nothing shouting */}
      <div style={{ marginTop: 44, display: 'flex', flexDirection: 'column', gap: 7,
                    fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        <div>{b.truth.headline}</div>
        <div>{b.direction.headline}</div>
        <div>{b.reflection.headline}</div>
        <div>{b.continuity.headline}</div>
      </div>

      {/* Reflection — a real day of runs, only when there is one */}
      {today?.has_activity && (
        <div style={{ marginTop: 40, paddingTop: 22, borderTop: '1px solid var(--border, rgba(0,0,0,.08))' }}>
          <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
            <span style={{ ...SERIF, fontSize: 16, color: 'var(--text-primary)' }}>Reflection</span>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', fontVariantNumeric: 'tabular-nums' }}>{today.day}</span>
          </div>
          <div style={{ display: 'flex', gap: 22, marginTop: 12, flexWrap: 'wrap' }}>
            <Stat n={today.totals.runs} label={today.totals.runs === 1 ? 'run' : 'runs'} />
            <Stat n={today.totals.needs_verdict} label="need you"
                  color={today.totals.needs_verdict ? 'var(--stale, #b07d2b)' : undefined} />
            <Stat n={today.totals.accepted} label="accepted" />
            <Stat n={today.rulings_applied} label={today.rulings_applied === 1 ? 'ruling' : 'rulings'} />
            {today.totals.known_tokens > 0 && (
              <Stat n={Math.round(today.totals.known_tokens / 1000)} label="k tokens" />
            )}
          </div>
          <div style={{ marginTop: 16 }}>
            {today.runs.slice(0, 6).map(r => (
              <div key={r.id} style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '8px 0',
                                       borderTop: '1px solid var(--border, rgba(0,0,0,.06))' }}>
                <span style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '.06em',
                               width: 96, flexShrink: 0, color: OUTCOME_COLOR[r.outcome] || 'var(--text-muted)' }}>
                  {r.outcome === 'needs_verdict' ? 'needs you' : r.outcome}
                </span>
                <span style={{ ...SERIF, fontSize: 14, color: 'var(--text-primary)', flex: 1 }}>{r.objective}</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{r.artifacts} file{r.artifacts === 1 ? '' : 's'}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ n, label, color }: { n: number; label: string; color?: string }) {
  return (
    <span style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
      <span style={{ ...NUM, fontSize: 26, fontWeight: 300, color: color || 'var(--text-primary)' }}>{n}</span>
      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{label}</span>
    </span>
  );
}
