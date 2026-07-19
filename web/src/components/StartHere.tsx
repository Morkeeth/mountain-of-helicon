import { useEffect, useState } from 'react';

/* START HERE — the 90-second guided loop a judge cannot get lost in. Four beats:
   the problem → the catch (Qwen) → your one ruling → the proof (the guard now
   enforces it). Drives the REAL endpoints on the demo store: /api/findings finds
   the Stripe contradiction, /api/govern/apply-batch rules it and returns the
   receipt that proves enforcement. Alpine Wash, one thing per screen. */

const SERIF = { fontFamily: '"Fraunces", serif' } as const;

type Finding = { id: string; why: string; options: string[]; title: string };
type Receipt = {
  verify: { recorded_in_audit_log: boolean; compiled_into_law: boolean; guard_blocks_the_wrong_claim: boolean };
};

function Shell({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <div style={{ maxWidth: 600, margin: '0 auto', padding: '56px 24px', minHeight: 400 }}>
      <div style={{ display: 'flex', gap: 6, marginBottom: 40 }}>
        {[0, 1, 2, 3].map(i => (
          <div key={i} style={{ height: 3, flex: 1, borderRadius: 3,
            background: i <= step ? 'var(--text-primary)' : 'var(--border, rgba(0,0,0,.12))' }} />
        ))}
      </div>
      {children}
    </div>
  );
}

function Btn({ label, onClick, primary = false }: { label: string; onClick: () => void; primary?: boolean }) {
  return (
    <button onClick={onClick} style={{
      ...SERIF, fontSize: 16, cursor: 'pointer', padding: '12px 22px', borderRadius: 12,
      border: primary ? 'none' : '1px solid var(--border, rgba(0,0,0,.2))',
      background: primary ? 'var(--text-primary)' : 'transparent',
      color: primary ? 'var(--bg, #fff)' : 'var(--text-primary)',
    }}>{label}</button>
  );
}

export default function StartHere({ onExplore }: { onExplore?: () => void }) {
  const [step, setStep] = useState(0);
  const [finding, setFinding] = useState<Finding | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/findings?lane=decision&limit=20').then(r => r.json()).then(d => {
      const f = (d.findings || []).find((x: { kind: string }) => x.kind === 'factual');
      if (f) setFinding(f); else setErr('Run `helicon demo` first — this walkthrough needs the seeded store.');
    }).catch(e => setErr(String(e)));
  }, []);

  const H = (t: string) => <div style={{ ...SERIF, fontSize: 30, lineHeight: 1.25, color: 'var(--text-primary)' }}>{t}</div>;
  const P = (t: string) => <div style={{ ...SERIF, fontSize: 17, lineHeight: 1.6, color: 'var(--text-muted)', marginTop: 16 }}>{t}</div>;

  async function rule(truth: string) {
    if (!finding) return;
    setBusy(true); setErr(null);
    const fid = parseInt(finding.id.replace('audit-', ''), 10);
    try {
      const res = await fetch('/api/govern/apply-batch', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rulings: [{ finding_id: fid, verb: 'rule_truth', payload: { truth }, label: truth }] }),
      }).then(r => r.json());
      setReceipt(res.receipt?.[0] ?? null);
      setStep(3);
    } catch (e) { setErr(String(e)); }
    setBusy(false);
  }

  if (err) return <Shell step={step}>{H('Almost there')}{P(err)}</Shell>;
  if (!finding) return <Shell step={0}>{P('…')}</Shell>;

  // 0 — the problem
  if (step === 0) return (
    <Shell step={0}>
      {H('Your agent remembers two things that disagree.')}
      <div style={{ ...SERIF, fontSize: 17, marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ padding: 16, borderRadius: 12, background: 'var(--card, rgba(0,0,0,.03))' }}>
          “Stripe is in <b>test mode</b> — charges are simulated.” <span style={{ color: 'var(--text-muted)' }}>(March)</span>
        </div>
        <div style={{ padding: 16, borderRadius: 12, background: 'var(--card, rgba(0,0,0,.03))' }}>
          “We went <b>live</b> on Stripe — every charge is real money.” <span style={{ color: 'var(--text-muted)' }}>(July)</span>
        </div>
      </div>
      {P('Believe the stale one, and your agent charges real customers by mistake.')}
      <div style={{ marginTop: 32 }}><Btn label="What Helicon did →" onClick={() => setStep(1)} primary /></div>
    </Shell>
  );

  // 1 — the catch
  if (step === 1) return (
    <Shell step={1}>
      {H('Helicon caught it. Qwen said: contradiction.')}
      {P('A similarity score just sees two memories about Stripe and calls them related. Qwen read both and judged that they cannot both be true.')}
      {P('That is the difference — a judge, not a search.')}
      <div style={{ marginTop: 32 }}><Btn label="Now you decide →" onClick={() => setStep(2)} primary /></div>
    </Shell>
  );

  // 2 — your ruling
  if (step === 2) return (
    <Shell step={2}>
      {H('Which is true, right now?')}
      {P('One tap. Helicon does the rest.')}
      <div style={{ display: 'flex', gap: 12, marginTop: 28, flexWrap: 'wrap' }}>
        {finding.options.map(o => (
          <Btn key={o} label={`It's ${o}`} onClick={() => rule(o)} primary={o.includes('live')} />
        ))}
      </div>
      {busy && P('Applying…')}
    </Shell>
  );

  // 3 — the proof
  const v = receipt?.verify;
  return (
    <Shell step={3}>
      {H('Done. That is the whole product.')}
      <div style={{ ...SERIF, fontSize: 17, marginTop: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
        {[
          ['Your decision is recorded', v?.recorded_in_audit_log],
          ['Compiled into your rules', v?.compiled_into_law],
          ['The guard now blocks the wrong claim', v?.guard_blocks_the_wrong_claim],
        ].map(([label, ok]) => (
          <div key={label as string} style={{ display: 'flex', gap: 12, alignItems: 'baseline' }}>
            <span style={{ color: ok ? 'var(--improve, #2f7d5b)' : 'var(--text-muted)', fontSize: 18 }}>{ok ? '✓' : '·'}</span>
            <span style={{ color: 'var(--text-primary)' }}>{label as string}</span>
          </div>
        ))}
      </div>
      {P('Your agent can no longer act on “Stripe is in test mode.” You ruled once; the guard enforces it forever.')}
      <div style={{ marginTop: 32, display: 'flex', gap: 12 }}>
        <Btn label="Run it again" onClick={() => { setStep(0); setReceipt(null); }} />
        {onExplore && <Btn label="Explore Helicon →" onClick={onExplore} primary />}
      </div>
    </Shell>
  );
}
