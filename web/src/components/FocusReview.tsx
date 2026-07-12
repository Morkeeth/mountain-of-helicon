import { useState, useMemo } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse } from '../api';

/* Zen review — one thing at a time. The wall of findings collapses into a single
   calm question: rule this, it advances, breathe. The full dashboard stays one
   click away ("see all"). Only what a human must rule on enters the queue; the
   aging pile is auto-managed and never shown here. */

const INK = 'var(--helicon-ink)';
const MUTED = 'var(--helicon-muted)';
const FAINT = 'var(--helicon-faint)';
const ACCENT = 'var(--helicon-accent)';
const MIST = 'var(--helicon-mist)';
const SERIF = 'var(--helicon-serif)';
const MONO = 'var(--helicon-mono)';

const SEV: Record<string, number> = { critical: 0, warning: 1, info: 2 };
function sevColor(s: string) {
  return s === 'critical' ? ACCENT : s === 'warning' ? 'var(--helicon-stale)' : FAINT;
}

export default function FocusReview({ data, onActed, onSeeAll }: {
  data: FindingsResponse | null;
  onActed: (f: Finding) => void;
  onSeeAll: () => void;
}) {
  // attention queue: only human-decision findings, most consequential first
  const queue = useMemo(() =>
    (data?.findings || [])
      .filter(f => f.severity === 'critical' || f.severity === 'warning')
      .sort((a, b) => (SEV[a.severity] ?? 2) - (SEV[b.severity] ?? 2)),
    [data]);

  const [i, setI] = useState(0);
  const [acting, setActing] = useState(false);
  const ambient = data?.summary?.ambient ?? 0;
  const advance = (f?: Finding) => { if (f) onActed(f); setI(x => x + 1); };

  if (!data) return <div className="py-24 text-center text-[13px]" style={{ color: MUTED }}>…</div>;

  if (queue.length === 0 || i >= queue.length) {
    return (
      <div className="max-w-lg mx-auto py-24 text-center animate-fade-in">
        <div style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[30px] leading-tight">
          The record is settled.
        </div>
        <p className="mt-3 text-[14px] leading-relaxed" style={{ color: MUTED }}>
          Nothing needs your ruling.{ambient > 0 ? ` ${ambient} aging findings are auto-managed — no action needed.` : ''}
        </p>
        <button onClick={onSeeAll} className="mt-7 text-[13px] transition-colors hover:opacity-70"
          style={{ color: ACCENT }}>See all findings →</button>
      </div>
    );
  }

  const f = queue[i];
  const auditId = f.id.startsWith('audit-') ? parseInt(f.id.slice(6), 10) : null;
  const confirmAudit = async (d: string) => {
    if (auditId === null) return advance(f);
    setActing(true);
    try { await api.confirmAudit(auditId, d); } finally { setActing(false); }
    advance(f);
  };
  const review = async (d: string) => {
    if (!f.cube_id) return advance(f);
    setActing(true);
    try { await api.submitReview(f.cube_id, d, `via focus: ${f.kind}`, 0); } finally { setActing(false); }
    advance(f);
  };

  return (
    <div className="max-w-xl mx-auto">
      {/* quiet progress + escape */}
      <div className="flex items-center justify-between mb-12">
        <div className="flex items-center gap-3">
          <span className="tabular-nums text-[13px]" style={{ color: INK, fontFamily: MONO }}>
            {i + 1}<span style={{ color: FAINT }}> / {queue.length}</span>
          </span>
          <div className="h-[3px] w-28 rounded-full overflow-hidden" style={{ background: MIST }}>
            <div className="h-full rounded-full" style={{ width: `${(i / queue.length) * 100}%`, background: ACCENT, transition: 'width 300ms ease-out' }} />
          </div>
          <span className="text-[11px]" style={{ color: FAINT }}>~{Math.max(1, Math.ceil((queue.length - i) * 0.5))} min</span>
        </div>
        <button onClick={onSeeAll} className="text-[12px] transition-colors hover:opacity-70" style={{ color: MUTED }}>see all →</button>
      </div>

      {/* the one thing */}
      <div key={f.id} className="animate-fade-in">
        <div className="text-[10px] uppercase tracking-[0.15em] mb-4" style={{ color: sevColor(f.severity) }}>
          {f.severity} · {(f.kind || '').replace(/_/g, ' ')}
        </div>
        <h2 style={{ fontFamily: SERIF, color: INK, fontWeight: 300 }} className="text-[23px] leading-snug">
          {f.why}
        </h2>
        <p className="mt-2.5 text-[13px]" style={{ color: MUTED }}>{f.title}</p>

        {f.evidence_preview && <Receipt text={f.evidence_preview} src={`${f.source || ''}${f.source_ref ? ' · ' + f.source_ref : ''}`} />}

        <div className="mt-9 flex items-center gap-2.5 flex-wrap">
          {f.suggested_action === 'fix_skill' ? (
            <><CmdChip cmd="helicon fix-skills --apply" /><Later onClick={() => advance(f)} /></>
          ) : f.suggested_action === 'reconcile' ? (
            <><CmdChip cmd="helicon reconcile --apply" /><Later onClick={() => advance(f)} /></>
          ) : f.suggested_action === 'kill_stale' && auditId !== null ? (
            <><Primary disabled={acting} onClick={() => confirmAudit('dismissed')}>Keep</Primary>
              <Ghost disabled={acting} onClick={() => confirmAudit('acted')}>Retire</Ghost>
              <Later onClick={() => advance(f)} /></>
          ) : (
            <><Primary disabled={acting} onClick={() => (f.cube_id ? review('approved') : confirmAudit('dismissed'))}>Confirm — still true</Primary>
              <Ghost disabled={acting} onClick={() => (f.cube_id ? review('killed') : confirmAudit('acted'))}>Retire</Ghost>
              <Later onClick={() => advance(f)} /></>
          )}
        </div>
      </div>
    </div>
  );
}

