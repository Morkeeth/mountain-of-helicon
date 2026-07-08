import { useState, useCallback } from 'react';

/* The volatility gate. truth = fact + timestamp + decay. Fast facts (a %, a
   count, a price, a rank) rot in a memory file; they belong in the live layer
   or need a decay stamp. Helicon finds the suspects, Qwen sentences them, and
   one click fixes the source. */

const SERIF = { fontFamily: 'var(--helicon-serif)', fontVariationSettings: "'opsz' 144" } as const;
const RED = 'var(--helicon-accent)';
const GOLD = 'var(--helicon-stale)';
const GOOD = 'var(--helicon-conflict)';

interface Fact {
  id: string; title: string; source: string; source_ref: string;
  signals: string[]; tier?: string; reason?: string; stale_when?: string;
}
interface Suspect { id: string; title: string; source: string; source_ref?: string; signals: string[]; }
interface Scan {
  suspects: number; judged: number; keyless: boolean;
  fast: Fact[]; slow_undated: Fact[]; static: number;
  unsentenced?: Suspect[];
}

const API = (p: string, opts?: RequestInit) => fetch(`/api${p}`, opts).then(r => r.json());

function SectionLabel({ children, color }: { children: React.ReactNode; color?: string }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.26em] mb-3" style={{ color: color ?? RED }}>
      {children}
    </div>
  );
}

function Signals({ signals }: { signals: string[] }) {
  if (!signals?.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {signals.map((s, i) => (
        <span key={i} className="text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: 'rgba(60,40,20,0.05)', color: 'var(--helicon-muted)', border: '1px solid rgba(60,40,20,0.10)' }}>
          {s}
        </span>
      ))}
    </div>
  );
}

function PrimaryButton({ onClick, disabled, children }: { onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="text-[12px] px-3 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40"
      style={{ background: RED }}>
      {children}
    </button>
  );
}

function GhostButton({ onClick, disabled, children }: { onClick: () => void; disabled?: boolean; children: React.ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-300 bg-white hover:bg-zinc-100 transition-colors disabled:opacity-40"
      style={{ color: 'var(--helicon-ink)' }}>
      {children}
    </button>
  );
}

function FastFactCard({ f }: { f: Fact }) {
  const [state, setState] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const act = async (action: 'move' | 'stamp') => {
    setBusy(true);
    try {
      const res = await API('/volatility/act', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action, source_ref: f.source_ref, title: f.title,
          excerpt: f.reason ?? '', stale_when: f.stale_when ?? '',
        }),
      });
      setState(res?.ok ? (action === 'move' ? 'moved to live layer ✓' : 'stamped ✓') : (res?.reason || 'no change'));
    } catch {
      setState('failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border px-5 py-4" style={{ borderColor: 'rgba(158,63,50,0.28)', background: 'rgba(158,63,50,0.04)' }}>
      <div className="flex items-start gap-2">
        <span className="w-1.5 h-1.5 rounded-sm mt-2 shrink-0" style={{ background: RED }} />
        <div className="min-w-0 flex-1">
          <h4 className="text-[14.5px] leading-snug m-0" style={{ color: 'var(--helicon-ink)', fontWeight: 500 }}>{f.title}</h4>
          {f.reason && <p className="text-[13px] mt-1 m-0" style={{ color: 'var(--helicon-muted)' }}>{f.reason}</p>}
          {f.stale_when && (
            <p className="text-[12.5px] mt-1.5 m-0">
              <span className="uppercase tracking-[0.1em] text-[10px]" style={{ color: RED }}>goes wrong when: </span>
              <span style={{ color: 'var(--helicon-ink)' }}>{f.stale_when}</span>
            </p>
          )}
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--helicon-muted)', fontFamily: 'var(--font-mono, monospace)' }}>{f.source_ref}</div>
          <Signals signals={f.signals} />
          <div className="flex items-center gap-2 mt-3 flex-wrap">
            <PrimaryButton onClick={() => act('move')} disabled={busy}>Move to live layer</PrimaryButton>
            <GhostButton onClick={() => act('stamp')} disabled={busy}>Add stale_when</GhostButton>
            {state && <span className="text-[11px]" style={{ color: state.includes('✓') ? GOOD : 'var(--helicon-muted)' }}>{state}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}

function SlowFactRow({ f }: { f: Fact }) {
  const [state, setState] = useState<string>('');
  const [busy, setBusy] = useState(false);

  const stamp = async () => {
    setBusy(true);
    try {
      const res = await API('/volatility/act', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'stamp', source_ref: f.source_ref, title: f.title, excerpt: f.reason ?? '', stale_when: f.stale_when ?? '' }),
      });
      setState(res?.ok ? 'stamped ✓' : (res?.reason || 'no change'));
    } catch {
      setState('failed');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-xl border border-zinc-800/50 bg-white px-5 py-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h4 className="text-[14px] leading-snug m-0" style={{ color: 'var(--helicon-ink)', fontWeight: 500 }}>{f.title}</h4>
          {f.reason && <p className="text-[12.5px] mt-1 m-0" style={{ color: 'var(--helicon-muted)' }}>{f.reason}</p>}
          <div className="text-[11px] mt-1.5" style={{ color: 'var(--helicon-muted)', fontFamily: 'var(--font-mono, monospace)' }}>{f.source_ref}</div>
          <Signals signals={f.signals} />
        </div>
        <div className="flex flex-col items-end gap-1.5 shrink-0">
          <GhostButton onClick={stamp} disabled={busy}>Add stale_when</GhostButton>
          {state && <span className="text-[11px]" style={{ color: state.includes('✓') ? GOOD : 'var(--helicon-muted)' }}>{state}</span>}
        </div>
      </div>
    </div>
  );
}

