import { useState, useEffect, useCallback } from 'react';

/* The reading, the opening surface. The browser twin of `helicon read`: the
   record read back to you as a portrait, not a dashboard. A little mythic,
   numbers as the heroes. Qwen narrates a deterministic digest, so the prose is
   grounded and the numbers are real. Court voice throughout. */

const SERIF = { fontFamily: 'var(--helicon-serif)', fontVariationSettings: "'opsz' 144" } as const;
const GOOD = 'var(--helicon-conflict)';   // Laurel Green, the "still true" signal
const GOLD = 'var(--helicon-stale)';
const RED = 'var(--helicon-accent)';

interface Entity { name: string; type: string; n: number; }
interface OutputMix { kind: string; pct: number; }
interface Area { name: string; n: number; }
interface Health { live: number; reviewed_pct: number; rot_classes: number; rot_total: number; volatile: number; gold_rules: number; }
interface ProcessEvent { label: string | null; reviewed: number; }
interface Process { reviewed_start: number; reviewed_now: number; events: ProcessEvent[]; }
interface Digest {
  entities: Entity[]; output_mix: OutputMix[]; areas: Area[]; recent: string[];
  health: Health; process: Process | null; sources?: string[];
}
interface Move { title: string; why: string; }
interface Reading { opening: string; who: string; builder: string; standing: string; process: string; moves: Move[]; }
interface Portrait { digest: Digest; keyless: boolean; reading: Reading | null; }

const API = (p: string) => fetch(`/api${p}`).then(r => r.json());

// The summit, built of tonal stone tiles; terracotta shows only on the cracked
// ridge tile. Matches the locked tesserae identity.
function Summit({ size = 56 }: { size?: number }) {
  return (
    <svg width={size} height={size * 0.6} viewBox="0 0 44 26" fill="none"
      stroke="var(--helicon-ink)" strokeWidth={1.4} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
      <path d="M2.5 23 L14 5 L22 16.5" opacity={0.5} />
      <path d="M15 23 L27.5 4 L41.5 23" />
    </svg>
  );
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[10px] uppercase tracking-[0.26em] mb-2.5" style={{ color: RED }}>
      {children}
    </div>
  );
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[11px] px-2 py-0.5 rounded-full whitespace-nowrap"
      style={{ background: 'rgba(60,40,20,0.05)', color: 'var(--helicon-ink)', border: '1px solid rgba(60,40,20,0.10)' }}>
      {children}
    </span>
  );
}

// One health number, big, serif, tabular, colored by meaning.
function Hero({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className="flex flex-col gap-1 min-w-[64px]">
      <span className="text-[38px] leading-none tabular-nums" style={{ ...SERIF, fontWeight: 500, color }}>
        {value}
      </span>
      <span className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-muted)' }}>{label}</span>
    </div>
  );
}

function LoadingReading() {
  return (
    <div className="py-24 flex flex-col items-center text-center">
      <div className="animate-pulse-subtle"><Summit size={64} /></div>
      <p className="mt-5 text-[20px]" style={{ ...SERIF, fontWeight: 400, color: 'var(--helicon-ink)' }}>
        Reading the record…
      </p>
      <p className="mt-1.5 text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
        Composing who the record shows you are. This takes a moment; the reading is written, not cached.
      </p>
    </div>
  );
}

