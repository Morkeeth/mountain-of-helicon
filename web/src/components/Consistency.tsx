import { useState, useCallback, useEffect } from 'react';

/* The consistency gate. The index (MEMORY.md) is loaded every session and
   checked by nobody, so it drifts from the directory it indexes: it points at
   files that are gone, and it never names files that are there. Deterministic,
   free, honest. */

const SERIF = { fontFamily: 'var(--helicon-serif)', fontVariationSettings: "'opsz' 144" } as const;
const RED = 'var(--helicon-accent)';
const GOLD = 'var(--helicon-stale)';

interface ConsistencyReport {
  ok: boolean;
  reason?: string;
  index?: string;
  dir?: string;
  pointers?: number;
  on_disk?: number;
  external?: string[];
  dangling?: string[];
  dangling_wikilinks?: string[];
  unlisted?: string[];
  consistent?: boolean;
}

const API = (p: string) => fetch(`/api${p}`).then(r => r.json());

function SectionLabel({ children, color }: { children: React.ReactNode; color?: string }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.26em] mb-3" style={{ color: color ?? RED }}>
      {children}
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[30px] leading-none tabular-nums" style={{ ...SERIF, fontWeight: 500, color: 'var(--helicon-ink)' }}>
        {value.toLocaleString()}
      </span>
      <span className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-muted)' }}>{label}</span>
    </div>
  );
}

function FileList({ items, mono }: { items: string[]; mono?: boolean }) {
  return (
    <div className="space-y-1.5">
      {items.map((f, i) => (
        <div key={i} className="text-[12.5px]"
          style={{ color: 'var(--helicon-ink)', fontFamily: mono ? 'var(--font-mono, monospace)' : undefined }}>
          {f}
        </div>
      ))}
    </div>
  );
}

export default function Consistency() {
  const [data, setData] = useState<ConsistencyReport | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    API('/consistency').then(setData).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="pb-10">
      <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
        <div>
          <h2 className="text-[26px] leading-tight m-0" style={{ ...SERIF, fontWeight: 400, color: 'var(--helicon-ink)' }}>
            the index must match its own directory
          </h2>
          <p className="text-[13px] mt-1.5 max-w-[62ch]" style={{ color: 'var(--helicon-muted)' }}>
            The memory index is loaded every session and checked by nobody, so it drifts: it points at files that are gone, and never names files that are there.
          </p>
        </div>
        <button onClick={load} disabled={loading}
          className="text-[12px] px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90 disabled:opacity-40 shrink-0"
          style={{ background: RED }}>
          {loading ? 'checking…' : 'Re-check'}
        </button>
      </div>

      {loading && (
        <div className="py-16 text-center">
          <div className="inline-block w-8 h-1 rounded-full animate-pulse-subtle" style={{ background: RED, opacity: 0.6 }} />
          <p className="text-[13px] mt-3" style={{ color: 'var(--helicon-muted)' }}>Reading the index against its directory…</p>
        </div>
      )}

      {!loading && data && !data.ok && (
        <div className="rounded-xl border border-zinc-800/50 bg-white px-5 py-4">
          <p className="text-[13px] m-0" style={{ color: 'var(--helicon-muted)' }}>{data.reason || 'No index configured or found.'}</p>
        </div>
      )}

      {!loading && data && data.ok && (
        <div className="space-y-8">
          {/* Counts */}
          <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
            <div className="flex flex-wrap gap-x-12 gap-y-6">
              <Stat value={data.pointers ?? 0} label="pointers" />
              <Stat value={data.on_disk ?? 0} label="files on disk" />
              <Stat value={data.external?.length ?? 0} label="external links" />
            </div>
            {data.index && (
              <div className="text-[11px] mt-5 pt-4 border-t border-zinc-800/40" style={{ color: 'var(--helicon-muted)', fontFamily: 'var(--font-mono, monospace)' }}>
                {data.index}
              </div>
            )}
          </div>

          {data.consistent ? (
            <div className="rounded-2xl border px-6 py-5" style={{ borderColor: 'rgba(197,162,90,0.4)', background: 'rgba(197,162,90,0.06)' }}>
              <p className="text-[16px] m-0" style={{ ...SERIF, fontWeight: 500, color: GOLD }}>
                Index and directory agree. Nothing points at a ghost, nothing hides.
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {(data.dangling?.length ?? 0) > 0 && (
                <section>
                  <SectionLabel>Dangling · points to files that are gone</SectionLabel>
                  <div className="rounded-xl border px-5 py-4" style={{ borderColor: 'rgba(158,63,50,0.28)', background: 'rgba(158,63,50,0.04)' }}>
                    <FileList items={data.dangling!} mono />
                  </div>
                </section>
              )}

              {(data.dangling_wikilinks?.length ?? 0) > 0 && (
                <section>
                  <SectionLabel>Dangling wikilinks · named, but no file</SectionLabel>
                  <div className="rounded-xl border px-5 py-4" style={{ borderColor: 'rgba(158,63,50,0.28)', background: 'rgba(158,63,50,0.04)' }}>
                    <FileList items={data.dangling_wikilinks!} />
                  </div>
                </section>
              )}

              {(data.unlisted?.length ?? 0) > 0 && (
                <section>
                  <SectionLabel color="var(--helicon-muted)">Unlisted · files the index never names</SectionLabel>
                  <div className="rounded-xl border border-zinc-800/50 bg-white px-5 py-4">
                    <FileList items={data.unlisted!} mono />
                  </div>
                </section>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
