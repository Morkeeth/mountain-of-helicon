import { useEffect, useState } from 'react';

/* BRIEF — the morning screen, the product vision in one view. Reads /api/brief:
   all five pillars assembled once on the server, rendered honestly here. Alpine
   Wash: Fraunces carries the one number that matters (how many things need YOU),
   mono for ids and costs, CSS-var colors for meaning. No status lights, no fake
   precision — an empty pillar says so in words. */

type Brief = {
  truth: { grade: number | null; reviewed: number; total: number; headline: string;
           no_longer_trustworthy: { id: string; title: string; confidence: number }[]; stale_count: number };
  continuity: { context_packets: number; task_runs: number; headline: string };
  direction: { headline: string;
               task_classes: { task_class: string; recommendation: string | null; lean: string | null; sufficient: boolean }[] };
  reflection: { headline: string; rulings_applied: { id: string; at: string }[];
                runs_scored: { run_id: string; model: string; score: number; verified_ratio: number; cost: number }[] };
  calm: { open_exceptions: number; headline: string;
          worth_your_judgment: { id: number; finding: string; severity: string }[] };
};

const MONO = { fontFamily: '"IBM Plex Mono", monospace' } as const;
const NUM = { fontFamily: '"Fraunces", serif', fontVariantNumeric: 'tabular-nums' } as const;
const SERIF = { fontFamily: '"Fraunces", serif' } as const;

function sevColor(s: string): string {
  if (s === 'critical') return 'var(--regress, #b4472e)';
  if (s === 'high') return 'var(--text-primary)';
  return 'var(--text-muted)';
}

function Pillar({ name, headline, children }: { name: string; headline: string; children?: React.ReactNode }) {
  return (
    <section style={{ borderTop: '1px solid var(--border, rgba(0,0,0,.12))', padding: '18px 0' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, flexWrap: 'wrap' }}>
        <span style={{ ...MONO, fontSize: 11, letterSpacing: '.14em', color: 'var(--text-muted)', minWidth: 96 }}>
          {name.toUpperCase()}
        </span>
        <span style={{ ...SERIF, fontSize: 17, color: 'var(--text-primary)' }}>{headline}</span>
      </div>
      {children && <div style={{ marginTop: 10, marginLeft: 110 }}>{children}</div>}
    </section>
  );
}

export default function BriefView() {
  const [b, setB] = useState<Brief | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    fetch('/api/brief').then(r => r.json()).then(d => alive && setB(d)).catch(e => alive && setErr(String(e)));
    return () => { alive = false; };
  }, []);

  if (err) return <div style={{ padding: 24, ...MONO, color: 'var(--text-muted)' }}>brief unavailable — {err}</div>;
  if (!b) return <div style={{ padding: 24, ...MONO, color: 'var(--text-muted)' }}>assembling the brief…</div>;

  const need = b.calm.worth_your_judgment.length;

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '28px 20px 60px' }}>
      {/* Hero: the one number that matters — how many things need the human */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ ...MONO, fontSize: 11, letterSpacing: '.14em', color: 'var(--text-muted)' }}>MORNING BRIEF</div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 14, marginTop: 6 }}>
          <span style={{ ...NUM, fontSize: 68, lineHeight: 1, fontWeight: 300,
                         color: need ? 'var(--regress, #b4472e)' : 'var(--text-muted)' }}>{need}</span>
          <span style={{ ...SERIF, fontSize: 20, color: 'var(--text-primary)' }}>
            {need === 1 ? 'thing worth your judgment' : 'things worth your judgment'}
          </span>
        </div>
      </div>

      <Pillar name="Calm" headline={b.calm.headline}>
        {b.calm.worth_your_judgment.map(e => (
          <div key={e.id} style={{ padding: '6px 0', display: 'flex', gap: 10 }}>
            <span style={{ ...MONO, fontSize: 12, color: sevColor(e.severity), minWidth: 62 }}>{e.severity}</span>
            <span style={{ fontSize: 14, color: 'var(--text-primary)' }}>#{e.id} {e.finding}</span>
          </div>
        ))}
      </Pillar>

      <Pillar name="Truth" headline={b.truth.headline}>
        {b.truth.no_longer_trustworthy.map(m => (
          <div key={m.id} style={{ padding: '5px 0', display: 'flex', gap: 10, alignItems: 'baseline' }}>
            <span style={{ ...MONO, fontSize: 11, color: 'var(--text-muted)' }}>{m.id}</span>
            <span style={{ fontSize: 14, color: 'var(--text-primary)' }}>{m.title}</span>
            <span style={{ ...NUM, fontSize: 12, color: 'var(--text-muted)' }}>conf {m.confidence}</span>
          </div>
        ))}
      </Pillar>

      <Pillar name="Direction" headline={b.direction.headline}>
        {b.direction.task_classes.map(p => (
          <div key={p.task_class} style={{ padding: '5px 0', ...MONO, fontSize: 13 }}>
            <span style={{ color: 'var(--text-muted)' }}>{p.task_class} → </span>
            <span style={{ color: p.sufficient ? 'var(--improve, #2f7d5b)' : 'var(--text-muted)' }}>
              {p.recommendation || `${p.lean} (lean)`}
            </span>
          </div>
        ))}
      </Pillar>

      <Pillar name="Reflection" headline={b.reflection.headline}>
        {b.reflection.runs_scored.map(r => (
          <div key={r.run_id} style={{ padding: '5px 0', ...MONO, fontSize: 12, color: 'var(--text-muted)' }}>
            {r.run_id} · {r.model} · score <span style={{ ...NUM, color: 'var(--text-primary)' }}>{r.score}</span> · ${r.cost}
          </div>
        ))}
      </Pillar>

      <Pillar name="Continuity" headline={b.continuity.headline} />
    </div>
  );
}
