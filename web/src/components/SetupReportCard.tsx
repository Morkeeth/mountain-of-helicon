import { useState } from 'react';

/* The Setup Report Card, "how healthy is my agent's memory setup?", graded
   live against the Track-1 MemoryAgent criteria. Heavy (runs the battery +
   cross-source pairing), so it's an explicit "run the exam" action. */

const API = (p: string) => fetch(`/api${p}`).then(r => r.json());

const VERDICT: Record<string, { color: string; label: string }> = {
  HEALTHY: { color: 'var(--helicon-good)', label: 'Healthy' },
  DEGRADED: { color: 'var(--helicon-stale)', label: 'Degraded' },
  BROKEN: { color: 'var(--helicon-accent)', label: 'Broken' },
};

interface SubGoal { verdict: string; [k: string]: unknown }
interface Report {
  track: string; overall: string;
  battery_tasks: { total: number; healthy?: number; degraded?: number; broken?: number };
  last_scan_hours_ago: number | null;
  sub_goals: Record<string, SubGoal>;
}

// Audit Score ring — the honest overall (healthy retrieval tasks / total)
function Ring({ pct, color }: { pct: number; color: string }) {
  const r = 33;
  const c = 2 * Math.PI * r;
  const off = c * (1 - Math.max(0, Math.min(100, pct)) / 100);
  return (
    <svg width="94" height="94" viewBox="0 0 94 94" className="shrink-0">
      <circle cx="47" cy="47" r={r} fill="none" stroke="var(--helicon-mist)" strokeWidth="6.5" />
      <circle
        cx="47" cy="47" r={r} fill="none" stroke={color} strokeWidth="6.5" strokeLinecap="round"
        strokeDasharray={c} strokeDashoffset={off} transform="rotate(-90 47 47)"
        style={{ transition: 'stroke-dashoffset .9s cubic-bezier(0.16,1,0.3,1)' }}
      />
      <text x="47" y="52" textAnchor="middle" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontSize: 23 }} fill="var(--helicon-ink)">{pct}%</text>
    </svg>
  );
}

const GOAL_META: { key: string; label: string; stat: (g: SubGoal) => string }[] = [
  { key: 'efficient_storage_retrieval', label: 'Efficient store & retrieval',
    stat: g => `P@3 ${g.precision_at_3 ?? '-'} · MRR ${g.mrr ?? '-'}` },
  { key: 'timely_forgetting', label: 'Timely forgetting',
    stat: g => `${(g.retired_superseded as number ?? 0) + (g.retired_killed as number ?? 0)} retired · freshness ${g.freshness_pass_rate ?? '-'}` },
  { key: 'recall_under_limited_context', label: 'Recall in limited context',
    stat: g => `~${g.mean_tokens_per_query_top5 ?? '-'} tok/query · thinness ${g.thinness_pass_rate ?? '-'}` },
  { key: 'cross_session_accuracy', label: 'Cross-session accuracy',
    stat: g => {
      const cs = (g.cross_source_contradictions as { inter_judge_kappa?: number; second_judge?: string } | undefined);
      const k = cs?.inter_judge_kappa;
      const base = `${g.snapshots_regressed ?? 0}/${g.snapshots_total ?? 0} snapshots regressed`;
      return k != null ? `${base} · two-judge κ=${k}` : `${base} · two-judge panel (Qwen + ${cs?.second_judge ?? 'DeepSeek'})`;
    } },
];

export default function SetupReportCard() {
  const [rep, setRep] = useState<Report | null>(null);
  const [loading, setLoading] = useState(false);

  const run = () => {
    setLoading(true);
    API('/setup-report').then(setRep).finally(() => setLoading(false));
  };

  const ov = rep ? (VERDICT[rep.overall] || VERDICT.DEGRADED) : null;

  return (
    <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: 'var(--helicon-muted)' }}>
            Setup report card
          </div>
          <p className="mt-1.5 text-[13px]" style={{ color: 'var(--helicon-muted)', maxWidth: '46ch' }}>
            How healthy is your agent's memory setup? Graded live against the seven MemoryAgent criteria, storage, forgetting, recall, cross-session accuracy.
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="text-[12px] px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 shrink-0"
          style={{ background: 'var(--helicon-accent)' }}
        >
          {loading ? 'running the exam…' : rep ? 'Re-run exam' : 'Run the exam'}
        </button>
      </div>

      {loading && (
        <p className="mt-6 text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
          Running the battery over every retrieval task + scanning for cross-source contradictions… (~20s)
        </p>
      )}

      {rep && !loading && (
        <div className="mt-6">
          <div className="flex items-center gap-5 mb-6">
            <Ring
              pct={rep.battery_tasks.total ? Math.round(((rep.battery_tasks.healthy ?? 0) / rep.battery_tasks.total) * 100) : 0}
              color={ov!.color}
            />
            <div>
              <div className="text-[10px] uppercase tracking-[0.2em]" style={{ color: 'var(--helicon-muted)' }}>Overall score</div>
              <div className="text-[26px] leading-tight" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: ov!.color }}>
                {ov!.label}
              </div>
              <div className="text-[12px] mt-0.5 tabular-nums" style={{ color: 'var(--helicon-muted)' }}>
                {rep.battery_tasks.total} retrieval tasks · {rep.battery_tasks.healthy ?? 0} healthy / {rep.battery_tasks.degraded ?? 0} degraded / {rep.battery_tasks.broken ?? 0} broken
                {rep.last_scan_hours_ago != null && ` · scanned ${rep.last_scan_hours_ago}h ago`}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {GOAL_META.map(m => {
              const g = rep.sub_goals[m.key];
              if (!g) return null;
              const v = VERDICT[g.verdict] || VERDICT.DEGRADED;
              return (
                <div key={m.key} className="rounded-lg border border-zinc-800/30 px-4 py-3" style={{ background: 'rgba(23,40,58,0.025)' }}>
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[13px]" style={{ color: 'var(--helicon-ink)' }}>{m.label}</span>
                    <span className="text-[10px] uppercase tracking-wider px-1.5 py-0.5 rounded" style={{ color: v.color, border: `1px solid ${v.color}` }}>
                      {v.label}
                    </span>
                  </div>
                  <p className="text-[11px] mt-1 tabular-nums" style={{ color: 'var(--helicon-muted)' }}>{m.stat(g)}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
