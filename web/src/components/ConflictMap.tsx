import { useEffect, useState } from 'react';
import { api } from '../api';
import type { Finding } from '../api';

/* CONFLICT MAP, Oscar's call on the Graph tab: "surely there's better ways
   to visualise this". This is the flat, honest version: every open
   contradiction as a pair, file vs file, value vs value, the evidence
   between them, and the one command that closes it. No cosmic 3D. */

function Side({ label, text, align }: { label: string; text: string; align: 'left' | 'right' }) {
  return (
    <div style={{ textAlign: align, minWidth: 0 }}>
      <div style={{ fontSize: 10, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--helicon-muted)', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 12.5, color: '#443e36', overflowWrap: 'break-word' }}>{text}</div>
    </div>
  );
}

export default function ConflictMap() {
  const [rows, setRows] = useState<Finding[] | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    api.getFindings({ kind: 'factual', limit: 40 }).then(r => setRows(r.findings)).catch(() => setRows([]));
  }, []);

  if (rows === null) return <div style={{ fontSize: 12, color: 'var(--helicon-muted)' }}>Loading conflicts…</div>;
  if (!rows.length) return (
    <div className="rounded-2xl p-10 text-center helicon-surface" style={{ background: 'var(--helicon-bg)' }}>
      <div style={{ fontFamily: 'var(--helicon-serif)', fontSize: 22, fontWeight: 400 }}>No open contradictions.</div>
      <div style={{ fontSize: 12.5, color: 'var(--helicon-muted)', marginTop: 6 }}>Every fact in the store currently agrees with itself. The exam keeps checking.</div>
    </div>
  );

  return (
    <div className="rounded-2xl p-7 helicon-surface" style={{ background: 'var(--helicon-bg)', color: 'var(--helicon-ink)', boxShadow: '0 20px 60px rgba(50,40,28,.14)' }}>
      <div style={{ fontSize: 10, letterSpacing: '0.3em', textTransform: 'uppercase', color: 'var(--helicon-muted)', marginBottom: 4 }}>
        conflict map · {rows.length} open · each card is two sources that cannot both be true
      </div>
      {rows.map(f => {
        const ev = (f.evidence_preview || '').split('\n');
        const a = ev.find(l => l.startsWith('A:')) || '';
        const la = ev[ev.indexOf(a) + 1] || '';
        const b = ev.find(l => l.startsWith('B:')) || '';
        const lb = ev[ev.indexOf(b) + 1] || '';
        const id = f.id.replace('audit-', '');
        const cmd = `helicon resolve ${id}`;
        return (
          <div key={f.id} style={{ borderTop: '1px solid var(--helicon-line)', padding: '18px 0' }}>
            <div style={{ fontSize: 13.5, fontWeight: 600, marginBottom: 12 }}>{f.why.replace(/^Contradiction: /, '')}</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 18, alignItems: 'start' }}>
              <Side label={a.replace('A:', 'source A ·')} text={la.replace(/^\s*\|\s*/, '')} align="left" />
              <div style={{ alignSelf: 'center', color: 'var(--helicon-accent)', fontSize: 18 }} title="cannot both be true">⇄</div>
              <Side label={b.replace('B:', 'source B ·')} text={lb.replace(/^\s*\|\s*/, '')} align="right" />
            </div>
            <button
              onClick={() => { navigator.clipboard.writeText(cmd); setCopied(f.id); setTimeout(() => setCopied(null), 1500); }}
              className="mt-3 text-[11px] px-3 py-1.5 rounded-md border border-zinc-300 bg-white hover:bg-zinc-100"
              style={{ fontFamily: 'monospace' }}
            >
              {copied === f.id ? 'copied' : cmd} · rule on it
            </button>
          </div>
        );
      })}
    </div>
  );
}
