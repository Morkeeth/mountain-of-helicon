import { useEffect, useState } from 'react';
import { api, type BatteryHistory } from '../api';
import DitherArea from './DitherArea';

/* Memory health over time - the ONE honest trend on the Memory tab.
   Every point is a real context-quality battery run (healthy_share), no
   interpolation, no backfill. The shape is carried by a hand-rolled Bayer-8
   dither (see DitherArea) - density rises with the value, so the trend reads
   without a gridline.

   Colour discipline: the improvement-orange is EARNED, not decorative. If the
   trend is up it lerps toward improve at the floor; if health has fallen the
   dither stays quiet slate, never orange. The delta obeys the same rule. */

export default function MemoryHealthTrend() {
  const [hist, setHist] = useState<BatteryHistory | null>(null);

  useEffect(() => {
    api.getBatteryHistory().then(setHist).catch(() => {});
  }, []);

  const pts = (hist?.points ?? []).filter((p) => p.healthy_share !== null);
  if (pts.length < 2) return null;

  const vals = pts.map((p) => Math.round((p.healthy_share as number) * 100));
  const now = vals[vals.length - 1];
  const delta = now - vals[0];
  const up = delta >= 0;

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

      <DitherArea
        series={vals}
        height={132}
        topColor={up ? '--helicon-improve' : '--helicon-muted'}
        botColor="--helicon-accent"
        topFallback={up ? '#C67C3E' : '#4E6173'}
        botFallback="#223A4E"
        ariaLabel={`Memory health over time: ${now}% of retrieval tasks served healthy context now, ${vals[0]}% at the first run across ${pts.length} battery runs, a change of ${delta >= 0 ? '+' : ''}${delta} points. The dithered area rises with the healthy share.`}
      />

      <div className="text-[11px] mt-3" style={{ color: 'var(--helicon-muted)' }}>
        One real point per battery run, no interpolation, no backfill. The curve is as young as the habit.
      </div>
    </div>
  );
}
