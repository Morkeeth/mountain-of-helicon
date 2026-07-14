import { useEffect, useState } from 'react';

/* ROUTE — which model earns the work. Two reads, both from verified reality:
   /api/route (per task-class, Wilson-scored verified pass-rate on YOUR terminals)
   and /api/leaderboard (population survive-vs-revert across your repos). Alpine
   Wash: the Wilson lower bound is the hero number, Fraunces, colored by strength;
   mono for the tabular truth. No status lights, no fake precision. */

type RouteResult = {
  task_class: string; recommendation: string | null; lean: string | null;
  sufficient: boolean; min_n: number; uncheckable: number; models_compared: number;
  best: { model: string; harness: string; pass: number; fail: number; n: number;
          rate: number; wilson_lb: number };
  candidates: { model: string; pass: number; n: number; wilson_lb: number }[];
};
type LbRow = {
  model: string; harness: string; commits: number; reverted: number;
  revert_rate: number; survival_lb: number;
};

const MONO = { fontFamily: '"IBM Plex Mono", monospace' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;

function lbColor(v: number): string {
  if (v >= 0.9) return 'var(--improve)';
  if (v >= 0.5) return 'var(--text-primary)';
  return 'var(--text-muted)';
}

export default function RouteView() {
  const [route, setRoute] = useState<{ results: RouteResult[] } | null>(null);
  const [lb, setLb] = useState<{ commits: number; repos: number; rows: LbRow[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/route').then(r => r.json()).then(d => alive && setRoute(d)).catch(e => alive && setErr(String(e)));
    fetch('/api/leaderboard?max=200').then(r => r.json()).then(d => alive && setLb(d)).catch(() => {});
    return () => { alive = false; };
  }, []);

  if (err) return <div className="py-16 text-center text-[13px]" style={{ color: 'var(--improve)' }}>Could not load route: {err}</div>;
  if (!route) return <div className="py-20 text-center text-sm" style={{ color: 'var(--text-muted)' }}>Reading verified outcomes…</div>;

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <div style={MONO} className="text-[11px] tracking-[0.14em] uppercase mb-1"><span style={{ color: 'var(--text-muted)' }}>from verified outcomes, not benchmarks</span></div>
        <h2 style={{ fontFamily: '"Fraunces", serif', color: 'var(--text-primary)' }} className="text-[26px] leading-tight font-medium">
          Which model earns the work
        </h2>
      </div>

      {/* per task-class routing (your terminals' verdicts) */}
      <div className="space-y-2.5 mb-8">
        {route.results.length === 0 && (
          <div className="py-10 text-center text-sm" style={{ color: 'var(--text-muted)' }}>
            No routing evidence yet. Build it: <span style={MONO}>helicon route --record --run</span>
          </div>
        )}
        {route.results.map(r => {
          const pick = r.recommendation || r.lean;
          const tag = r.recommendation ? 'route' : r.lean ? 'lean' : 'insufficient';
          return (
            <div key={r.task_class} className="rounded-[14px] px-5 py-4 flex items-center gap-5"
                 style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
              <div className="flex-1 min-w-0">
                <div style={{ color: 'var(--text-primary)' }} className="text-[14px] font-medium">
                  {r.task_class}
                </div>
                <div style={{ ...MONO, color: 'var(--text-muted)' }} className="text-[11px] mt-0.5">
                  {pick
                    ? <>{tag} <span style={{ color: 'var(--text-secondary)' }}>{pick.replace('claude-', '')}</span> · verified {r.best.pass}/{r.best.n}</>
                    : <>best: {r.best.model.replace('claude-', '')} {r.best.pass}/{r.best.n}, need n≥{r.min_n}</>}
                </div>
              </div>
              <div className="text-right shrink-0 w-20">
                <div style={{ ...NUM, color: lbColor(r.best.wilson_lb) }} className="text-[28px] leading-none">{r.best.wilson_lb}</div>
                <div style={{ ...MONO, color: 'var(--text-muted)' }} className="text-[9px] tracking-[0.12em] uppercase mt-0.5">wilson lb</div>
              </div>
            </div>
          );
        })}
      </div>

      {/* population reliability leaderboard (survive vs revert across repos) */}
      {lb && lb.rows.length > 0 && (
        <div>
          <div style={MONO} className="text-[11px] tracking-[0.14em] uppercase mb-2" >
            <span style={{ color: 'var(--text-muted)' }}>reliability · {lb.commits} commits, {lb.repos} repos · survive vs revert</span>
          </div>
          <div className="rounded-[14px] overflow-hidden" style={{ background: 'var(--surface)', border: '1px solid var(--border)' }}>
            <table className="w-full text-[12px]" style={MONO}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left font-normal py-2 px-4">model</th>
                  <th className="text-left font-normal py-2 px-2">harness</th>
                  <th className="text-right font-normal py-2 px-2">commits</th>
                  <th className="text-right font-normal py-2 px-2">revert</th>
                  <th className="text-right font-normal py-2 px-4">survival</th>
                </tr>
              </thead>
              <tbody>
                {lb.rows.map((r, i) => (
                  <tr key={i} style={{ color: 'var(--text-secondary)', borderTop: i ? '1px solid var(--border-subtle)' : 'none' }}>
                    <td className="py-2 px-4" style={{ color: 'var(--text-primary)' }}>{r.model}</td>
                    <td className="py-2 px-2">{r.harness}</td>
                    <td className="py-2 px-2 text-right">{r.commits}</td>
                    <td className="py-2 px-2 text-right" style={{ color: r.revert_rate > 0 ? 'var(--improve)' : 'var(--text-muted)' }}>
                      {(r.revert_rate * 100).toFixed(1)}%
                    </td>
                    <td className="py-2 px-4 text-right" style={{ ...NUM, color: lbColor(r.survival_lb) }}>{r.survival_lb}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