export default function Volatility() {
  const [data, setData] = useState<Scan | null>(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(() => {
    setLoading(true);
    API('/volatility/scan').then(setData).finally(() => setLoading(false));
  }, []);

  return (
    <div className="pb-10">
      <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
        <div>
          <h2 className="text-[26px] leading-tight m-0" style={{ ...SERIF, fontWeight: 400, color: 'var(--helicon-ink)' }}>
            truth = fact + timestamp + decay
          </h2>
          <p className="text-[13px] mt-1.5 max-w-[62ch]" style={{ color: 'var(--helicon-muted)' }}>
            A fact with a percentage, a count, a price, or a rank is fast: it belongs in the live layer or needs a decay stamp, never bare in a memory file where it rots silently.
          </p>
        </div>
        <button onClick={run} disabled={loading}
          className="text-[12px] px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 shrink-0"
          style={{ background: RED }}>
          {loading ? 'scanning…' : data ? 'Re-scan' : 'Scan the record'}
        </button>
      </div>

      {loading && (
        <div className="py-16 text-center">
          <div className="inline-block w-8 h-1 rounded-full animate-pulse-subtle" style={{ background: RED, opacity: 0.6 }} />
          <p className="text-[13px] mt-3" style={{ color: 'var(--helicon-muted)' }}>Finding fast facts, sentencing the top suspects…</p>
        </div>
      )}

      {!loading && data && (
        <div className="space-y-10">
          {/* Keyless degrade */}
          {data.keyless && (
            <div>
              <p className="text-[13px] mb-4" style={{ color: 'var(--helicon-muted)' }}>
                Helicon sees <span className="tabular-nums" style={{ color: RED }}>{data.suspects}</span> suspect{data.suspects === 1 ? '' : 's'} carrying a fast-fact signal. A Qwen key sentences them into fast, slow, and static.
              </p>
              <div className="space-y-2">
                {(data.unsentenced ?? []).map(s => (
                  <div key={s.id} className="rounded-xl border border-zinc-800/50 bg-white px-5 py-3.5">
                    <h4 className="text-[14px] leading-snug m-0" style={{ color: 'var(--helicon-ink)', fontWeight: 500 }}>{s.title}</h4>
                    {s.source_ref && <div className="text-[11px] mt-1" style={{ color: 'var(--helicon-muted)', fontFamily: 'var(--font-mono, monospace)' }}>{s.source_ref}</div>}
                    <Signals signals={s.signals} />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Fast facts, the rot */}
          {!data.keyless && (
            <section>
              <SectionLabel>Fast facts, the rot</SectionLabel>
              {data.fast.length > 0 ? (
                <div className="space-y-3">
                  {data.fast.map(f => <FastFactCard key={f.id} f={f} />)}
                </div>
              ) : (
                <p className="text-[13px]" style={{ color: GOOD }}>No fast facts loose in memory. Nothing timestamped is quietly rotting.</p>
              )}
            </section>
          )}

          {/* Slow facts missing decay */}
          {!data.keyless && data.slow_undated.length > 0 && (
            <section>
              <SectionLabel color={GOLD}>Slow facts missing decay</SectionLabel>
              <div className="space-y-3">
                {data.slow_undated.map(f => <SlowFactRow key={f.id} f={f} />)}
              </div>
            </section>
          )}

          {/* Honest footer */}
          {!data.keyless && (
            <p className="text-[12px] pt-2" style={{ color: 'var(--helicon-muted)' }}>
              <span className="tabular-nums" style={{ color: GOOD }}>{data.static}</span> static fact{data.static === 1 ? '' : 's'}, correctly durable.
            </p>
          )}
        </div>
      )}

      {!loading && !data && (
        <p className="text-[13px] py-8" style={{ color: 'var(--helicon-muted)' }}>
          Scan the record to see which stored facts have gone volatile.
        </p>
      )}
    </div>
  );
}
