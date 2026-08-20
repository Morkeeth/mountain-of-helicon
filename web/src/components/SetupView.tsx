import { useEffect, useState, useCallback } from 'react';

/* THE SETUP — the census of the stack and the two-axis score (proposal v3).
   Axis 1 PRIMARY: you vs you — dated snapshots, the score is a trend, never a
   lone number; before the second reading the trend honestly says it can't
   exist yet. Axis 2 SECONDARY: you vs the frontier — each chip is a
   deterministic probe with a citation; FAIL and UNMEASURED render as
   themselves, never as green. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';
const PANEL = 'var(--helicon-panel-2)';
const LINE = 'var(--helicon-line)';

interface Cell { value: number | null; measured: boolean; how: string; names?: string[] }
interface FileStat { label: string; path: string; exists: boolean; lines?: number; bytes?: number; age_days?: number }
interface Chip { id: string; claim: string; verdict: 'PASS' | 'FAIL' | 'UNMEASURED'; probe: string; source: string }
interface Snapshot { day: string; skills: number | null; routines: number | null; memories_live: number | null; memories_retired: number | null; sessions: number | null; context_bytes: number | null; chips_pass: number; chips_fail: number; chips_unmeasured: number }
interface SetupData {
  census: {
    skills: Cell; routines: Cell; sessions: Cell;
    memories: { live: Cell; retired: Cell; files?: Cell };
    context_files: FileStat[];
    connectors: Record<string, boolean>;
  };
  axis2: Chip[];
  snapshots: Snapshot[];
  ran_at: string; cached: boolean;
}

const VERDICT_COLOR: Record<Chip['verdict'], string> = {
  PASS: 'var(--helicon-good, #3a7d44)',
  FAIL: ACCENT,
  UNMEASURED: FAINT,
};

function CensusRow({ label, cell }: { label: string; cell: Cell }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2" style={{ borderBottom: `1px solid ${LINE}` }}>
      <span className="text-[13px] w-40 shrink-0" style={{ color: INK }}>{label}</span>
      {cell.measured ? (
        <span className="tabular-nums text-[15px]" style={{ fontFamily: MONO, color: INK }}>{cell.value?.toLocaleString()}</span>
      ) : (
        <span className="text-[12px] uppercase tracking-wider" style={{ color: FAINT }}>unmeasured</span>
      )}
      <span className="text-[11px] leading-snug min-w-0 flex-1 basis-40 break-words" style={{ color: MUTED }}>{cell.how}</span>
    </div>
  );
}

/* The trend, honest about its own length. One snapshot is a baseline, not a
   trend; the delta line only exists from the second reading on. */
function Trend({ snaps }: { snaps: Snapshot[] }) {
  if (snaps.length === 0) {
    return <p className="text-[13px]" style={{ color: MUTED }}>
      No reading recorded yet. Record the first — the trend begins with the second.
    </p>;
  }
  const [latest, prev] = snaps; // API returns newest first
  if (!prev) {
    return <p className="text-[13px]" style={{ color: MUTED }}>
      First reading recorded {latest.day}. The trend begins with the second reading.
    </p>;
  }
  const delta = (a: number | null, b: number | null) =>
    a == null || b == null ? '—' : (a - b >= 0 ? `+${a - b}` : `${a - b}`);
  const rows: [string, number | null, string][] = [
    ['memories live', latest.memories_live, delta(latest.memories_live, prev.memories_live)],
    ['sessions', latest.sessions, delta(latest.sessions, prev.sessions)],
    ['frontier checks passing', latest.chips_pass, delta(latest.chips_pass, prev.chips_pass)],
    ['always-loaded bytes', latest.context_bytes, delta(latest.context_bytes, prev.context_bytes)],
  ];
  return (
    <div>
      <p className="text-[11px] uppercase tracking-[0.15em] mb-2" style={{ color: MUTED }}>
        {latest.day} vs {prev.day} · {snaps.length} readings held
      </p>
      {rows.map(([label, v, d]) => (
        <div key={label} className="flex items-baseline gap-3 py-1">
          <span className="text-[13px] w-44" style={{ color: INK }}>{label}</span>
          <span className="tabular-nums text-[14px]" style={{ fontFamily: MONO, color: INK }}>{v?.toLocaleString() ?? '—'}</span>
          <span className="tabular-nums text-[12px]" style={{ fontFamily: MONO, color: MUTED }}>{d}</span>
        </div>
      ))}
    </div>
  );
}