export default function Reading() {
  const [data, setData] = useState<Portrait | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    API('/portrait').then(setData).finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) return <LoadingReading />;
  if (!data) return null;

  const { digest, keyless, reading } = data;
  const h = digest.health;
  const proc = digest.process;
  const gain = proc ? proc.reviewed_now - proc.reviewed_start : 0;

  return (
    <div className="pb-10">
      {/* Watercolor hero band — the record opens on the mountain */}
      <div
        className="relative mb-9 overflow-hidden"
        style={{ height: 300, borderRadius: 'var(--helicon-radius)', boxShadow: 'var(--helicon-shadow)', border: '1px solid var(--helicon-line)' }}
      >
        <img
          src="/mountain.png"
          alt="Mount Helicon"
          className="absolute inset-0 w-full h-full object-cover"
          style={{ objectPosition: 'center 42%', animation: 'heliconMist 30s ease-in-out infinite' }}
        />
        <div className="absolute inset-0" style={{ background: 'linear-gradient(180deg, rgba(241,236,225,0.04) 38%, rgba(241,236,225,0.62) 100%)' }} />
        <div className="absolute left-8 top-7">
          <div className="text-[12px] uppercase" style={{ letterSpacing: '0.34em', lineHeight: 2, fontWeight: 500, color: 'var(--helicon-ink)' }}>Mount Helicon</div>
          <div className="text-[27px] leading-none" style={{ ...SERIF, fontStyle: 'italic', fontWeight: 400, color: 'var(--helicon-ink)' }}>the reading</div>
          <div style={{ width: 44, height: 1, background: 'var(--helicon-faint)', marginTop: 12 }} />
        </div>
        <button
          onClick={load}
          className="absolute right-6 top-6 text-[12px] px-3 py-1.5 rounded-lg transition-colors"
          style={{ color: 'var(--helicon-ink)', background: 'rgba(247,243,235,0.72)', border: '1px solid var(--helicon-line)' }}
        >
          Read again
        </button>
      </div>

      {/* Hero opening line */}
      {reading?.opening && (
        <h1 className="text-[clamp(28px,4.6vw,46px)] leading-[1.12] max-w-[22ch] m-0"
          style={{ ...SERIF, fontWeight: 500, color: 'var(--helicon-ink)' }}>
          {reading.opening}
        </h1>
      )}

      {keyless && (
        <p className="mt-4 text-[13px] max-w-[60ch]" style={{ color: 'var(--helicon-muted)' }}>
          The reading needs a Qwen key; the record below is real.
        </p>
      )}

      {/* Prose blocks */}
      {reading && (
        <div className="mt-10 grid md:grid-cols-2 gap-x-10 gap-y-8">
          <div>
            <SectionLabel>Who the record shows</SectionLabel>
            <p className="text-[15.5px] leading-relaxed m-0" style={{ color: 'var(--helicon-ink)' }}>{reading.who}</p>
          </div>
          <div>
            <SectionLabel>The builder</SectionLabel>
            <p className="text-[15.5px] leading-relaxed m-0" style={{ color: 'var(--helicon-ink)' }}>{reading.builder}</p>
          </div>
        </div>
      )}

      {/* Grounding strip */}
      <div className="mt-10 rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-6 py-5 space-y-4">
        {digest.entities.length > 0 && (
          <div className="flex gap-3 items-baseline flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.16em] w-[92px] shrink-0" style={{ color: 'var(--helicon-muted)' }}>Recurring</span>
            <div className="flex flex-wrap gap-1.5">
              {digest.entities.slice(0, 10).map(e => <Chip key={e.name}>{e.name}</Chip>)}
            </div>
          </div>
        )}
        {digest.output_mix.length > 0 && (
          <div className="flex gap-3 items-baseline flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.16em] w-[92px] shrink-0" style={{ color: 'var(--helicon-muted)' }}>You make</span>
            <div className="flex flex-wrap gap-1.5">
              {digest.output_mix.slice(0, 6).map(m => (
                <Chip key={m.kind}>{m.kind} <span className="tabular-nums" style={{ color: GOLD }}>{m.pct}%</span></Chip>
              ))}
            </div>
          </div>
        )}
        {digest.areas.length > 0 && (
          <div className="flex gap-3 items-baseline flex-wrap">
            <span className="text-[10px] uppercase tracking-[0.16em] w-[92px] shrink-0" style={{ color: 'var(--helicon-muted)' }}>You invest</span>
            <div className="flex flex-wrap gap-1.5">
              {digest.areas.slice(0, 8).map(a => <Chip key={a.name}>{a.name}</Chip>)}
            </div>
          </div>
        )}
      </div>

      {/* The process at work */}
      {proc && proc.events.length > 1 && (
        <section className="mt-12">
          <SectionLabel>The process at work</SectionLabel>
          {reading?.process && (
            <p className="text-[15px] leading-relaxed max-w-[64ch] mb-5" style={{ color: 'var(--helicon-ink)' }}>{reading.process}</p>
          )}
          <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-6 py-5">
            <div className="flex items-baseline gap-3 mb-4">
              <span className="text-[13px]" style={{ color: 'var(--helicon-muted)' }}>Reviewed, over time</span>
              <span className="text-[13px] tabular-nums ml-auto" style={{ color: 'var(--helicon-muted)' }}>
                {proc.reviewed_start.toLocaleString()} <span style={{ opacity: 0.5 }}>→</span> <span style={{ color: GOLD }}>{proc.reviewed_now.toLocaleString()}</span>
              </span>
              {gain > 0 && (
                <span className="text-[16px] tabular-nums" style={{ ...SERIF, fontWeight: 600, color: GOOD }}>+{gain.toLocaleString()}</span>
              )}
            </div>
            <div className="space-y-2">
              {proc.events.map((ev, i) => {
                const pct = proc.reviewed_now > 0 ? Math.max(3, (ev.reviewed / proc.reviewed_now) * 100) : 3;
                return (
                  <div key={i} className="flex items-center gap-3">
                    <span className="text-[11px] w-[120px] shrink-0 truncate" style={{ color: 'var(--helicon-muted)' }} title={ev.label ?? ''}>
                      {ev.label ?? '·'}
                    </span>
                    <div className="flex-1 h-2.5 rounded-full overflow-hidden" style={{ background: 'rgba(60,40,20,0.06)' }}>
                      <div className="h-full rounded-full transition-all duration-700" style={{ width: `${pct}%`, background: GOLD, opacity: 0.55 + 0.45 * (i / Math.max(1, proc.events.length - 1)) }} />
                    </div>
                    <span className="text-[11px] tabular-nums w-[52px] text-right" style={{ color: 'var(--helicon-ink)' }}>{ev.reviewed.toLocaleString()}</span>
                  </div>
                );
              })}
            </div>
          </div>
        </section>
      )}

      {/* Standing, the health numbers as heroes */}
      <section className="mt-12">
        <SectionLabel>Standing</SectionLabel>
        {reading?.standing && (
          <p className="text-[15px] leading-relaxed max-w-[64ch] mb-6" style={{ color: 'var(--helicon-ink)' }}>{reading.standing}</p>
        )}
        <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6 flex flex-wrap gap-x-10 gap-y-6">
          <Hero value={`${h.reviewed_pct}%`} label="reviewed" color={h.reviewed_pct >= 50 ? GOOD : GOLD} />
          <Hero value={`${h.rot_classes}/${h.rot_total}`} label="rot classes firing" color={h.rot_classes > 0 ? RED : GOOD} />
          <Hero value={h.volatile.toLocaleString()} label="volatile facts" color={RED} />
          <Hero value={h.live.toLocaleString()} label="live memories" color={GOLD} />
          <Hero value={h.gold_rules.toLocaleString()} label="golden rules" color={GOLD} />
        </div>
      </section>

      {/* What the record argues for */}
      {reading && reading.moves.length > 0 && (
        <section className="mt-12">
          <SectionLabel>What the record argues for</SectionLabel>
          <div className="space-y-4">
            {reading.moves.map((m, i) => (
              <div key={i} className="rounded-xl bg-white shadow-sm border border-zinc-800/50 px-6 py-5 flex gap-4 items-baseline">
                <span className="text-[15px] tabular-nums" style={{ ...SERIF, color: GOLD }}>{String(i + 1).padStart(2, '0')}</span>
                <div>
                  <h3 className="text-[18px] leading-snug m-0" style={{ ...SERIF, fontWeight: 600, color: 'var(--helicon-ink)' }}>{m.title}</h3>
                  <p className="text-[13.5px] mt-1 m-0" style={{ color: 'var(--helicon-muted)' }}>{m.why}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Keyless: recent record as grounding */}
      {keyless && digest.recent.length > 0 && (
        <section className="mt-12">
          <SectionLabel>Most recent in the record</SectionLabel>
          <div className="flex flex-wrap gap-1.5">
            {digest.recent.slice(0, 8).map((t, i) => <Chip key={i}>{t}</Chip>)}
          </div>
        </section>
      )}
    </div>
  );
}
