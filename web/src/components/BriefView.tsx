import { useEffect, useState } from 'react';

/* BRIEF — the calm morning glance. One number (how many things need YOU), the
   few things that do, and everything else reduced to a single quiet line. No
   section labels, no nested lists, no tables. Reads /api/brief. Alpine Wash. */

type Brief = {
  truth: { headline: string };
  continuity: { headline: string };
  direction: { headline: string };
  reflection: { headline: string };
  calm: { headline: string; worth_your_judgment: { id: number; finding: string; severity: string }[] };
};

const SERIF = { fontFamily: '"Fraunces", serif' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;

export default function BriefView() {
  const [b, setB] = useState<Brief | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/brief').then(r => r.json()).then(d => alive && setB(d)).catch(e => alive && setErr(String(e)));
    return () => { alive = false; };
  }, []);

  if (err) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>brief unavailable — {err}</div>;
  if (!b) return <div style={{ padding: 40, color: 'var(--text-muted)' }}>…</div>;

  const need = b.calm.worth_your_judgment;

  return (
    <div style={{ maxWidth: 620, margin: '0 auto', padding: '64px 24px' }}>
      {/* the one thing that matters */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16 }}>
        <span style={{ ...NUM, fontSize: 88, lineHeight: 1, fontWeight: 300,
                       color: need.length ? 'var(--regress, #b4472e)' : 'var(--text-muted)' }}>
          {need.length}
        </span>
        <span style={{ ...SERIF, fontSize: 22, color: 'var(--text-primary)' }}>
          {need.length === 1 ? 'thing worth your judgment' : 'things worth your judgment'}
        </span>
      </div>

      {/* the few things — just the words, calm */}
      <div style={{ marginTop: 28 }}>
        {need.length === 0 && (
          <div style={{ ...SERIF, fontSize: 17, color: 'var(--text-muted)' }}>Nothing needs you right now.</div>
        )}
        {need.map(e => (
          <div key={e.id} style={{ display: 'flex', gap: 14, alignItems: 'baseline', padding: '11px 0',
                                   borderTop: '1px solid var(--border, rgba(0,0,0,.08))' }}>
            <span style={{ width: 7, height: 7, borderRadius: 7, flexShrink: 0, marginTop: 7,
                           background: e.severity === 'critical' ? 'var(--regress, #b4472e)' : 'var(--text-muted)' }} />
            <span style={{ ...SERIF, fontSize: 16, lineHeight: 1.5, color: 'var(--text-primary)' }}>{e.finding}</span>
          </div>
        ))}
      </div>

      {/* everything else — four quiet lines, nothing shouting */}
      <div style={{ marginTop: 44, display: 'flex', flexDirection: 'column', gap: 7,
                    fontSize: 14, color: 'var(--text-muted)', lineHeight: 1.5 }}>
        <div>{b.truth.headline}</div>
        <div>{b.direction.headline}</div>
        <div>{b.reflection.headline}</div>
        <div>{b.continuity.headline}</div>
      </div>
    </div>
  );
}
