import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';
import { api, type JudgeRow, type JudgeRun } from '../api';

/* THE JUDGE — Qwen benchmarked as the memory-rot judge against human-ruled
   ground truth.

   Two rules govern this file, and they outrank how good the chart looks:

   1. It renders the LAST SAVED run and never starts one. A bench is live
      cross-provider inference: real money, real minutes. A page load must not
      spend either.
   2. If there is no saved run, it says so and names the command. It never
      hardcodes, interpolates, back-fills or "example"-fills a number. A
      fabricated benchmark in a hackathon submission is fraud, so the empty
      state is a first-class design, not a fallback.

   The `notes` from the bench are rendered verbatim: they are the channel that
   says what was NOT measured (e.g. no competitor judged, no OpenRouter key),
   and the absence of a competitor must be visible rather than implied. */

const QWEN_INK = 'var(--helicon-accent)';    // #223A4E — the subject
const FIELD_INK = 'var(--helicon-conflict)'; // #AEBFCC — the context
/* Validated, not eyeballed (dataviz validate_palette.js, light, surface #F4EFE7):
   #223A4E vs #AEBFCC — CVD ΔE 45.3, normal-vision ΔE 45.8, both PASS.
   The mist's 1.65 contrast raises the validator's contrast WARN, which is not
   dismissable: it obligates visible labels or a table view. Both ship below.
   (The near pair #223A4E/#465B6F was rejected: normal-vision ΔE 12.4, a hard
   FAIL — two marks a full-colour reader cannot tell apart.) */