function Receipt({ text, src }: { text: string; src: string }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-5">
      <button onClick={() => setOpen(o => !o)} className="text-[12px] transition-colors hover:opacity-70" style={{ color: ACCENT }}>
        {open ? 'hide the receipt' : 'show the receipt'}
      </button>
      {open && (
        <div className="mt-2.5 animate-fade-in">
          <pre className="text-[11px] p-3.5 rounded-lg whitespace-pre-wrap leading-relaxed max-h-52 overflow-auto"
            style={{ color: MUTED, background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>{text}</pre>
          {src && <p className="text-[10px] mt-1.5" style={{ color: FAINT }}>{src}</p>}
        </div>
      )}
    </div>
  );
}

function Primary({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="px-4 py-2 rounded-lg text-[13px] font-medium text-[#F4EFE7] transition-all hover:brightness-110 active:scale-95 disabled:opacity-40"
      style={{ backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }}>{children}</button>
  );
}
function Ghost({ children, onClick, disabled }: { children: React.ReactNode; onClick: () => void; disabled?: boolean }) {
  return (
    <button onClick={onClick} disabled={disabled}
      className="px-4 py-2 rounded-lg text-[13px] transition-all active:scale-95 disabled:opacity-40 bg-white"
      style={{ border: '1px solid var(--helicon-line-2)', color: INK }}>{children}</button>
  );
}
function Later({ onClick }: { onClick: () => void }) {
  return <button onClick={onClick} className="px-3 py-2 text-[13px] transition-colors hover:opacity-70" style={{ color: FAINT }}>Later</button>;
}
function CmdChip({ cmd }: { cmd: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button onClick={() => { navigator.clipboard?.writeText(cmd); setCopied(true); setTimeout(() => setCopied(false), 1200); }}
      className="px-3 py-2 rounded-lg text-[12px] transition-colors hover:opacity-80"
      style={{ fontFamily: MONO, color: INK, background: 'var(--helicon-panel-2)', border: '1px solid var(--helicon-line)' }}>
      {copied ? 'copied ✓' : `${cmd}  ⧉`}
    </button>
  );
}
