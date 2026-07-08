import { useState } from 'react';

/* External store audit — point Helicon at a Mem0 store (the backend Alibaba's
   docs recommend), pull what it kept, and run the rot exam. The store owns the
   write path; Helicon is the exam it never runs on itself. */

const API = (p: string) => fetch(`/api${p}`).then(r => r.json());

interface Finding { id: string; name: string; receipt: string; }
interface Audit {
  configured: boolean; store?: string; memories?: number;
  rot_found?: number; classes?: number; findings?: Finding[];
}

export default function StoreAudit() {
  const [a, setA] = useState<Audit | null>(null);
  const [loading, setLoading] = useState(false);

  const run = () => { setLoading(true); API('/stores/audit').then(setA).finally(() => setLoading(false)); };

  return (
    <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: 'var(--helicon-muted)' }}>
            Audit an external store
          </div>
          <p className="mt-1.5 text-[13px]" style={{ color: 'var(--helicon-muted)', maxWidth: '52ch' }}>
            Point Helicon at a <strong style={{ color: 'var(--helicon-ink)' }}>Mem0</strong> store — the memory backend Alibaba's own docs recommend for Qwen agents. It stores and retrieves; it never checks if what it kept is still true. Helicon does.
          </p>
        </div>
        <button
          onClick={run}
          disabled={loading}
          className="text-[12px] px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 shrink-0"
          style={{ background: 'var(--helicon-accent)' }}
        >
          {loading ? 'auditing the store…' : a ? 'Re-audit Mem0' : 'Audit the Mem0 store'}
        </button>
      </div>

      {a && !a.configured && !loading && (
        <p className="mt-5 text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
          No Mem0 store configured. Add a <code>mem0_audit</code> block with an API key to config.
        </p>
      )}

      {a && a.configured && !loading && (
        <div className="mt-6">
          <div className="flex items-baseline gap-3 mb-4 flex-wrap">
            <span className="text-[15px]" style={{ color: 'var(--helicon-ink)' }}>
              <strong>Mem0</strong> stored <span className="tabular-nums" style={{ fontFamily: 'var(--helicon-serif)' }}>{a.memories}</span> memories.
            </span>
            <span className="text-[15px]" style={{ color: (a.rot_found ?? 0) > 0 ? 'var(--helicon-accent)' : 'var(--helicon-stale)' }}>
              Helicon found rot in <span className="tabular-nums" style={{ fontFamily: 'var(--helicon-serif)', fontSize: 22 }}>{a.rot_found}</span> of {a.classes} classes it never checks.
            </span>
          </div>

          {(a.findings?.length ?? 0) > 0 ? (
            <div className="space-y-2">
              {a.findings!.map(f => (
                <div key={f.id} className="rounded-lg border px-4 py-3" style={{ borderColor: 'rgba(158,63,50,0.28)', background: 'rgba(158,63,50,0.04)' }}>
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-sm" style={{ background: 'var(--helicon-accent)' }} />
                    <span className="text-[12px] uppercase tracking-wider" style={{ color: 'var(--helicon-accent)' }}>{f.id} · {f.name}</span>
                  </div>
                  <p className="text-[13px] mt-1.5" style={{ color: 'var(--helicon-ink)' }}>{f.receipt}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[13px]" style={{ color: 'var(--helicon-stale)' }}>This Mem0 store is clean — no rot classes firing.</p>
          )}
        </div>
      )}
    </div>
  );
}
