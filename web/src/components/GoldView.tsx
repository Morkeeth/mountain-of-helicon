import { useEffect, useState } from 'react';
import DitherArea from './DitherArea';

/* GOLD, the stack's law, compiled from human judgment. Every rule was born
   from a ruling, a precedent, a declared fact or standing feedback, and
   carries its provenance. The growth strip is the law's own history. */

interface GoldData { markdown: string; history: { ts: string; total: number }[]; }

const API = (path: string) => fetch(`/api${path}`).then(r => r.json());

function renderLine(l: string, i: number) {
  if (l.startsWith('# '))
    return <h1 key={i} style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 900, fontSize: 30, margin: '0 0 4px', fontVariationSettings: "'opsz' 144" }}>{l.slice(2)}</h1>;
  if (l.startsWith('## '))
    return <h2 key={i} style={{ fontSize: 11, letterSpacing: '0.2em', textTransform: 'uppercase', color: 'var(--helicon-accent)', margin: '26px 0 10px' }}>{l.slice(3)}</h2>;
  if (l.startsWith('- '))
    return <div key={i} style={{ fontSize: 13.5, color: '#443e36', padding: '5px 0 0 14px', textIndent: -14 }}>◆ {l.slice(2).replace(/\*\*/g, '').replace(/`/g, '')}</div>;
  if (l.startsWith('  _') || l.startsWith('_'))
    return <div key={i} style={{ fontSize: 11, color: 'var(--helicon-muted)', paddingLeft: 14 }}>{l.trim().replace(/^_|_$/g, '')}</div>;
  if (l.startsWith('---')) return <hr key={i} style={{ border: 0, borderTop: '1px solid var(--helicon-line)', margin: '22px 0' }} />;
  if (!l.trim()) return null;
  return <p key={i} style={{ fontSize: 12.5, color: 'var(--helicon-muted)', margin: '4px 0' }}>{l.replace(/[_`]/g, '')}</p>;
}

export default function GoldView() {
  const [data, setData] = useState<GoldData | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);

  const copyRules = () => {
    if (!data) return;
    navigator.clipboard.writeText(data.markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  };

  const load = (fresh = 0) => {
    setBusy(true);
    API(`/gold${fresh ? '?fresh=1' : ''}`).then(setData).finally(() => setBusy(false));
  };
  useEffect(() => { load(); }, []);

  if (!data) return <div style={{ fontSize: 12, color: 'var(--helicon-muted)' }}>Compiling the law…</div>;

  const hist = data.history;
  // a compile once emitted total=1 (data bug); it is not a rule count, drop it
  const series = hist.map(h => h.total).filter(t => t > 10);
  const first = series[0];
  const now = series[series.length - 1];
  const learned = now - first;

  return (
    <div className="rounded-2xl p-7 helicon-surface" style={{ background: 'var(--helicon-bg)', color: 'var(--helicon-ink)', boxShadow: '0 20px 60px rgba(50,40,28,.14)' }}>
      <div className="flex items-end justify-between mb-2">
        <div style={{ fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
          the law · every rule has a receipt · grows when you rule
        </div>
        <div className="flex items-end gap-3">
          <button
            onClick={copyRules}
            className="text-[11px] px-3 py-1.5 rounded-md text-white transition-opacity hover:opacity-90"
            style={{ background: 'var(--helicon-accent)' }}
          >
            {copied ? 'copied ✓' : 'Copy rules'}
          </button>
          <button
            onClick={() => load(1)}
            disabled={busy}
            className="text-[11px] px-3 py-1.5 rounded-md border border-zinc-300 bg-white hover:bg-zinc-100 disabled:opacity-40"
          >
            {busy ? 'compiling…' : 'recompile'}
          </button>
        </div>
      </div>
      <p style={{ fontSize: 11, color: 'var(--helicon-muted)', margin: '0 0 14px' }}>
Infrastructure, not a doc to copy each time. <code style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--helicon-ink)' }}>helicon gold --inject</code> writes it into <code style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--helicon-ink)' }}>~/.claude</code> so every session obeys it, and it recompiles itself as you rule.
      </p>

      {series.length > 1 && (
        <div style={{ margin: '0 0 20px' }}>
          <div className="flex items-baseline justify-between" style={{ marginBottom: 6 }}>
            <div style={{ fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--helicon-muted)' }}>
              the law growing
            </div>
            <div style={{ fontSize: 11 }} className="tabular-nums">
              <span style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 600, fontSize: 15, color: 'var(--helicon-ink)' }}>{now}</span>
              <span style={{ color: 'var(--helicon-muted)' }}> rules · </span>
              <span style={{ color: 'var(--helicon-improve)', fontWeight: 600 }}>+{learned} learned</span>
            </div>
          </div>
          <DitherArea
            series={series}
            height={88}
            ariaLabel={`Golden rules over time: grew from ${first} to ${now} rules across ${series.length} compiles, a gain of ${learned}. The dithered area rises with the rule count.`}
          />
        </div>
      )}

      {data.markdown.split('\n').map(renderLine)}
    </div>
  );
}
