import { useEffect, useMemo, useState } from 'react';
import { api, type BatteryReport, type BatteryTask, type SnapshotReport } from '../api';

/* Mountain-of-tesserae renderer, ported from web/helicon-tesserae.html.
   Memory renders as a summit of tonal stone tiles; terracotta appears ONLY on
   cracked tiles. Here the cracks are REAL: one per BROKEN/DEGRADED benchmark
   task from the live context-quality battery. Nothing is synthetic. */

const W = 360;
const H = 190;
const TILE = 9;
const GAP = 1;
const RIDGE_DRAMA = 0.5;
const PALETTE_SPREAD = 0.28;

// deterministic PRNG so the same verdicts always draw the same mountain
function mulberry32(seed: number) {
  return () => {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const hsl = (h: number, s: number, l: number) => `hsl(${h} ${s}% ${l}%)`;

// ridge elevation profile 0..1 across x (0..1): a main peak + subordinate ridges
function ridge(x: number, drama: number) {
  const base =
    0.3 +
    0.55 * Math.exp(-Math.pow((x - 0.42) / 0.2, 2)) +
    0.3 * Math.exp(-Math.pow((x - 0.72) / 0.13, 2)) +
    0.16 * Math.exp(-Math.pow((x - 0.15) / 0.12, 2)) +
    0.03 * Math.sin(x * 38);
  return 0.18 + base * (0.55 + drama * 0.7);
}

function buildMountain(crackCount: number, seed: number) {
  const rand = mulberry32(seed);
  const size = TILE;
  const g = GAP;
  const sp = PALETTE_SPREAD;
  const drama = RIDGE_DRAMA;
  const cols = Math.floor((W + g) / (size + g));
  const rows = Math.floor((H + g) / (size + g));
  let s = '';
  const ridgePts: [number, number][] = [];

  for (let c = 0; c < cols; c++) {
    const xf = c / (cols - 1);
    const rY = 1 - ridge(xf, drama);
    const startRow = Math.max(0, Math.round(rY * rows));
    ridgePts.push([g + c * (size + g), g + startRow * (size + g)]);
    for (let r = startRow; r < rows; r++) {
      const x = g + c * (size + g);
      const y = g + r * (size + g);
      const depth = (r - startRow) / (rows - startRow || 1);
      const hue = 208 - depth * 172; // slate summit -> warm stone base
      const sat = 6 + sp * 34;
      const light = 74 - depth * 20 + (rand() - 0.5) * 4;
      s += `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="0" fill="${hsl(hue, sat, light)}"/>`;
    }
  }

  // cracked tiles near the summit ridge — ONE per flagged task, terracotta fracture
  const groundL = 98;
  for (let k = 0; k < crackCount; k++) {
    const c = Math.floor(cols * (0.3 + rand() * 0.5));
    const xf = c / (cols - 1);
    const startRow = Math.max(0, Math.round((1 - ridge(xf, drama)) * rows));
    const r = startRow + Math.floor(rand() * 3);
    const x = g + c * (size + g);
    const y = g + r * (size + g);
    s += `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="0" fill="${hsl(40, 22, Math.min(97, groundL))}"/>`;
    s += `<path d="M${x + 1.5} ${y + size - 1.5} L${x + size * 0.55} ${y + 1.5} M${x + size * 0.42} ${
      y + size - 1.5
    } L${x + size - 1.5} ${y + 2.5}" stroke="var(--helicon-accent)" stroke-width="0.8"/>`;
  }

  const d = 'M' + ridgePts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L');
  const ridgeLine = `<path d="${d}" fill="none" stroke="${hsl(210, 14, 40)}" stroke-width="0.8" opacity="0.6" stroke-linejoin="round"/>`;
  const viewH = g + rows * (size + g);
  return { svg: ridgeLine + s, viewH };
}

const DOT: Record<string, string> = {
  BROKEN: 'var(--helicon-accent)',
  DEGRADED: 'var(--helicon-stale)',
};

function failSummary(t: BatteryTask): string {
  const fails = t.results.filter((r) => r.status === 'FAIL');
  if (!fails.length) return t.verdict.toLowerCase();
  return fails.map((f) => f.name).join(' · ').toLowerCase();
}

export default function HeliconMountain() {
  const [battery, setBattery] = useState<BatteryReport | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .getBattery()
      .then((b) => {
        if (!alive) return;
        setBattery(b);
      })
      .catch((e) => alive && setError(String(e)))
      .finally(() => alive && setLoading(false));
    api
      .getSnapshots()
      .then((s) => alive && setSnapshots(s))
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  const flagged = useMemo(
    () =>
      (battery?.tasks || [])
        .filter((t) => t.verdict !== 'HEALTHY')
        .sort((a) => (a.verdict === 'BROKEN' ? -1 : 1)),
    [battery]
  );

  const intact = battery && battery.total ? Math.round((battery.summary.healthy / battery.total) * 100) : 0;
  const { svg, viewH } = useMemo(() => buildMountain(flagged.length, (battery?.total || 0) * 100 + flagged.length), [
    flagged.length,
    battery?.total,
  ]);

  return (
    <div
      className="rounded-2xl p-7 helicon-surface"
      style={{
        background: 'var(--helicon-bg)',
        color: 'var(--helicon-ink)',
        boxShadow: '0 20px 60px rgba(50,40,28,.14)',
      }}
    >
      <div className="flex items-baseline gap-3 mb-1">
        <b
          style={{
            fontFamily: 'var(--helicon-serif)',
            fontWeight: 300,
            fontSize: 26,
            letterSpacing: '0.02em',
            textTransform: 'uppercase',
            fontVariationSettings: "'opsz' 144",
          }}
        >
          Helicon
        </b>
        <em style={{ fontStyle: 'normal', fontSize: 9.5, letterSpacing: '0.36em', textTransform: 'uppercase', color: 'var(--helicon-accent)', opacity: 0.85 }}>
          tesserae
        </em>
      </div>
      <div style={{ fontSize: 12.5, lineHeight: 1.6, color: '#6f665a', maxWidth: '42ch', margin: '10px 0 22px' }}>
        Your agent's memory is a mountain built of tiles. Helicon shows you the moment one starts to crack. Every crack
        below is a real benchmark task whose retrieved context is degraded or broken.
      </div>

      {error && <div style={{ fontSize: 12, color: 'var(--helicon-accent)' }}>Could not load integrity data: {error}</div>}
      {loading && !battery && (
        <div style={{ fontSize: 12, color: 'var(--helicon-muted)' }}>Running the context-quality battery on live memory…</div>
      )}

      {battery && (
        <>
          <div style={{ background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', borderRadius: 14, padding: '20px 20px 12px' }}>
            <div className="flex items-baseline justify-between mb-1">
              <b style={{ fontFamily: 'var(--helicon-serif)', fontSize: 30, fontWeight: 400, fontVariationSettings: "'opsz' 144" }}>
                {intact}
                <i style={{ fontStyle: 'normal', color: 'var(--helicon-accent)' }}>%</i>
              </b>
              <span style={{ fontSize: 10, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
                mosaic intact · {battery.summary.healthy}/{battery.total} tasks healthy
              </span>
            </div>
            <svg style={{ display: 'block', width: '100%' }} viewBox={`0 0 ${W} ${viewH}`} dangerouslySetInnerHTML={{ __html: svg }} />
          </div>

          <div style={{ fontSize: 9.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--helicon-muted)', margin: '20px 0 4px' }}>
            {flagged.length ? `Flagged — ${flagged.length} task${flagged.length > 1 ? 's' : ''} cracking` : 'All benchmark tasks healthy'}
          </div>
          {flagged.map((t) => (
            <div
              key={t.task}
              className="flex items-center gap-3"
              style={{ fontSize: 13, padding: '10px 0', borderTop: '1px solid var(--helicon-line)', color: '#443e36' }}
            >
              <span style={{ width: 7, height: 7, borderRadius: 1, flex: 'none', background: DOT[t.verdict] || 'var(--helicon-conflict)' }} />
              <span style={{ fontWeight: 600 }}>{t.task}</span>
              <span style={{ color: 'var(--helicon-muted)' }}>· {failSummary(t)}</span>
            </div>
          ))}

          {snapshots && snapshots.total > 0 && (
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 18 }}>
              Snapshots: {snapshots.clean}/{snapshots.total} clean vs baseline
              {snapshots.regressed > 0 ? `, ${snapshots.regressed} regressed` : ''}.
            </div>
          )}
          {snapshots && snapshots.total === 0 && (
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 18 }}>
              No context snapshots captured yet — run <code>glaze snapshot add "&lt;task&gt;"</code> to baseline retrieval and catch regressions.
            </div>
          )}
        </>
      )}
    </div>
  );
}
