import { useState, useEffect } from 'react';
import { api } from '../api';
import type { ProjectRecommendation, WeeklySummary, ContextSwitchData } from '../api';

export function FocusView() {
  const [recommendations, setRecommendations] = useState<ProjectRecommendation[]>([]);
  const [weekly, setWeekly] = useState<WeeklySummary | null>(null);
  const [contextSwitches, setContextSwitches] = useState<ContextSwitchData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getProjectRecommendations(),
      api.getContextSwitches(),
    ]).then(([rec, cs]) => {
      setRecommendations(rec.recommendations);
      setWeekly(rec.weekly);
      setContextSwitches(cs);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="py-20 text-center">
        <span className="text-zinc-600 text-sm">Loading project intelligence...</span>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Top banner */}
      {weekly && (
        <div className="border border-zinc-800/40 rounded-lg px-5 py-4">
          <div className="flex items-baseline justify-between">
            <div>
              <span className="text-[14px] text-zinc-300">
                You touched <strong className="text-zinc-100 tabular-nums">{weekly.touched_count}</strong> projects this week.
              </span>
              <span className="text-[14px] text-zinc-300 ml-1">
                You shipped from <strong className={`tabular-nums ${weekly.shipped_count === 0 ? 'text-red-400' : 'text-emerald-400'}`}>{weekly.shipped_count}</strong>.
              </span>
            </div>
            <span className="text-[11px] text-zinc-700">since {weekly.week_start}</span>
          </div>
          {weekly.shipped_count > 0 && (
            <div className="mt-2 flex gap-1.5 flex-wrap">
              {weekly.shipped_from.map(p => (
                <span key={p} className="text-[11px] px-2 py-0.5 bg-emerald-500/10 text-emerald-400/80 rounded">
                  {p}
                </span>
              ))}
            </div>
          )}
          {weekly.shipped_count === 0 && weekly.touched_count > 0 && (
            <p className="text-[12px] text-red-400/60 mt-2">
              All motion, no output. Pick one project and ship something.
            </p>
          )}
        </div>
      )}

      {/* Context switch alert */}
      {contextSwitches && contextSwitches.avg_switch_index > 0.2 && (
        <div className="border border-amber-200 rounded-lg px-5 py-3 bg-amber-50">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
            <span className="text-[13px] text-amber-700">
              Context-switch index: {(contextSwitches.avg_switch_index * 100).toFixed(0)}%
            </span>
          </div>
          <p className="text-[11px] text-zinc-600 mt-1">
            {contextSwitches.flagged_sessions.length} sessions touched 3+ projects with nothing shipped.
          </p>
        </div>
      )}

      {/* Project cards */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-10">
        <div>
          <div className="flex items-baseline justify-between mb-6">
            <h2 className="text-[15px] font-medium text-zinc-200">Projects by Urgency</h2>
            <span className="text-[11px] text-zinc-700">{recommendations.length} active</span>
          </div>

          <div className="space-y-1">
            {recommendations.map((rec, i) => (
              <ProjectCard key={rec.name} rec={rec} rank={i + 1} />
            ))}
            {recommendations.length === 0 && (
              <div className="py-12 text-center">
                <p className="text-zinc-600 text-sm">No projects with enough data yet.</p>
                <p className="text-zinc-700 text-[12px] mt-1">Scan more sources to populate project intelligence.</p>
              </div>
            )}
          </div>
        </div>

        <aside className="space-y-6">
          <ContextSwitchPanel data={contextSwitches} />
          <FocusLegend />
        </aside>
      </div>
    </div>
  );
}

