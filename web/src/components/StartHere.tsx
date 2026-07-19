import { useEffect, useState } from 'react';

/* START HERE — the critical path, stripped to the bone. Two screens, almost no
   words: make the one decision, see it enforced. Drives the real endpoints on the
   demo store. Alpine Wash. */

const SERIF = { fontFamily: '"Fraunces", serif' } as const;

type Finding = { id: string; options: string[] };

export default function StartHere({ onExplore }: { onExplore?: () => void }) {
  const [finding, setFinding] = useState<Finding | null>(null);
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/findings?lane=decision&limit=20').then(r => r.json()).then(d => {
      const f = (d.findings || []).find((x: { kind: string }) => x.kind === 'factual');
      if (f) setFinding(f); else setErr('Run `helicon demo` to load the walkthrough.');
    }).catch(e => setErr(String(e)));
  }, []);

  async function rule(truth: string) {
    if (!finding) return;
    setBusy(true);
    const fid = parseInt(finding.id.replace('audit-', ''), 10);
    await fetch('/api/govern/apply-batch', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rulings: [{ finding_id: fid, verb: 'rule_truth', payload: { truth }, label: truth }] }),
    }).catch(() => {});
    setBusy(false); setDone(true);
  }

  const wrap: React.CSSProperties = {
    maxWidth: 480, margin: '0 auto', padding: '15vh 28px',
    display: 'flex', flexDirection: 'column', gap: 18,
  };
  const big = { ...SERIF, fontSize: 34, lineHeight: 1.2, color: 'var(--text-primary)' } as const;
  const sub = { fontSize: 16, lineHeight: 1.5, color: 'var(--text-muted)' } as const;

  if (err) return <div style={wrap}><div style={big}>Almost there</div><div style={sub}>{err}</div></div>;
  if (!finding) return <div style={wrap}><div style={sub}>…</div></div>;

  // done — enforced, in one glance
  if (done) return (
    <div style={wrap}>
      <div style={{ ...big, color: 'var(--improve, #2f7d5b)' }}>Locked. ✓</div>
      <div style={sub}>Your agent can no longer act on the wrong answer.</div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', opacity: 0.8 }}>
        You ruled once · it became a rule · the guard enforces it from here.
      </div>
      {onExplore && (
        <button onClick={onExplore} style={{ ...SERIF, alignSelf: 'flex-start', marginTop: 12,
          fontSize: 16, cursor: 'pointer', padding: '11px 20px', borderRadius: 12, border: 'none',
          background: 'var(--text-primary)', color: 'var(--bg, #fff)' }}>
          See the rest →
        </button>
      )}
    </div>
  );

  // the one decision
  return (
    <div style={wrap}>
      <div style={big}>Is Stripe live, or in test mode?</div>
      <div style={sub}>Believe the wrong one and your agent charges real customers.</div>
      <div style={{ display: 'flex', gap: 12, marginTop: 6, flexWrap: 'wrap' }}>
        {finding.options.map(o => (
          <button key={o} onClick={() => rule(o)} disabled={busy} style={{
            ...SERIF, fontSize: 17, cursor: 'pointer', padding: '13px 22px', borderRadius: 12,
            border: o.includes('live') ? 'none' : '1px solid var(--border, rgba(0,0,0,.2))',
            background: o.includes('live') ? 'var(--text-primary)' : 'transparent',
            color: o.includes('live') ? 'var(--bg, #fff)' : 'var(--text-primary)',
          }}>It's {o}</button>
        ))}
      </div>
      <div style={{ fontSize: 13, color: 'var(--text-muted)', opacity: 0.7, marginTop: 4 }}>
        Qwen flagged this — the two facts can't both be true.
      </div>
    </div>
  );
}
