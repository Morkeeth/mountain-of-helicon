import { useEffect, useMemo, useState } from 'react';
import { api, type BatteryHistory, type BatteryHistoryPoint, type BatteryReport, type BatteryTask, type SnapshotReport } from '../api';

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

// A hover target: one tessera tied to one real battery task
interface TaskTile {
  x: number;
  y: number;
  size: number;
  task: BatteryTask;
}

function buildMountain(crackTasks: BatteryTask[], healthyTasks: BatteryTask[], seed: number) {
  const rand = mulberry32(seed);
  const size = TILE;
  const g = GAP;
  const sp = PALETTE_SPREAD;
  const drama = RIDGE_DRAMA;
  const cols = Math.floor((W + g) / (size + g));
  const rows = Math.floor((H + g) / (size + g));
  let s = '';
  const ridgePts: [number, number][] = [];
  const startRows: number[] = [];

  for (let c = 0; c < cols; c++) {
    const xf = c / (cols - 1);
    const rY = 1 - ridge(xf, drama);
    const startRow = Math.max(0, Math.round(rY * rows));
    startRows.push(startRow);
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

  const tiles: TaskTile[] = [];

  // cracked tiles near the summit ridge — ONE per flagged task, terracotta fracture
  const groundL = 98;
  for (let k = 0; k < crackTasks.length; k++) {
    const c = Math.floor(cols * (0.3 + rand() * 0.5));
    const startRow = startRows[c];
    const r = startRow + Math.floor(rand() * 3);
    const x = g + c * (size + g);
    const y = g + r * (size + g);
    s += `<rect x="${x}" y="${y}" width="${size}" height="${size}" rx="0" fill="${hsl(40, 22, Math.min(97, groundL))}"/>`;
    s += `<path d="M${x + 1.5} ${y + size - 1.5} L${x + size * 0.55} ${y + 1.5} M${x + size * 0.42} ${
      y + size - 1.5
    } L${x + size - 1.5} ${y + 2.5}" stroke="var(--helicon-accent)" stroke-width="0.8"/>`;
    tiles.push({ x, y, size, task: crackTasks[k] });
  }

  // healthy tasks map onto ridge-top tesserae, spread across the summit line
  for (let k = 0; k < healthyTasks.length; k++) {
    const c = Math.min(cols - 1, Math.floor(((k + 0.5) / healthyTasks.length) * cols));
    const x = g + c * (size + g);
    const y = g + startRows[c] * (size + g);
    tiles.push({ x, y, size, task: healthyTasks[k] });
  }

  const d = 'M' + ridgePts.map((p) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' L');
  const ridgeLine = `<path d="${d}" fill="none" stroke="${hsl(210, 14, 40)}" stroke-width="0.8" opacity="0.6" stroke-linejoin="round"/>`;
  const viewH = g + rows * (size + g);
  return { svg: ridgeLine + s, viewH, tiles };
}

const DOT: Record<string, string> = {
  BROKEN: 'var(--helicon-accent)',
  DEGRADED: 'var(--helicon-stale)',
};

/* Degradation-over-time: % of benchmark tasks serving healthy context, one
   real point per battery run (dashboard load or `helicon report`). No
   interpolation, no backfill — the curve is as long as the tool has run.
   This is the on-screen answer to "Is your AI agent getting dumber?" */
function DegradationCurve({ history }: { history: BatteryHistory }) {
  const [hover, setHover] = useState<BatteryHistoryPoint | null>(null);
  const pts = history.points.filter((p) => p.healthy_share !== null);
  if (!pts.length) return null;

  const CW = 360;
  const CH = 110;
  const PAD = { l: 34, r: 12, t: 10, b: 18 };
  const plotW = CW - PAD.l - PAD.r;
  const plotH = CH - PAD.t - PAD.b;
  const ts = (p: BatteryHistoryPoint) => new Date(p.recorded_at + 'Z').getTime();
  const t0 = ts(pts[0]);
  const span = Math.max(1, ts(pts[pts.length - 1]) - t0);
  const px = (p: BatteryHistoryPoint) =>
    pts.length === 1 ? PAD.l + plotW / 2 : PAD.l + ((ts(p) - t0) / span) * plotW;
  const py = (share: number) => PAD.t + (1 - share) * plotH;
  const line = pts.map((p, i) => `${i ? 'L' : 'M'}${px(p).toFixed(1)} ${py(p.healthy_share!).toFixed(1)}`).join(' ');
  const fmt = (iso: string) => {
    const d = new Date(iso + 'Z');
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };
  const latest = pts[pts.length - 1];

  return (
    <div style={{ marginTop: 22 }}>
      <div className="flex items-baseline justify-between" style={{ marginBottom: 4 }}>
        <span style={{ fontSize: 9.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
          Is your agent getting dumber?
        </span>
        <b style={{ fontFamily: 'var(--helicon-serif)', fontSize: 18, fontWeight: 400, fontVariationSettings: "'opsz' 144" }}>
          {Math.round((latest.healthy_share ?? 0) * 100)}
          <i style={{ fontStyle: 'normal', color: 'var(--helicon-accent)', fontSize: 13 }}>%</i>
          <span style={{ fontSize: 10, color: 'var(--helicon-muted)', letterSpacing: '0.08em', marginLeft: 6 }}>healthy now</span>
        </b>
      </div>
      <div style={{ position: 'relative', background: 'var(--helicon-panel)', border: '1px solid var(--helicon-line)', borderRadius: 10, padding: '6px 4px 2px' }}>
        <svg style={{ display: 'block', width: '100%' }} viewBox={`0 0 ${CW} ${CH}`}>
          {[0, 0.5, 1].map((g) => (
            <g key={g}>
              <line x1={PAD.l} x2={CW - PAD.r} y1={py(g)} y2={py(g)} stroke="var(--helicon-line)" strokeWidth={0.6} />
              <text x={PAD.l - 5} y={py(g) + 3} textAnchor="end" fontSize={7.5} fill="var(--helicon-muted)">
                {Math.round(g * 100)}%
              </text>
            </g>
          ))}
          <path d={line} fill="none" stroke="var(--helicon-ink)" strokeWidth={1.6} strokeLinejoin="round" strokeLinecap="round" />
          {pts.map((p, i) => (
            <g key={p.recorded_at + i}>
              <circle cx={px(p)} cy={py(p.healthy_share!)} r={i === pts.length - 1 ? 3.4 : 2.6}
                fill={i === pts.length - 1 ? 'var(--helicon-accent)' : 'var(--helicon-ink)'}
                stroke="var(--helicon-panel)" strokeWidth={1} />
              <circle cx={px(p)} cy={py(p.healthy_share!)} r={9} fill="transparent" style={{ cursor: 'pointer' }}
                onMouseEnter={() => setHover(p)} onMouseLeave={() => setHover(null)} />
            </g>
          ))}
          <text x={PAD.l} y={CH - 5} fontSize={7.5} fill="var(--helicon-muted)">{fmt(pts[0].recorded_at)}</text>
          {pts.length > 1 && (
            <text x={CW - PAD.r} y={CH - 5} textAnchor="end" fontSize={7.5} fill="var(--helicon-muted)">
              {fmt(latest.recorded_at)}
            </text>
          )}
        </svg>
        {hover && (
          <div
            style={{
              position: 'absolute',
              left: `${(px(hover) / CW) * 100}%`,
              top: `${(py(hover.healthy_share!) / CH) * 100}%`,
              transform: 'translate(-50%, calc(-100% - 8px))',
              background: 'var(--helicon-ink)', color: 'var(--helicon-bg)',
              borderRadius: 8, padding: '6px 9px', fontSize: 11, lineHeight: 1.5,
              whiteSpace: 'nowrap', pointerEvents: 'none', zIndex: 10,
              boxShadow: '0 6px 18px rgba(43,40,37,.28)',
            }}
          >
            <div style={{ fontWeight: 600 }}>{fmt(hover.recorded_at)}</div>
            <div style={{ opacity: 0.8 }}>
              {hover.healthy}/{hover.total} healthy · {hover.degraded} degraded · {hover.broken} broken · ~{hover.mean_tokens} tok/query
            </div>
          </div>
        )}
      </div>
      <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 6 }}>
        One real point per battery run — no interpolation, no backfill. The curve is as young as the habit.
      </div>
    </div>
  );
}

function failSummary(t: BatteryTask): string {
  const fails = t.results.filter((r) => r.status === 'FAIL');
  if (!fails.length) return t.verdict.toLowerCase();
  return fails.map((f) => f.name).join(' · ').toLowerCase();
}

export default function HeliconMountain() {
  const [battery, setBattery] = useState<BatteryReport | null>(null);
  const [history, setHistory] = useState<BatteryHistory | null>(null);
  const [snapshots, setSnapshots] = useState<SnapshotReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hovered, setHovered] = useState<TaskTile | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .getBattery()
      .then((b) => {
        if (!alive) return;
        setBattery(b);
        // fetch AFTER the battery run so the point it just recorded is included
        api.getBatteryHistory().then((h) => alive && setHistory(h)).catch(() => {});
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

  const healthy = useMemo(() => (battery?.tasks || []).filter((t) => t.verdict === 'HEALTHY'), [battery]);

  const intact = battery && battery.total ? Math.round((battery.summary.healthy / battery.total) * 100) : 0;
  const { svg, viewH, tiles } = useMemo(
    () => buildMountain(flagged, healthy, (battery?.total || 0) * 100 + flagged.length),
    [flagged, healthy, battery?.total]
  );

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
          Mount Helicon
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
                mosaic intact · {battery.summary.healthy} healthy
                {' / '}
                <span style={{ color: battery.summary.degraded ? 'var(--helicon-stale)' : undefined }}>{battery.summary.degraded} degraded</span>
                {' / '}
                <span style={{ color: battery.summary.broken ? 'var(--helicon-accent)' : undefined }}>{battery.summary.broken} broken</span>
              </span>
            </div>
            <div style={{ position: 'relative' }}>
              <svg style={{ display: 'block', width: '100%' }} viewBox={`0 0 ${W} ${viewH}`}>
                <g dangerouslySetInnerHTML={{ __html: svg }} />
                {tiles.map((tile, i) => (
                  <rect
                    key={`${tile.task.task}-${i}`}
                    x={tile.x - 1}
                    y={tile.y - 1}
                    width={tile.size + 2}
                    height={tile.size + 2}
                    fill="transparent"
                    stroke={hovered === tile ? 'var(--helicon-ink)' : 'none'}
                    strokeWidth={0.6}
                    style={{ cursor: 'pointer' }}
                    onMouseEnter={() => setHovered(tile)}
                    onMouseLeave={() => setHovered(null)}
                  />
                ))}
              </svg>
              {hovered && (() => {
                const fails = hovered.task.results.filter((r) => r.status === 'FAIL');
                const below = hovered.y < viewH * 0.3; // summit tiles: flip tooltip under the tile
                return (
                  <div
                    style={{
                      position: 'absolute',
                      left: `${((hovered.x + hovered.size / 2) / W) * 100}%`,
                      top: `${((below ? hovered.y + hovered.size : hovered.y) / viewH) * 100}%`,
                      transform: below ? 'translate(-50%, 8px)' : 'translate(-50%, calc(-100% - 8px))',
                      background: 'var(--helicon-ink)',
                      color: 'var(--helicon-bg)',
                      borderRadius: 8,
                      padding: '7px 10px',
                      fontSize: 11,
                      lineHeight: 1.5,
                      maxWidth: 260,
                      pointerEvents: 'none',
                      zIndex: 10,
                      boxShadow: '0 6px 18px rgba(43,40,37,.28)',
                    }}
                  >
                    <div style={{ fontWeight: 600 }}>{hovered.task.task}</div>
                    <div style={{ opacity: 0.8 }}>
                      {hovered.task.verdict.toLowerCase()}
                      {fails.length > 0 ? ` — failing: ${fails.map((f) => f.name).join(', ')}` : ' — all checks passing'}
                    </div>
                  </div>
                );
              })()}
            </div>
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 10 }}>
              Each tessera is a retrieval task. Cracks mark tasks serving broken memory.
            </div>
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

          {history && <DegradationCurve history={history} />}

          {snapshots && snapshots.total > 0 && (
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 18 }}>
              Snapshots: {snapshots.clean}/{snapshots.total} clean vs baseline
              {snapshots.regressed > 0 ? `, ${snapshots.regressed} regressed` : ''}.
            </div>
          )}
          {snapshots && snapshots.total === 0 && (
            <div style={{ fontSize: 11, color: 'var(--helicon-muted)', marginTop: 18 }}>
              No context snapshots captured yet — run <code>helicon snapshot add "&lt;task&gt;"</code> to baseline retrieval and catch regressions.
            </div>
          )}
        </>
      )}
    </div>
  );
}
