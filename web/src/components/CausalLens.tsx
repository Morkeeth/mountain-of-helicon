import { useState } from 'react';

type Memory = {
  rank: number; id: string; title: string; source: string;
  age_days: number | null; confidence: number; status: string; acted_on: boolean;
};

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const ACCENT = 'var(--helicon-accent)';

export default function CausalLens() {
  const [task, setTask] = useState('');
  const [mems, setMems] = useState<Memory[] | null>(null);
  const [asked, setAsked] = useState('');
  const [loading, setLoading] = useState(false);

  async function trace(e?: React.FormEvent) {
    e?.preventDefault();
    if (!task.trim()) return;
    setLoading(true); setAsked(task);
    try {
      const r = await fetch(`/api/lens?task=${encodeURIComponent(task)}&k=8`);
      const d = await r.json();
      setMems(d.memories || []);
    } finally { setLoading(false); }
  }

  return (
    <div className="max-w-2xl">
      <h2 style={{ fontFamily: 'var(--helicon-serif)', color: INK }} className="text-[27px] leading-tight">
        Causal Lens
      </h2>
      <p className="mt-1.5 text-[14px] leading-relaxed" style={{ color: MUTED, maxWidth: '54ch' }}>
        Every answer stands on memory. Trace which memories produced one — then correct
        the premise upstream instead of editing the output.
      </p>

      <form onSubmit={trace} className="mt-5 flex gap-2">
        <input
          value={task}
          onChange={e => setTask(e.target.value)}
          placeholder="An answer or task the agent worked on…"
          className="flex-1 px-3.5 py-2 rounded-lg text-[14px] outline-none"
          style={{ background: 'var(--helicon-panel-2)', color: INK, border: '1px solid var(--helicon-line)' }}
        />
        <button
          type="submit"
          className="px-4 py-2 rounded-lg text-[13px] font-medium text-[#F4EFE7] transition-all hover:brightness-110 active:scale-95"
          style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}
        >Trace</button>
      </form>

      {loading && <div className="mt-8 text-[13px]" style={{ color: MUTED }}>…tracing the memory</div>}

      {mems && !loading && (
        <div className="mt-8">
          {/* the answer anchor */}
          <div className="pl-4 border-l-2" style={{ borderColor: ACCENT }}>
            <div className="text-[10px] uppercase tracking-wider mb-1" style={{ color: MUTED, fontFamily: 'var(--helicon-sans)' }}>the answer</div>
            <div style={{ fontFamily: 'var(--helicon-serif)', color: INK }} className="text-[17px] leading-snug">“{asked}”</div>
          </div>

          {mems.length === 0 && (
            <div className="mt-6 text-[13px]" style={{ color: MUTED }}>No memory stands behind this answer.</div>
          )}

          {/* the causal threads: each memory hangs off the answer */}
          <div className="mt-1">
            {mems.map(m => <MemoryRow key={m.id} m={m} />)}
          </div>
        </div>
      )}
    </div>
  );
}

function MemoryRow({ m }: { m: Memory }) {
  const stale = m.age_days != null && m.age_days > 90;
  const retired = !['approved', 'pending', ''].includes(m.status);
  const conf = Math.max(0, Math.min(1, m.confidence));
  return (
    <div className="relative pl-4 py-3 border-l-2" style={{ borderColor: 'var(--helicon-line-2)' }}>
      {/* thread node */}
      <span className="absolute left-[-5px] top-[18px] w-2 h-2 rounded-full"
        style={{ background: retired ? 'var(--helicon-stale)' : ACCENT }} />
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[14px] leading-snug" style={{ color: INK }}>
          <span style={{ color: MUTED }} className="mr-1.5 tabular-nums text-[12px]">{m.rank}.</span>
          {m.title || m.id}
        </div>
        <div className="shrink-0 tabular-nums text-[11px]" style={{ color: MUTED, fontFamily: 'var(--helicon-mono)' }}>
          {m.age_days != null ? `${m.age_days}d` : '—'}
        </div>
      </div>
      {/* influence bar + provenance */}
      <div className="mt-1.5 flex items-center gap-2.5">
        <div className="h-1 rounded-full overflow-hidden" style={{ width: 96, background: 'var(--helicon-mist)' }}>
          <div className="h-full rounded-full" style={{ width: `${conf * 100}%`, background: ACCENT }} />
        </div>
        <span className="text-[11px]" style={{ color: MUTED, fontFamily: 'var(--helicon-sans)' }}>{m.source}</span>
        {stale && <span className="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded" style={{ color: 'var(--helicon-stale)', background: 'rgba(198,150,63,0.12)' }}>stale</span>}
        {retired && <span className="text-[10px] uppercase tracking-wide" style={{ color: 'var(--helicon-stale)' }}>{m.status}</span>}
        {m.acted_on && <span className="text-[10px] uppercase tracking-wide" style={{ color: ACCENT }}>acted-on</span>}
      </div>
    </div>
  );
}