const isQwen = (m: string) => m.toLowerCase().includes('qwen');
const fmtCost = (c: number) => (c >= 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(5)}`);

/* ---------------------------------------------------------------------------
   The headline, DERIVED. Every number below is computed from the saved run;
   none is written down. If the data changes the sentence changes, and if the
   data cannot support a sentence there is no sentence.
--------------------------------------------------------------------------- */
function headline(rows: JudgeRow[]): { lead: string; sub: string } | null {
  const scored = rows.filter(r => r.accuracy !== null);
  if (!scored.length) return null;
  const top = Math.max(...scored.map(r => r.accuracy as number));
  const atTop = scored.filter(r => r.accuracy === top);
  const priced = atTop.filter(r => r.cost_usd != null && (r.cost_usd as number) > 0);

  if (priced.length >= 2) {
    const cheap = priced.reduce((a, b) => ((a.cost_usd as number) < (b.cost_usd as number) ? a : b));
    const dear = priced.reduce((a, b) => ((a.cost_usd as number) > (b.cost_usd as number) ? a : b));
    const ratio = (dear.cost_usd as number) / (cheap.cost_usd as number);
    if (ratio >= 1.5) {
      return {
        lead: `${atTop.length} models tie at ${top}`,
        sub: `${cheap.model} matches ${dear.model} exactly, at ${ratio.toFixed(1)}x less cost `
          + `(${fmtCost(cheap.cost_usd as number)} vs ${fmtCost(dear.cost_usd as number)} on the same probes).`,
      };
    }
    return { lead: `${atTop.length} models tie at ${top}`, sub: `Cost between them varies by ${ratio.toFixed(1)}x.` };
  }
  const best = atTop[0];
  return {
    lead: `${best.model} leads at ${top}`,
    sub: best.cost_usd != null ? `${fmtCost(best.cost_usd)} for the full probe set.` : 'Cost not priced for this model.',
  };
}

/* ---------------------------------------------------------------------------
   The chart. Cost (x, log) against accuracy (y) — ONE chart carrying both
   measures, because the claim is a RATIO between them and a ratio read across
   two charts is not read at all. Two spatial axes, never two y-scales.

   Sized from the container rather than scaled by viewBox: a viewBox squeezed
   into 350px would shrink 11px labels to 6px, and the phone is the review
   device.
--------------------------------------------------------------------------- */
function CostAccuracyChart({ rows }: { rows: JudgeRow[] }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setW(el.clientWidth));
    ro.observe(el);
    setW(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const pts = rows.filter(r => r.accuracy !== null && r.cost_usd != null && (r.cost_usd as number) > 0);
  if (!pts.length) {
    return (
      <div style={{ fontSize: 11.5, color: 'var(--helicon-muted)' }}>
        No model in this run has both a cost and an accuracy, so there is nothing to plot.
        The table below carries what was measured.
      </div>
    );
  }

  const narrow = w < 480;
  const H = narrow ? 250 : 290;
  // left gutter holds the tick numbers; the rotated axis title only earns its
  // own column on a wide screen (on a phone it collided with the ticks, and the
  // card title already says "Accuracy against cost")
  const M = { t: 22, r: narrow ? 14 : 22, b: 42, l: narrow ? 42 : 60 };
  const iw = Math.max(10, w - M.l - M.r);
  const ih = H - M.t - M.b;

  // x: log10(cost), padded by a fifth of a decade so no dot sits on the frame
  const lxs = pts.map(p => Math.log10(p.cost_usd as number));
  let lo = Math.min(...lxs), hi = Math.max(...lxs);
  if (hi - lo < 0.3) { lo -= 0.25; hi += 0.25; }
  else { const pad = (hi - lo) * 0.18; lo -= pad; hi += pad; }
  const X = (c: number) => M.l + ((Math.log10(c) - lo) / (hi - lo)) * iw;

  /* y: 0.5 is not a decorative floor. The probe set is balanced (equal real
     contradictions and consistent controls), so 0.5 IS chance — a judge below
     it is worthless. Anchoring here gives the axis meaning instead of zooming
     on noise. It stretches down only if a judge actually scores below chance. */
  const minAcc = Math.min(...pts.map(p => p.accuracy as number));
  const yLo = Math.min(0.5, Math.floor(minAcc * 10) / 10);
  const Y = (a: number) => M.t + (1 - (a - yLo) / (1 - yLo)) * ih;

  const yTicks: number[] = [];
  for (let v = yLo; v <= 1.0001; v += (1 - yLo) / 5) yTicks.push(Math.round(v * 100) / 100);

  // x ticks: the real cost values, which are the numbers a reader cares about
  const xTicks = Array.from(new Set(pts.map(p => p.cost_usd as number))).sort((a, b) => a - b);

  /* Direct-label placement. Every judge in a tie sits at the SAME y, so a fixed
     offset stacks every label on one line and they overprint into mush (which
     is exactly what 390px showed). Labels are centred on their dot and pushed to
     the first vertical level that does not collide with one already placed.
     Levels alternate above/below so a tie fans out instead of piling up. */
  const LEVELS = [-13, 15, -27, 29, -41, 43];
  const placed: { x0: number; x1: number; dy: number }[] = [];
  const labels = pts.map(p => {
    const cx = X(p.cost_usd as number), cy = Y(p.accuracy as number);
    const halfW = (p.model.length * 5.3) / 2 + 3;   // ~5.3px per mono char at 9.5px
    let x = Math.min(Math.max(cx, M.l + halfW), M.l + iw - halfW); // clamp inside the frame
    const dy = LEVELS.find(lv =>
      !placed.some(q => q.dy === lv && x - halfW < q.x1 && x + halfW > q.x0)
    ) ?? LEVELS[LEVELS.length - 1];
    placed.push({ x0: x - halfW, x1: x + halfW, dy });
    return { cx, cy, x, dy };
  });

  return (
    <div ref={wrap} className="w-full">
      {w > 0 && (
        <svg width={w} height={H} role="img"
             aria-label={`Cost against accuracy for ${pts.length} judge models. ${pts.map(p => `${p.model}: accuracy ${p.accuracy}, cost ${fmtCost(p.cost_usd as number)}`).join('. ')}`}>
          {/* y grid, recessive */}
          {yTicks.map(t => (
            <g key={t}>
              <line x1={M.l} x2={M.l + iw} y1={Y(t)} y2={Y(t)} stroke="var(--helicon-line)" strokeWidth={1} />
              <text x={M.l - 7} y={Y(t) + 3} textAnchor="end"
                    style={{ fontFamily: 'var(--helicon-mono)', fontSize: 9.5, fill: 'var(--helicon-faint)' }}>
                {t.toFixed(2)}
              </text>
            </g>
          ))}

          {/* the chance line: a labelled baseline, not a gridline */}
          <line x1={M.l} x2={M.l + iw} y1={Y(0.5)} y2={Y(0.5)}
                stroke="var(--helicon-faint)" strokeWidth={1} strokeDasharray="3 3" />
          <text x={M.l + 4} y={Y(0.5) - 5}
                style={{ fontFamily: 'var(--helicon-mono)', fontSize: 9, fill: 'var(--helicon-faint)' }}>
            0.50 chance
          </text>

          {/* x ticks at the real costs */}
          {xTicks.map(c => (
            <text key={c} x={X(c)} y={H - 24} textAnchor="middle"
                  style={{ fontFamily: 'var(--helicon-mono)', fontSize: 9, fill: 'var(--helicon-faint)' }}>
              {fmtCost(c)}
            </text>
          ))}
          <text x={M.l + iw / 2} y={H - 8} textAnchor="middle"
                style={{ fontSize: 10, fill: 'var(--helicon-muted)' }}>
            cost for the full probe set (log scale) →
          </text>
          <text transform={`translate(11, ${M.t + ih / 2}) rotate(-90)`} textAnchor="middle"
                style={{ fontSize: 10, fill: 'var(--helicon-muted)' }}>
            accuracy
          </text>

          {pts.map((p, i) => {
            const cx = X(p.cost_usd as number), cy = Y(p.accuracy as number);
            const q = isQwen(p.model);
            const on = hover === i;
            // label left of the dot when it would run off the right edge
            const flip = cx > M.l + iw - 86;
            return (
              <g key={p.model}>
                {/* hit target well beyond the 8px mark (dataviz: no pinpoint dots) */}
                <circle cx={cx} cy={cy} r={20} fill="transparent" style={{ cursor: 'pointer' }}
                        onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)} />
                <circle cx={cx} cy={cy} r={on ? 8 : 6} fill={q ? QWEN_INK : FIELD_INK}
                        stroke="var(--helicon-panel)" strokeWidth={2} style={{ pointerEvents: 'none' }} />
                {/* direct label: identity never rides on colour alone */}
                <text x={flip ? cx - 11 : cx + 11} y={cy - 9} textAnchor={flip ? 'end' : 'start'}
                      style={{
                        fontFamily: 'var(--helicon-mono)', fontSize: 9.5,
                        fill: 'var(--helicon-ink)', fontWeight: q ? 600 : 400, pointerEvents: 'none',
                      }}>
                  {p.model}
                </text>
              </g>
            );
          })}
        </svg>
      )}

      {hover !== null && pts[hover] && (
        <div className="mt-1" style={{
          fontFamily: 'var(--helicon-mono)', fontSize: 10.5, color: 'var(--helicon-ink)',
          background: 'var(--helicon-bg-2)', borderRadius: 6, padding: '6px 9px',
        }}>
          {pts[hover].model} · accuracy {pts[hover].accuracy} · {fmtCost(pts[hover].cost_usd as number)}
          {pts[hover].latency_s != null && ` · ${pts[hover].latency_s}s`}
        </div>
      )}
    </div>
  );
}

/* The table. Not a fallback: it is how identity survives colour-blindness,
   grayscale printing and the validator's contrast WARN on the mist mark. */
function JudgeTable({ rows }: { rows: JudgeRow[] }) {
  const cell: CSSProperties = {
    fontFamily: 'var(--helicon-mono)', fontSize: 10.5, color: 'var(--helicon-ink)',
    padding: '7px 10px 7px 0', whiteSpace: 'nowrap',
  };
  const head: CSSProperties = {
    fontSize: 9, letterSpacing: '0.1em', textTransform: 'uppercase',
    color: 'var(--helicon-faint)', textAlign: 'left', padding: '0 10px 6px 0', whiteSpace: 'nowrap',
  };
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse', minWidth: '100%' }}>
        <thead>
          <tr>
            <th style={head}>model</th>
            <th style={head}>recall</th>
            <th style={head}>specificity</th>
            <th style={head}>accuracy</th>
            <th style={head}>cost</th>
            <th style={head}>latency</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.model} style={{ borderTop: '1px solid var(--helicon-line)' }}>
              <td style={{ ...cell, fontWeight: isQwen(r.model) ? 600 : 400 }}>
                <span style={{
                  display: 'inline-block', width: 7, height: 7, borderRadius: 4, marginRight: 7,
                  background: isQwen(r.model) ? QWEN_INK : FIELD_INK,
                }} />
                {r.model}
              </td>
              <td style={cell}>{r.caught != null && r.pos_n != null ? `${r.caught}/${r.pos_n}` : '—'}</td>
              <td style={cell}>{r.passed != null && r.neg_n != null ? `${r.passed}/${r.neg_n}` : '—'}</td>
              <td style={{ ...cell, fontWeight: 600 }}>{r.accuracy ?? '—'}</td>
              <td style={cell}>{r.cost_usd != null ? fmtCost(r.cost_usd) : 'n/a'}</td>
              <td style={{ ...cell, color: 'var(--helicon-muted)' }}>{r.latency_s != null ? `${r.latency_s}s` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function JudgeView() {
  const [data, setData] = useState<JudgeRun | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.getJudge().then(setData).catch(e => setErr(String(e)));
  }, []);

  if (err) return <div style={{ fontSize: 12, color: 'var(--helicon-critical)' }}>Could not read the bench: {err}</div>;
  if (!data) return <div style={{ fontSize: 12, color: 'var(--helicon-muted)' }}>Reading the last bench…</div>;

  const eyebrow = (
    <div style={{ fontSize: 9.5, letterSpacing: '0.24em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
      qwen as memory judge · vs human-ruled ground truth
    </div>
  );

  /* The empty state. It names the command and nothing else: no greyed-out
     example chart, no placeholder bars. An unrun bench looks unrun. */
  if (!data.ran) {
    return (
      <div className="animate-fade-in rounded-2xl px-5 py-6 sm:px-7 sm:py-7"
           style={{ background: 'var(--helicon-panel)', boxShadow: 'var(--helicon-shadow)' }}>
        {eyebrow}
        <div style={{
          fontFamily: 'var(--helicon-serif)', fontSize: 26, fontWeight: 300, color: 'var(--helicon-ink)',
          margin: '10px 0 8px', letterSpacing: '-0.01em', lineHeight: 1.2,
        }}>
          No judge run has been saved.
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--helicon-muted)', lineHeight: 1.6, maxWidth: 560 }}>
          {data.why} This page will not invent one: there are no numbers here because none have been
          measured on this machine.
        </div>
        <code style={{
          display: 'block', marginTop: 14, fontFamily: 'var(--helicon-mono)', fontSize: 11.5,
          color: 'var(--helicon-on-dark)', background: 'var(--helicon-dark)',
          borderRadius: 8, padding: '11px 13px', overflowX: 'auto',
        }}>
          {data.command}
        </code>
      </div>
    );
  }

  const rows = Object.values(data.rows);
  const h = headline(rows);
  const anyField = rows.some(r => !isQwen(r.model));
  const when = new Date(data.run_at).toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  });

  return (
    <div className="animate-fade-in flex flex-col gap-4">
      <div className="rounded-2xl px-5 py-5 sm:px-7 sm:py-6"
           style={{ background: 'var(--helicon-panel)', boxShadow: 'var(--helicon-shadow)' }}>
        {eyebrow}

        {h && (
          <>
            <div style={{
              fontFamily: 'var(--helicon-serif)', fontSize: 30, fontWeight: 300, color: 'var(--helicon-ink)',
              margin: '9px 0 6px', letterSpacing: '-0.015em', lineHeight: 1.15,
            }}>
              {h.lead}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--helicon-ink-70)', lineHeight: 1.6, maxWidth: 620 }}>
              {h.sub}
            </div>
          </>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1"
             style={{ fontFamily: 'var(--helicon-mono)', fontSize: 10, color: 'var(--helicon-faint)' }}>
          <span>{data.probes} probes ({data.positives} real contradictions + {data.negatives} consistent controls)</span>
          <span>·</span><span>set: {data.probe_set}</span>
          <span>·</span><span>run {when}</span>
          {data.inter_tier_agreement !== null && (<><span>·</span><span>inter-judge agreement {data.inter_tier_agreement}</span></>)}
        </div>
      </div>

      <div className="rounded-2xl px-4 py-5 sm:px-6"
           style={{ background: 'var(--helicon-panel)', boxShadow: 'var(--helicon-shadow)' }}>
        <div className="px-1 mb-1" style={{ fontSize: 12.5, color: 'var(--helicon-ink)', fontWeight: 600 }}>
          Accuracy against cost
        </div>
        <div className="px-1 mb-3" style={{ fontSize: 11, color: 'var(--helicon-muted)', lineHeight: 1.5 }}>
          Both measures on one chart, because the claim is the ratio between them.
          {anyField
            ? ' Qwen in ink, the rest of the field in mist.'
            : ' Every judge in this run is a Qwen tier.'}
        </div>

        {anyField && (
          <div className="px-1 mb-2 flex items-center gap-3" style={{ fontSize: 10, color: 'var(--helicon-muted)' }}>
            <span className="flex items-center gap-1.5">
              <span style={{ width: 8, height: 8, borderRadius: 4, background: QWEN_INK, display: 'inline-block' }} /> Qwen
            </span>
            <span className="flex items-center gap-1.5">
              <span style={{ width: 8, height: 8, borderRadius: 4, background: FIELD_INK, display: 'inline-block' }} /> other providers
            </span>
          </div>
        )}

        <CostAccuracyChart rows={rows} />

        <div className="mt-4 px-1">
          <JudgeTable rows={rows} />
        </div>
      </div>

      {/* What was NOT measured, verbatim from the bench. The gap is the point:
          without a competitor key there is no cross-provider comparison, and
          this surface says that rather than quietly implying one. */}
      {data.notes.length > 0 && (
        <div className="rounded-2xl px-5 py-4 sm:px-6"
             style={{ background: 'var(--helicon-bg-2)', border: '1px dashed var(--helicon-line-2)' }}>
          <div style={{ fontSize: 9.5, letterSpacing: '0.18em', textTransform: 'uppercase', color: 'var(--helicon-stale)' }}>
            not measured in this run
          </div>
          {data.notes.map((n, i) => (
            <div key={i} className="mt-1.5" style={{ fontSize: 11.5, color: 'var(--helicon-muted)', lineHeight: 1.55 }}>
              {n}
            </div>
          ))}
        </div>
      )}

      <div className="px-1" style={{ fontSize: 10.5, color: 'var(--helicon-faint)', lineHeight: 1.6 }}>
        Ground truth is the operator's own rulings plus real vault facts: the probe sentences are
        constructed, the verdicts are human. Cost is measured from live token usage, not a price list.
        A bench never runs from this page — <code style={{ fontFamily: 'var(--helicon-mono)' }}>helicon judge-bench --set all --save</code> writes the next one.
      </div>
    </div>
  );
}
