import { useState, useEffect, useCallback } from 'react';

/* Focus, the cherry. Memory state -> your next moves, each citing the exact
   memory it came from. Detection is automatic; deciding what to DO is the human
   act this surfaces. A move leaves as a paste-ready agent prompt or a vault note. */

interface Receipt { ref: string; kind: string; title: string; why: string; source: string; cube_id: string | null; output_kind?: string; }
interface Move { title: string; kind: string; body: string; rationale: string; receipts: Receipt[]; }
interface MovesData { moves: Move[]; grounded_in: number; dropped_uncited?: number; generated_at: string; note?: string; }

const API = (p: string, opts?: RequestInit) => fetch(`/api${p}`, opts).then(r => r.json());

const KIND_TONE: Record<string, string> = {
  prompt: 'var(--helicon-accent)',
  goal: 'var(--helicon-stale)',
  loop: 'var(--helicon-muted)',
};

export default function Focus() {
  const [data, setData] = useState<MovesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [routed, setRouted] = useState<Record<number, string>>({});

  const generate = useCallback(() => {
    setLoading(true);
    setRouted({});
    API('/focus/moves').then(setData).finally(() => setLoading(false));
  }, []);

  useEffect(() => { generate(); }, [generate]);

  const route = async (m: Move, i: number, destination: 'prompt' | 'vault') => {
    const r = await API('/focus/route', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ destination, move: m }),
    });
    if (destination === 'prompt') {
      await navigator.clipboard.writeText(r.prompt);
      setRouted(x => ({ ...x, [i]: 'copied for your agent' }));
    } else {
      setRouted(x => ({ ...x, [i]: `saved → ${(r.path || '').split('/').slice(-2).join('/')}` }));
    }
    setTimeout(() => setRouted(x => { const n = { ...x }; delete n[i]; return n; }), 3000);
  };

  return (
    <div>
      <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
        <div>
          <h2 className="text-[26px] leading-tight" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: 'var(--helicon-ink)' }}>
            Your next moves
          </h2>
          <p className="text-[12px] mt-1" style={{ color: 'var(--helicon-muted)' }}>
            {data
              ? `Your agent's memory, read back to you as what to do next. ${data.grounded_in} flagged memories became these moves, each carries the memory it came from, so none of it is a guess.`
              : 'Reading the state of your memory…'}
          </p>
        </div>
        <button
          onClick={generate}
          disabled={loading}
          className="text-[12px] px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40"
          style={{ background: 'var(--helicon-accent)' }}
        >
          {loading ? 'thinking…' : 'Regenerate'}
        </button>
      </div>

      {loading && (
        <div className="py-20 text-center">
          <div className="inline-block w-8 h-1 rounded-full animate-pulse-subtle" style={{ background: 'var(--helicon-accent)', opacity: 0.6 }} />
          <p className="text-[13px] mt-3" style={{ color: 'var(--helicon-muted)' }}>Reading what rotted, what stalled, what needs you…</p>
        </div>
      )}

      {!loading && data?.note && (
        <div className="py-16 text-center text-[13px]" style={{ color: 'var(--helicon-muted)' }}>{data.note}</div>
      )}

      {!loading && data && data.moves.length > 0 && (
        <div className="space-y-4">
          {data.moves.map((m, i) => (
            <div key={i} className="rounded-xl bg-white shadow-sm border border-zinc-800/50 p-5">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[10px] uppercase tracking-[0.18em] px-1.5 py-0.5 rounded" style={{ color: KIND_TONE[m.kind], border: `1px solid ${KIND_TONE[m.kind]}`, opacity: 0.9 }}>
                  {m.kind}
                </span>
                {(() => {
                  const lens = m.receipts.map(r => r.output_kind).find(k => k && k !== 'default');
                  return lens ? <span className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-stale)' }}>· shaped for {lens}</span> : null;
                })()}
              </div>
              <h3 className="text-[17px] leading-snug" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 600, color: 'var(--helicon-ink)' }}>
                {m.title}
              </h3>

              <pre className="mt-3 text-[12.5px] whitespace-pre-wrap leading-relaxed rounded-lg p-3.5 border border-zinc-800/30" style={{ fontFamily: 'var(--font-mono, monospace)', color: 'var(--helicon-ink)', background: 'rgba(60,40,20,0.03)' }}>
                {m.body}
              </pre>

              {m.rationale && (
                <p className="text-[12px] mt-2.5" style={{ color: 'var(--helicon-muted)' }}>{m.rationale}</p>
              )}

              <div className="mt-3">
                <p className="text-[10px] uppercase tracking-wider mb-1.5" style={{ color: 'var(--helicon-muted)' }}>Grounded in</p>
                <div className="flex flex-wrap gap-1.5">
                  {m.receipts.map(r => (
                    <span key={r.ref} title={r.why}
                      className="text-[11px] px-2 py-0.5 rounded-full cursor-help"
                      style={{ background: 'rgba(60,40,20,0.05)', color: 'var(--helicon-ink)', border: '1px solid rgba(60,40,20,0.10)' }}>
                      {(r.title || r.ref).slice(0, 46)}{(r.title || '').length > 46 ? '…' : ''}
                    </span>
                  ))}
                </div>
              </div>

              <div className="mt-4 flex items-center gap-2">
                <button onClick={() => route(m, i, 'prompt')}
                  title="Copies this move as a ready-to-paste prompt for your coding agent"
                  className="text-[12px] px-3 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90"
                  style={{ background: 'var(--helicon-accent)' }}>
                  Copy as prompt →
                </button>
                <button onClick={() => route(m, i, 'vault')}
                  title="Saves this move as a note in your vault (00 Dashboard/helicon-next-moves.md)"
                  className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-300 bg-white hover:bg-zinc-100 transition-colors" style={{ color: 'var(--helicon-ink)' }}>
                  Save to vault
                </button>
                {routed[i] && <span className="text-[11px]" style={{ color: 'var(--helicon-stale)' }}>{routed[i]} ✓</span>}
              </div>
            </div>
          ))}
          {(data.dropped_uncited ?? 0) > 0 && (
            <p className="text-[11px] text-center pt-1" style={{ color: 'var(--helicon-muted)' }}>
              {data.dropped_uncited} suggestion{data.dropped_uncited === 1 ? '' : 's'} dropped for not citing a specific memory.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
