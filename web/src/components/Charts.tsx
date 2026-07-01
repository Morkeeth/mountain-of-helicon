import { useMemo } from 'react';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
  RadarChart, PolarGrid, PolarAngleAxis, Radar,
  LineChart, Line,
} from 'recharts';
import type { ScoreHistoryPoint, EvalRun, DecayStats } from '../api';

const ACCENT = '#3f3f46';
const ZINC_600 = '#9898ac';
const ZINC_800 = '#dcdce8';

function CustomTooltip({ active, payload, label }: { active?: boolean; payload?: { value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white border border-zinc-800/60 rounded-lg px-3 py-2 shadow-xl shadow-zinc-200/40 backdrop-blur-sm">
      <p className="text-[10px] text-zinc-500 mb-0.5">{label}</p>
      <p className="text-[13px] text-zinc-200 tabular-nums font-medium">{payload[0].value}%</p>
    </div>
  );
}

export function ScoreTimelineChart({ points }: { points: ScoreHistoryPoint[] }) {
  const data = useMemo(() =>
    points.map(p => ({
      date: p.recorded_at.slice(5, 10),
      score: Math.round(p.score),
      label: p.event_label,
    })),
    [points]
  );

  if (data.length === 0) return null;

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Score Timeline</h3>
      <ResponsiveContainer width="100%" height={160}>
        <AreaChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
          <defs>
            <linearGradient id="scoreGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={ACCENT} stopOpacity={0.25} />
              <stop offset="100%" stopColor={ACCENT} stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 9, fill: ZINC_600 }}
          />
          <YAxis
            domain={[0, 100]}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 9, fill: ZINC_600 }}
            ticks={[0, 25, 50, 75, 100]}
          />
          <Tooltip content={<CustomTooltip />} />
          <Area
            type="monotone"
            dataKey="score"
            stroke={ACCENT}
            strokeWidth={2}
            fill="url(#scoreGradient)"
            dot={{ r: 3, fill: ACCENT, strokeWidth: 0 }}
            activeDot={{ r: 5, fill: ACCENT, stroke: '#ffffff', strokeWidth: 2 }}
            animationDuration={1200}
            animationEasing="ease-out"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function ConfidenceDistribution({ cubes }: { cubes: { confidence: number }[] }) {
  const data = useMemo(() => {
    const buckets = Array.from({ length: 10 }, (_, i) => ({
      range: `${i * 10}-${(i + 1) * 10}%`,
      count: 0,
      bucket: i,
    }));
    for (const c of cubes) {
      const idx = Math.min(Math.floor(c.confidence * 10), 9);
      buckets[idx].count++;
    }
    return buckets;
  }, [cubes]);

  const barColor = (bucket: number) => {
    if (bucket < 2) return '#71717a';
    if (bucket < 5) return '#a1a1aa';
    return '#d4d4d8';
  };

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Confidence Distribution</h3>
      <ResponsiveContainer width="100%" height={120}>
        <BarChart data={data} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
          <XAxis
            dataKey="range"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 8, fill: ZINC_600 }}
            interval={1}
          />
          <YAxis
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 8, fill: ZINC_600 }}
          />
          <Bar dataKey="count" radius={[3, 3, 0, 0]} animationDuration={800}>
            {data.map(entry => (
              <Cell key={entry.range} fill={barColor(entry.bucket)} fillOpacity={0.5} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EvalRadar({ evalRun }: { evalRun: EvalRun }) {
  const data = useMemo(() => [
    { metric: 'P@3', value: evalRun.precision_at_3 * 100, fullMark: 100 },
    { metric: 'P@5', value: evalRun.precision_at_5 * 100, fullMark: 100 },
    { metric: 'MRR', value: evalRun.mrr * 100, fullMark: 100 },
    { metric: 'Forget', value: evalRun.forgetting_accuracy * 100, fullMark: 100 },
    { metric: 'Audit', value: evalRun.audit_recall * 100, fullMark: 100 },
  ], [evalRun]);

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-2">Eval Radar</h3>
      <ResponsiveContainer width="100%" height={200}>
        <RadarChart data={data} cx="50%" cy="50%" outerRadius="75%">
          <PolarGrid stroke={ZINC_800} />
          <PolarAngleAxis
            dataKey="metric"
            tick={{ fontSize: 10, fill: ZINC_600 }}
          />
          <Radar
            dataKey="value"
            stroke={ACCENT}
            fill={ACCENT}
            fillOpacity={0.15}
            strokeWidth={2}
            animationDuration={1000}
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function EvalTrendChart({ history }: { history: EvalRun[] }) {
  const data = useMemo(() =>
    [...history].reverse().map(r => ({
      date: r.run_at.slice(5, 16),
      p3: Math.round(r.precision_at_3 * 100),
      forget: Math.round(r.forgetting_accuracy * 100),
      audit: Math.round(r.audit_recall * 100),
    })),
    [history]
  );

  if (data.length < 2) return null;

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Eval Trend</h3>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -20 }}>
          <XAxis
            dataKey="date"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 8, fill: ZINC_600 }}
          />
          <YAxis
            domain={[0, 100]}
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 8, fill: ZINC_600 }}
          />
          <Line type="monotone" dataKey="p3" stroke={ACCENT} strokeWidth={1.5} dot={{ r: 2 }} name="P@3" />
          <Line type="monotone" dataKey="forget" stroke={'#71717a'} strokeWidth={1.5} dot={{ r: 2 }} name="Forget" />
          <Line type="monotone" dataKey="audit" stroke="#5c5c66" strokeWidth={1.5} dot={{ r: 2 }} name="Audit" />
        </LineChart>
      </ResponsiveContainer>
      <div className="flex gap-4 text-[10px] text-zinc-700 mt-1">
        <span className="flex items-center gap-1"><span className="w-3 h-[2px] rounded" style={{ background: '#3f3f46' }} /> P@3</span>
        <span className="flex items-center gap-1"><span className="w-3 h-[2px] rounded bg-zinc-500" /> Forget</span>
        <span className="flex items-center gap-1"><span className="w-3 h-[2px] rounded" style={{ background: '#5c5c66' }} /> Audit</span>
      </div>
    </div>
  );
}

