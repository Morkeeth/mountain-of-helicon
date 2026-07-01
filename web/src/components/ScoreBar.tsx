import type { Score } from '../api';

export function ScoreBar({ score }: { score: Score | null }) {
  if (!score) return null;
  const pct = score.score;
  const color = pct < 20 ? '#ef4444' : pct < 50 ? '#d97706' : '#3f3f46';

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Glaze Score</h3>
      <div className="flex items-baseline gap-2 mb-3">
        <span
          className="text-3xl font-light tabular-nums transition-colors duration-700"
          style={{ color: `${color}cc` }}
        >
          {pct}
        </span>
        <span className="text-[12px] text-zinc-700">/ 100</span>
      </div>
      <div className="w-full h-[4px] bg-zinc-800/60 rounded-full overflow-hidden mb-3">
        <div
          className="h-full rounded-full transition-all duration-1000 ease-out"
          style={{
            width: `${pct}%`,
            background: `linear-gradient(90deg, ${color}88, ${color}44)`,
          }}
        />
      </div>
      <div className="flex justify-between text-[11px] text-zinc-700">
        <span>{score.reviewed} reviewed</span>
        <span>{score.pending} pending</span>
      </div>
    </div>
  );
}
