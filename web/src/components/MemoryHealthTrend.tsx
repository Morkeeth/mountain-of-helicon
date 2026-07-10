import { useEffect, useState } from 'react';
import { api, type BatteryHistory, type BatteryHistoryPoint } from '../api';

/* Memory health over time — the ONE honest trend on the Memory tab.
   Every point is a real context-quality battery run (healthy_share), no
   interpolation, no backfill. Rendered as a themed SVG (bklit's line chart is
   fetched + available, but its @visx ParentSize does not measure under our
   headless verify path, so this card uses a plain, reliable SVG on the same
   real data). The delta since the first run is the only place the
   improvement-orange appears; a fall stays quiet slate. */

const W = 820;
const H = 150;
const PAD = { l: 6, r: 6, t: 14, b: 18 };

export default function MemoryHealthTrend() {
  const [hist, setHist] = useState<BatteryHistory | null>(null);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    api.getBatteryHistory().then(setHist).catch(() => {});
  }, []);

  const pts = (hist?.points ?? []).filter((p) => p.healthy_share !== null);
  if (pts.length < 2) return null;

  const vals = pts.map((p) => Math.round((p.healthy_share as number) * 100));
  const now = vals[vals.length - 1];
  const delta = now - vals[0];
  const up = delta >= 0;

  const x = (i: number) => PAD.l + (i / (pts.length - 1)) * (W - PAD.l - PAD.r);
  const y = (v: number) => PAD.t + (1 - v / 100) * (H - PAD.t - PAD.b);
  const line = vals.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(' ');
  const area = `${line} L${x(pts.length - 1).toFixed(1)} ${y(0).toFixed(1)} L${x(0).toFixed(1)} ${y(0).toFixed(1)} Z`;

  const fmt = (p: BatteryHistoryPoint) =>
    new Date(p.recorded_at + 'Z').toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

  return (
    <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
      <div className="flex items-baseline justify-between mb-1">
        <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: 'var(--helicon-muted)' }}>
          Memory health over time
        </div>
        <div className="text-[11px] tabular-nums" style={{ color: up ? 'var(--helicon-improve)' : 'var(--helicon-muted)' }}>
          {up ? '↑' : '↓'} {Math.abs(delta)} pts <span style={{ color: 'var(--helicon-muted)' }}>since first run</span>
        </div>
      </div>
      <div className="flex items-baseline gap-2 mb-4">
        <span
          className="tabular-nums"
          style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", fontSize: 44, lineHeight: 1, color: 'var(--helicon-ink)' }}
        >
          {now}
        </span>
        <span className="text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
          % of retrieval tasks served healthy context
        </span>
      </div>

      <div style={{ position: 'relative' }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', width: '100%' }} preserveAspectRatio="none">
          {[0, 50, 100].map((g) => (
            <line key={g} x1={PAD.l} x2={W - PAD.r} y1={y(g)} y2={y(g)} stroke="var(--helicon-line)" strokeWidth={1} />
          ))}
          <path d={area} fill="var(--helicon-accent)" opacity={0.06} />
          <path d={line} fill="none" stroke="var(--helicon-ink)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
          {vals.map((v, i) => (
            <g key={i}>
              <circle cx={x(i)} cy={y(v)} r={i === vals.length - 1 ? 4 : 2.5}
                fill={i === vals.length - 1 ? 'var(--helicon-accent)' : 'var(--helicon-ink)'} />
              <rect x={x(i) - 12} y={0} width={24} height={H} fill="transparent"
                onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} style={{ cursor: 'pointer' }} />
            </g>
          ))}
        </svg>
        {hover != null && (
          <div style={{
            position: 'absolute', left: `${(x(hover) / W) * 100}%`, top: 0,
            transform: 'translate(-50%, -108%)', background: 'var(--helicon-ink)', color: 'var(--helicon-panel)',
            borderRadius: 8, padding: '6px 9px', fontSize: 11, whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 5,
          }}>
            <b className="tabular-nums">{vals[hover]}%</b> healthy · {fmt(pts[hover])}
          </div>
        )}
      </div>

      <div className="text-[11px] mt-3" style={{ color: 'var(--helicon-muted)' }}>
        One real point per battery run — no interpolation, no backfill. The curve is as young as the habit.
      </div>
    </div>
  );
}