export default function SetupView() {
  const [data, setData] = useState<SetupData | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [recording, setRecording] = useState(false);

  const load = useCallback((fresh = false) => {
    fetch(`/api/setup${fresh ? '?fresh=1' : ''}`)
      .then(r => r.json()).then(setData)
      .catch(e => setErr(e instanceof Error ? e.message : 'load failed'));
  }, []);
  useEffect(() => { load(); }, [load]);

  const record = async () => {
    setRecording(true);
    try {
      await fetch('/api/setup/snapshot', { method: 'POST' });
      load(true);
    } finally { setRecording(false); }
  };

  if (err) return <p className="py-16 text-center text-[13px]" style={{ color: ACCENT }}>Setup census failed to load: {err}</p>;
  if (!data) return <p className="py-16 text-center text-[13px]" style={{ color: MUTED }}>…</p>;

  const { census, axis2, snapshots } = data;
  const passing = axis2.filter(c => c.verdict === 'PASS').length;
  const measurable = axis2.filter(c => c.verdict !== 'UNMEASURED').length;

  return (
    <div className="max-w-2xl mx-auto pb-16">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h1 style={{ fontFamily: SERIF, fontWeight: 300, color: INK }} className="text-[28px]">The Setup</h1>
        <button onClick={record} disabled={recording}
          className="text-[12px] px-3 py-1.5 rounded-lg shrink-0 transition-all hover:brightness-110 disabled:opacity-40"
          style={{ border: `1px solid ${LINE}`, color: INK }}>
          {recording ? 'Recording…' : "Record today's reading"}
        </button>
      </div>
      <p className="text-[12px] mb-8" style={{ color: MUTED }}>
        census {data.cached ? 'cached, ' : ''}taken {data.ran_at?.slice(0, 16).replace('T', ' ')} UTC
      </p>

      {/* AXIS 1 — you vs you (primary) */}
      <section className="mb-9">
        <h2 className="text-[11px] uppercase tracking-[0.16em] mb-3" style={{ color: ACCENT }}>You vs you — the primary axis</h2>
        <Trend snaps={snapshots} />
      </section>

      {/* AXIS 2 — you vs the frontier (secondary) */}
      <section className="mb-9">
        <h2 className="text-[11px] uppercase tracking-[0.16em] mb-1" style={{ color: MUTED }}>You vs the frontier — secondary</h2>
        <p className="text-[12px] mb-3" style={{ color: MUTED }}>
          <span style={{ fontFamily: MONO, color: INK }}>{passing}/{measurable}</span> measurable checks pass ·
          reference: docs/memory-context-frontier-2026-08.md
        </p>
        <div className="space-y-2">
          {axis2.map(c => (
            <div key={c.id} className="p-3 rounded-lg" style={{ background: PANEL, border: `1px solid ${LINE}` }}>
              <div className="flex items-baseline gap-2.5">
                <span className="text-[10px] uppercase tracking-wider w-24 shrink-0" style={{ color: VERDICT_COLOR[c.verdict], fontWeight: 700 }}>{c.verdict}</span>
                <span className="text-[13px] min-w-0 flex-1 break-words" style={{ color: INK }}>{c.claim}</span>
              </div>
              <p className="text-[11.5px] mt-1 md:ml-[6.6rem] break-words" style={{ fontFamily: MONO, color: MUTED }}>{c.probe}</p>
              <p className="text-[10.5px] mt-0.5 md:ml-[6.6rem] break-words" style={{ color: FAINT }}>{c.source}</p>
            </div>
          ))}
        </div>
      </section>

      {/* The census */}
      <section className="mb-9">
        <h2 className="text-[11px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>The census</h2>
        <CensusRow label="Skills" cell={census.skills} />
        <CensusRow label="Routines" cell={census.routines} />
        <CensusRow label="Memories, live" cell={census.memories.live} />
        <CensusRow label="Memories, retired" cell={census.memories.retired} />
        {census.memories.files && <CensusRow label="Memory files" cell={census.memories.files} />}
        <CensusRow label="Sessions" cell={census.sessions} />
      </section>

      {/* Where context lives */}
      <section>
        <h2 className="text-[11px] uppercase tracking-[0.16em] mb-2" style={{ color: MUTED }}>Where context lives</h2>
        {census.context_files.map(f => (
          <div key={f.label} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2" style={{ borderBottom: `1px solid ${LINE}` }}>
            <span className="text-[13px] w-56 shrink-0" style={{ color: INK }}>{f.label}</span>
            {f.exists ? (
              <>
                <span className="tabular-nums text-[12px]" style={{ fontFamily: MONO, color: INK }}>{f.lines} lines</span>
                <span className="tabular-nums text-[12px]" style={{ fontFamily: MONO, color: MUTED }}>{((f.bytes ?? 0) / 1024).toFixed(1)}KB</span>
                <span className="text-[11px]" style={{ color: FAINT }}>touched {f.age_days}d ago</span>
              </>
            ) : (
              <span className="text-[12px]" style={{ color: FAINT }}>not found</span>
            )}
          </div>
        ))}
        <p className="text-[11px] mt-2" style={{ color: FAINT }}>
          Connectors: {Object.entries(census.connectors).map(([k, v]) => `${k} ${v ? 'on' : 'off'}`).join(' · ') || 'none configured'}
        </p>
      </section>
    </div>
  );
}
