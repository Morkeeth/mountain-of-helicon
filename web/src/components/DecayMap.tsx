import type { DecayStats } from '../api';

function barColor(avg: number): string {
  if (avg < 0.1) return 'bg-red-500';
  if (avg < 0.3) return 'bg-amber-500';
  if (avg < 0.6) return 'bg-violet-400';
  return 'bg-violet-300';
}

export function DecayMap({ stats }: { stats: DecayStats | null }) {
  if (!stats) return null;

  const entries = Object.entries(stats).sort((a, b) => a[1].avg_confidence - b[1].avg_confidence);

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Decay Map</h3>
      <div className="space-y-2.5">
        {entries.map(([type, data]) => (
          <div key={type} className="flex items-center gap-3">
            <span className="text-[11px] text-zinc-500 w-16 text-right shrink-0">{type}</span>
            <div className="flex-1 h-[6px] bg-zinc-800/40 rounded-sm overflow-hidden relative">
              <div
                className={`h-full ${barColor(data.avg_confidence)} rounded-sm transition-all`}
                style={{ width: `${data.avg_confidence * 100}%` }}
              />
            </div>
            <span className="text-[11px] text-zinc-600 tabular-nums w-8 text-right">{(data.avg_confidence * 100).toFixed(0)}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}