export function DecayHeatmap({ stats }: { stats: DecayStats | null }) {
  if (!stats) return null;

  const entries = Object.entries(stats).sort((a, b) => a[1].avg_confidence - b[1].avg_confidence);
  const data = entries.map(([type, d]) => ({
    type,
    avg: Math.round(d.avg_confidence * 100),
    min: Math.round(d.min_confidence * 100),
    count: d.count,
  }));

  const getColor = (avg: number) => {
    if (avg < 20) return 'bg-zinc-400/40';
    if (avg < 50) return 'bg-zinc-400/25';
    return 'bg-zinc-400/15';
  };

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Memory Decay</h3>
      <div className="space-y-1.5">
        {data.map(d => (
          <div key={d.type} className="flex items-center gap-3 group">
            <span className="text-[11px] text-zinc-500 w-20 text-right shrink-0 truncate">{d.type}</span>
            <div className="flex-1 h-7 bg-zinc-800/30 rounded-md overflow-hidden relative">
              <div
                className={`h-full ${getColor(d.avg)} rounded-md transition-all duration-700 ease-out flex items-center`}
                style={{ width: `${d.avg}%` }}
              >
                <span className="text-[10px] text-zinc-400 ml-2 opacity-0 group-hover:opacity-100 transition-opacity">
                  {d.count} cubes
                </span>
              </div>
              <div
                className="absolute top-0 h-full w-[2px] bg-red-500/40"
                style={{ left: `${d.min}%` }}
                title={`min: ${d.min}%`}
              />
            </div>
            <span className="text-[11px] text-zinc-500 tabular-nums w-10 text-right">{d.avg}%</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-zinc-600 mt-2">red line = minimum confidence in type</p>
    </div>
  );
}

export function IngestionChart({ data }: { data: { day: string; added: number; source: string }[] }) {
  const grouped = useMemo(() => {
    const dayMap = new Map<string, number>();
    for (const r of data) {
      dayMap.set(r.day, (dayMap.get(r.day) || 0) + r.added);
    }
    return [...dayMap.entries()]
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([day, count]) => ({ day: day.slice(5), count }));
  }, [data]);

  if (grouped.length === 0) return null;

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Ingestion Timeline</h3>
      <ResponsiveContainer width="100%" height={100}>
        <BarChart data={grouped} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
          <XAxis
            dataKey="day"
            axisLine={false}
            tickLine={false}
            tick={{ fontSize: 8, fill: ZINC_600 }}
            interval={Math.max(0, Math.floor(grouped.length / 6))}
          />
          <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 8, fill: ZINC_600 }} />
          <Bar dataKey="count" fill={ACCENT} fillOpacity={0.4} radius={[2, 2, 0, 0]} animationDuration={600} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