function ProjectCard({ rec, rank }: { rec: ProjectRecommendation; rank: number }) {
  const [expanded, setExpanded] = useState(false);

  const shipColor = rec.ship_rate === 0
    ? 'text-red-600'
    : rec.ship_rate > 0.3
      ? 'text-emerald-600'
      : 'text-amber-600';

  const spinColor = rec.spin_score > 3
    ? 'text-red-600'
    : rec.spin_score > 1.5
      ? 'text-amber-600'
      : 'text-zinc-500';

  const urgencyBar = Math.min(rec.score / 80, 1);
  const urgencyColor = rec.score > 50
    ? 'bg-red-500/40'
    : rec.score > 30
      ? 'bg-amber-400'
      : 'bg-zinc-700/40';

  return (
    <div
      className="py-4 border-b border-zinc-800/30 cursor-pointer hover:bg-zinc-800/10 transition-colors rounded-sm px-1 -mx-1"
      onClick={() => setExpanded(!expanded)}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-zinc-700 tabular-nums w-4">{rank}</span>
            <h3 className="text-[14px] font-medium text-zinc-200 truncate">{rec.name}</h3>
            <div className="flex-1" />
            <div className="w-16 h-[3px] rounded-full overflow-hidden bg-zinc-800/60 shrink-0">
              <div
                className={`h-full rounded-full ${urgencyColor}`}
                style={{ width: `${urgencyBar * 100}%` }}
              />
            </div>
            <span className="text-[11px] text-zinc-600 tabular-nums w-8 text-right">{rec.score}</span>
          </div>

          <p className="text-[12px] text-zinc-500 leading-relaxed pl-6">{rec.action}</p>

          <div className="flex gap-4 mt-2 pl-6 text-[11px]">
            <span className="text-zinc-600 tabular-nums">{rec.cube_count} cubes</span>
            <span className={`tabular-nums ${shipColor}`}>
              {(rec.ship_rate * 100).toFixed(0)}% shipped
            </span>
            <span className={`tabular-nums ${spinColor}`}>
              {rec.spin_score.toFixed(1)}x spin
            </span>
            {rec.days_since_output !== null && (
              <span className={`tabular-nums ${rec.days_since_output > 14 ? 'text-red-600' : 'text-zinc-600'}`}>
                {rec.days_since_output}d ago
              </span>
            )}
            <span className="text-zinc-700 tabular-nums">{rec.pending} pending</span>
          </div>
        </div>
      </div>

      {expanded && (
        <div className="mt-3 pl-6 animate-fade-in">
          <div className="border-t border-zinc-800/30 pt-3">
            <h4 className="text-[11px] text-zinc-600 uppercase tracking-wider mb-2">Signals</h4>
            <div className="flex flex-wrap gap-1.5">
              {rec.reasons.map((r, i) => (
                <span key={i} className="text-[11px] px-2 py-0.5 bg-zinc-800/40 text-zinc-500 rounded">
                  {r}
                </span>
              ))}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3">
              <Stat label="Avg confidence" value={`${(rec.avg_confidence * 100).toFixed(0)}%`} />
              <Stat label="Ship rate" value={`${(rec.ship_rate * 100).toFixed(0)}%`} />
              <Stat label="Spin score" value={`${rec.spin_score.toFixed(1)}x`} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-[10px] text-zinc-700 block">{label}</span>
      <span className="text-[13px] text-zinc-400 tabular-nums">{value}</span>
    </div>
  );
}

function ContextSwitchPanel({ data }: { data: ContextSwitchData | null }) {
  if (!data || data.weekly.length === 0) return null;

  const maxSessions = Math.max(...data.weekly.map(w => w.sessions), 1);

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Context Switches</h3>

      <div className="mb-3">
        <div className="flex items-baseline justify-between">
          <span className="text-[11px] text-zinc-700">Avg switch index</span>
          <span className={`text-[13px] tabular-nums ${data.avg_switch_index > 0.2 ? 'text-amber-700' : 'text-zinc-400'}`}>
            {(data.avg_switch_index * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      <div className="space-y-1.5">
        {data.weekly.map(w => (
          <div key={w.week} className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-700 w-16 shrink-0">{w.week}</span>
            <div className="flex-1 h-[6px] bg-zinc-800/40 rounded-full overflow-hidden">
              <div className="h-full flex">
                <div
                  className="h-full bg-zinc-600/50 rounded-l-full"
                  style={{ width: `${((w.sessions - w.multi_project_sessions) / maxSessions) * 100}%` }}
                />
                <div
                  className={`h-full ${w.zero_ship_multi > 0 ? 'bg-red-500/40' : 'bg-amber-400'}`}
                  style={{ width: `${(w.multi_project_sessions / maxSessions) * 100}%` }}
                />
              </div>
            </div>
            <span className="text-[10px] text-zinc-700 tabular-nums w-4 text-right">{w.sessions}</span>
          </div>
        ))}
      </div>

      <div className="flex gap-3 mt-3 text-[10px] text-zinc-700">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-zinc-600/50" /> focused
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm bg-amber-500/40" /> multi-project
        </span>
      </div>

      {data.flagged_sessions.length > 0 && (
        <div className="mt-4">
          <h4 className="text-[10px] text-zinc-700 uppercase tracking-wider mb-2">Flagged</h4>
          <div className="space-y-1.5">
            {data.flagged_sessions.slice(0, 5).map(s => (
              <div key={s.session_id} className="text-[11px]">
                <span className="text-zinc-600">{s.session_id.slice(0, 16)}</span>
                <span className="text-zinc-700 ml-1">({s.project_tags.length} projects, 0 shipped)</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FocusLegend() {
  return (
    <div className="border-t border-zinc-800/30 pt-4">
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Scoring</h3>
      <div className="space-y-2 text-[11px] text-zinc-700 leading-relaxed">
        <p><strong className="text-zinc-500">Spin score</strong> = sessions / shipped items. Over 3x = pure spin.</p>
        <p><strong className="text-zinc-500">Ship rate</strong> = approved / reviewed. 0% = no output.</p>
        <p><strong className="text-zinc-500">Days since output</strong> = last commit or approved cube.</p>
        <p><strong className="text-zinc-500">Urgency</strong> = spin + staleness + backlog + decay + momentum.</p>
      </div>
    </div>
  );
}
