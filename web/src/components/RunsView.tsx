import { useEffect, useState } from 'react';

/* RUNS — the post-night-run cockpit. Score whole runs (verified yield / cost -
   damage) and read what to do next off the history. Shape from /api/runs:
   { cards: RunCard[], suggest: { scored_runs, min_runs, best_shape, route } }.
   Alpine Wash: ink-navy on paper, Fraunces numbers as heroes, one warm pop
   (--improve) for the good end of a score. No status-light theater. */

type RunCard = {
  run_id: string; start: string | null; end: string | null;
  duration_min: number; model: string; session_count: number;
  output_tokens: number; total_tokens: number;
  verified: number; checkable: number; verified_ratio: number | null;
  cost: number; damage: number; score: number;
};
type Suggest = {
  scored_runs: number; min_runs: number;
  best_shape: Record<string, number> | null;
  route: { results: { task_class: string; recommendation: string | null; lean: string | null;
                      best: { pass: number; n: number } }[] };
};

function fmtTok(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${Math.round(n / 1000)}k`;
  return String(n);
}
function when(iso: string | null): string {
  return (iso || '').slice(0, 16).replace('T', ' ');
}
// score colour: warm improvement pop at the good end, muted ink at the low end
function scoreColor(s: number): string {
  if (s >= 0.9) return 'var(--improve)';
  if (s >= 0.5) return 'var(--text-primary)';
  return 'var(--text-muted)';
}

const MONO = { fontFamily: '"IBM Plex Mono", monospace' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;

export default function RunsView() {
  const [data, setData] = useState<{ cards: RunCard[]; suggest: Suggest } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/runs').then(r => r.json())
      .then(d => alive && setData(d)).catch(e => alive && setErr(String(e)));
    return () => { alive = false; };
  }, []);

  if (err) return <div className="py-16 text-center text-[13px]" style={{ color: 'var(--improve)' }}>Could not load runs: {err}</div>;
  if (!data) return <div className="py-20 text-center text-sm" style={{ color: 'var(--text-muted)' }}>Scoring runs…</div>;

  const { cards, suggest } = data;

  return (
    <div className="max-w-3xl mx-auto">
      {/* header */}
      <div className="mb-6">
        <div style={{ ...MONO }} className="text-[11px] tracking-[0.14em] uppercase mb-1" >
          <span style={{ color: 'var(--text-muted)' }}>after the night run</span>
        </div>
        <h2 style={{ fontFamily: '"Fraunces", serif', color: 'var(--text-primary)' }}
            className="text-[26px] leading-tight font-medium">
          Which runs earned their tokens
        </h2>
      </div>

      {/* suggestions strip */}
      <div className="mb-6 rounded-[14px] p-4"
           style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
        <div className="grid grid-cols-3 gap-4">
          <Suggestion label="best run shape"
            value={suggest.best_shape
              ? Object.entries(suggest.best_shape).sort((a, b) => b[1] - a[1])[0][0]
              : `need ${suggest.min_runs - suggest.scored_runs} more`} />
          <Suggestion label="route the next task to"
            value={routePick(suggest.route)} />
          <Suggestion label="scored runs"
            value={`${suggest.scored_runs}`} mono />
        </div>
      </div>

      {/* run cards */}
      {cards.length === 0 ? (
        <div className="py-16 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
          No scored runs yet. Close a run: <span style={MONO}>helicon runs --close</span>
        </div>
      ) : (
        <div className="space-y-2.5">
          {cards.map(c => <RunCardRow key={c.run_id} c={c} />)}
        </div>
      )}
    </div>
  );
}

function routePick(route: Suggest['route']): string {
  const picks = (route?.results || []).filter(r => r.recommendation || r.lean);
  if (!picks.length) return 'no evidence yet';
  const r = picks[0];
  return `${r.recommendation || r.lean} · ${r.task_class}`;
}

function Suggestion({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ ...MONO, color: 'var(--text-muted)' }} className="text-[10px] tracking-[0.1em] uppercase mb-1.5">{label}</div>
      <div style={mono ? { ...NUM, color: 'var(--text-primary)' } : { color: 'var(--text-primary)' }}
           className={mono ? 'text-[22px] leading-none' : 'text-[14px] leading-snug font-medium'}>
        {value}
      </div>
    </div>
  );
}

function RunCardRow({ c }: { c: RunCard }) {
  const ratio = c.verified_ratio ?? 0;
  return (
    <div className="rounded-[14px] px-5 py-4 flex items-center gap-5"
         style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
      {/* left: identity */}
      <div className="flex-1 min-w-0">
        <div style={{ color: 'var(--text-primary)' }} className="text-[14px] font-medium truncate">
          {when(c.start)}
        </div>
        <div style={{ ...MONO, color: 'var(--text-muted)' }} className="text-[11px] mt-0.5">
          {c.session_count} session{c.session_count === 1 ? '' : 's'} · {c.duration_min}m · {fmtTok(c.output_tokens)} out · {c.model.replace('claude-', '')}
        </div>
      </div>

      {/* middle: verified yield bar */}
      <div className="w-32 shrink-0">
        <div style={{ ...MONO, color: 'var(--text-secondary)' }} className="text-[11px] mb-1">
          {c.verified}/{c.checkable} verified
        </div>
        <div className="h-[5px] rounded-full overflow-hidden" style={{ background: 'var(--accent-dim)' }}>
          <div className="h-full rounded-full" style={{ width: `${ratio * 100}%`, background: 'var(--accent)' }} />
        </div>
        {c.damage > 0 && (
          <div style={{ ...MONO, color: 'var(--improve)' }} className="text-[10px] mt-1">− {c.damage} damage</div>
        )}
      </div>

      {/* right: the hero — the score */}
      <div className="text-right shrink-0 w-16">
        <div style={{ ...NUM, color: scoreColor(c.score) }} className="text-[34px] leading-none">
          {c.score}
        </div>
        <div style={{ ...MONO, color: 'var(--text-muted)' }} className="text-[9px] tracking-[0.12em] uppercase mt-0.5">score</div>
      </div>
    </div>
  );
}
