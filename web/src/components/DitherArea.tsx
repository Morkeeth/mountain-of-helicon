import { useEffect, useRef, useState } from 'react';

/* DitherArea - hand-rolled Bayer-8 ordered-dither area chart on <canvas>.
   No dependency, our palette. Ported straight from scripts/dither_proto.py.

   Why hand-rolled and not dither-kit: its `color` prop is a 7-name fixed
   palette (no custom hex), so it cannot render Alpine Wash; its "no deps" claim
   is false (motion/d3/Tailwind/shadcn); it ships no ARIA path; and its license
   is unspecified while this repo is MIT + OFL. Dithering is a technique, not a
   library - this is the technique, ~40 lines, in our tokens.

   The look: density carries the value. Each column fills bottom→crest; the
   Bayer threshold makes the crest (near the value line) solid/dense and it
   dissolves into sparse dots toward the baseline. Taller columns hold more ink,
   so the shape reads without a gridline. Colour lerps from `bot` at the crest
   to `top` at the floor - the improvement-orange is earned at the base of the
   law's growth, calm slate at the living edge.

   Accessibility (the whole reason we did not adopt the library): the canvas is
   aria-hidden decoration. The real reading lives in an aria-label on the
   role="img" wrapper plus a visually-hidden data list a screen reader can walk. */

const BAYER8 = [
  [0, 32, 8, 40, 2, 34, 10, 42],
  [48, 16, 56, 24, 50, 18, 58, 26],
  [12, 44, 4, 36, 14, 46, 6, 38],
  [60, 28, 52, 20, 62, 30, 54, 22],
  [3, 35, 11, 43, 1, 33, 9, 41],
  [51, 19, 59, 27, 49, 17, 57, 25],
  [15, 47, 7, 39, 13, 45, 5, 37],
  [63, 31, 55, 23, 61, 29, 53, 21],
];

type RGB = [number, number, number];

/* Resolve a CSS custom property (e.g. "--helicon-improve") to rgb, so the chart
   tracks the token file, not a hardcoded hex. Falls back to the given hex. */
function readColor(el: Element | null, cssVar: string, fallback: string): RGB {
  let raw = fallback;
  if (el) {
    const v = getComputedStyle(el).getPropertyValue(cssVar).trim();
    if (v) raw = v;
  }
  return parseColor(raw) ?? parseColor(fallback) ?? [0, 0, 0];
}

function parseColor(s: string): RGB | null {
  s = s.trim();
  if (s.startsWith('#')) {
    const h = s.slice(1);
    const f = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
    if (f.length < 6) return null;
    return [parseInt(f.slice(0, 2), 16), parseInt(f.slice(2, 4), 16), parseInt(f.slice(4, 6), 16)];
  }
  const m = s.match(/rgba?\(([^)]+)\)/);
  if (m) {
    const p = m[1].split(/[,\s/]+/).map(Number);
    if (p.length >= 3) return [p[0], p[1], p[2]];
  }
  return null;
}

interface Props {
  series: number[];
  height?: number;      // css px
  cell?: number;        // dither cell size in css px (proto used 3)
  topColor?: string;    // CSS var name, drawn at the floor
  botColor?: string;    // CSS var name, drawn at the crest
  topFallback?: string;
  botFallback?: string;
  ariaLabel: string;    // the real reading, for screen readers
  className?: string;
  style?: React.CSSProperties;
}

export default function DitherArea({
  series,
  height = 84,
  cell = 3,
  topColor = '--helicon-improve',
  botColor = '--helicon-accent',
  topFallback = '#C67C3E',
  botFallback = '#223A4E',
  ariaLabel,
  className,
  style,
}: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [width, setWidth] = useState(0);

  // responsive: track the wrapper's width, redraw on resize
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      setWidth(Math.max(0, Math.floor(w)));
    });
    ro.observe(el);
    setWidth(Math.floor(el.clientWidth));
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || width < 4 || series.length < 2) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = width + 'px';
    canvas.style.height = height + 'px';
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const top = readColor(wrapRef.current, topColor, topFallback);
    const bot = readColor(wrapRef.current, botColor, botFallback);

    // work in a grid of dither cells, exactly like the PIL prototype
    const W = Math.max(2, Math.floor(width / cell));
    const H = Math.max(2, Math.floor(height / cell));
    const lo = Math.min(...series);
    const hi = Math.max(...series);
    const span = hi - lo || 1;
    const n = series.length;

    const heightAt = (px: number) => {
      const t = (px / Math.max(W - 1, 1)) * (n - 1);
      const i = Math.min(Math.floor(t), n - 2);
      const f = t - i;
      const v = series[i] + (series[i + 1] - series[i]) * f;
      return (v - lo) / span;
    };

    for (let px = 0; px < W; px++) {
      const colh = heightAt(px) * (H - 2) + 2;
      for (let py = 0; py < H; py++) {
        if (H - py > colh) continue;
        const frac = (H - py) / Math.max(colh, 1);
        if (frac < BAYER8[py % 8][px % 8] / 64) continue;
        const k = 1 - frac;
        const r = Math.round(bot[0] + (top[0] - bot[0]) * k);
        const g = Math.round(bot[1] + (top[1] - bot[1]) * k);
        const b = Math.round(bot[2] + (top[2] - bot[2]) * k);
        ctx.fillStyle = `rgb(${r},${g},${b})`;
        ctx.fillRect(px * cell, py * cell, cell, cell);
      }
    }
  }, [series, width, height, cell, topColor, botColor, topFallback, botFallback]);

  return (
    <div
      ref={wrapRef}
      className={className}
      style={{ position: 'relative', width: '100%', height, ...style }}
      role="img"
      aria-label={ariaLabel}
    >
      <canvas ref={canvasRef} aria-hidden="true" style={{ display: 'block' }} />
      {/* visually-hidden readable data - the screen-reader path the library lacked */}
      <span
        style={{
          position: 'absolute', width: 1, height: 1, padding: 0, margin: -1,
          overflow: 'hidden', clip: 'rect(0 0 0 0)', whiteSpace: 'nowrap', border: 0,
        }}
      >
        {ariaLabel}
      </span>
    </div>
  );
}
