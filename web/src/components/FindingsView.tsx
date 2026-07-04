import { useState } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse } from '../api';

/* FINDINGS — the heart of the dashboard. One list of everything that failed
   a check, unified across audit / skills / battery. The WHY sentence leads;
   the title is context. Every row carries its fix. Real data only. */

const KIND_ORDER = ['regret', 'agent-flag', 'temporal', 'decay', 'factual', 'logical', 'skill', 'battery'];

const KIND_LABEL: Record<string, string> = {
  regret: 'Regret',
  'agent-flag': 'Flagged',
  temporal: 'Temporal',
  decay: 'Decay',
  factual: 'Factual',
  logical: 'Logical',
  skill: 'Skill',
  battery: 'Battery',
};

const KIND_HINT: Record<string, string> = {
  regret: 'you retired it, retrieval keeps wanting it back',
  'agent-flag': 'an agent flagged this at point of use',
  temporal: 'time-relative wording gone stale',
  decay: 'confidence below the keep threshold',
  factual: 'contradicts another memory',
  logical: 'pattern no longer supported',
  skill: 'skills library rot',
  battery: 'retrieval task serving broken context',
};

function sevColor(sev: string): string {
  if (sev === 'critical') return 'var(--helicon-accent)';
  if (sev === 'warning') return 'var(--helicon-stale)';
  return '#a1a1aa';
}

// Copyable CLI one-liner chip — the fix for skill/reconcile findings.
function CopyChip({ cmd, title }: { cmd: string; title?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      title={title}
      onClick={e => {
        e.stopPropagation();
        navigator.clipboard.writeText(cmd).then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        });
      }}
      className="flex items-center gap-2 text-[11px] px-2.5 py-1 rounded-md border transition-all active:scale-95 bg-white shadow-sm font-mono"
      style={{ borderColor: 'var(--helicon-line)', color: '#443e36' }}
    >
      <code>{cmd}</code>
      <span style={{ color: copied ? 'var(--helicon-accent)' : 'var(--helicon-muted)', fontFamily: 'Inter, sans-serif' }}>
        {copied ? 'copied' : 'copy'}
      </span>
    </button>
  );
}

function ActionButton({ label, tone, disabled, onClick }: {
  label: string;
  tone: 'kill' | 'keep' | 'muted';
  disabled?: boolean;
  onClick: () => void;
}) {
  const styles =
    tone === 'kill'
      ? { borderColor: 'rgba(194,94,58,0.35)', color: 'var(--helicon-accent)' }
      : tone === 'keep'
        ? { borderColor: 'var(--helicon-line)', color: '#443e36' }
        : { borderColor: 'transparent', color: 'var(--helicon-muted)' };
  return (
    <button
      onClick={e => { e.stopPropagation(); onClick(); }}
      disabled={disabled}
      className="text-[11px] px-2.5 py-1 rounded-md border transition-all active:scale-95 disabled:opacity-30 bg-white shadow-sm"
      style={styles}
    >
      {label}
    </button>
  );
}

function FindingRow({ f, onGone }: { f: Finding; onGone: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [acting, setActing] = useState(false);

  const auditId = f.id.startsWith('audit-') ? parseInt(f.id.slice(6), 10) : null;

  const confirmAudit = async (decision: string) => {
    if (auditId === null) return;
    setActing(true);
    try { await api.confirmAudit(auditId, decision); } finally { setActing(false); }
    onGone();
  };

  const review = async (decision: string) => {
    if (!f.cube_id) return;
    setActing(true);
    try { await api.submitReview(f.cube_id, decision, `via findings: ${f.kind}`, 0); } finally { setActing(false); }
    onGone();
  };

  const actions = (() => {
    if (f.suggested_action === 'fix_skill') {
      return <CopyChip cmd="helicon fix-skills --apply" title="writes descriptions back with .bak backups" />;
    }
    if (f.suggested_action === 'reconcile') {
      return (
        <>
          <CopyChip cmd="helicon reconcile --apply" title="retires cubes a re-scan no longer sees" />
          {auditId !== null && <ActionButton label="Skip" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />}
        </>
      );
    }
    if (f.suggested_action === 'kill_stale' && auditId !== null) {
      return (
        <>
          <ActionButton label={acting ? '...' : 'Kill stale'} tone="kill" disabled={acting} onClick={() => confirmAudit('acted')} />
          <ActionButton label="Skip" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />
        </>
      );
    }
    // review (and battery kill_stale rows, which carry a cube): keep/kill the cube itself
    if (f.cube_id) {
      return (
        <>
          <ActionButton label={acting ? '...' : 'Keep'} tone="keep" disabled={acting} onClick={() => review('approved')} />
          <ActionButton label={acting ? '...' : 'Kill'} tone="kill" disabled={acting} onClick={() => review('killed')} />
          {auditId !== null && <ActionButton label="Skip" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />}
        </>
      );
    }
    if (auditId !== null) {
      return <ActionButton label="Skip" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />;
    }
    return null;
  })();

  return (
    <div className="animate-fade-in">
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(x => !x)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(x => !x); } }}
        className="flex items-start gap-3 py-3 px-4 hover:bg-zinc-800/10 transition-colors cursor-pointer"
      >
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0 mt-[7px]"
          style={{ background: sevColor(f.severity) }}
        />

        <div className="flex-1 min-w-0">
          {/* The WHY sentence is the finding — it leads. */}
          <p className="text-[13px] text-zinc-200 leading-snug">{f.why}</p>
          <p className="text-[11px] text-zinc-600 leading-snug mt-0.5 truncate">
            {f.title}
            <span className="text-zinc-700"> · {KIND_LABEL[f.kind] || f.kind}</span>
          </p>
        </div>

        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`text-zinc-600 shrink-0 mt-1.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>

        <div className="flex gap-1.5 shrink-0 items-center" onClick={e => e.stopPropagation()}>
          {actions}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 pl-9 animate-fade-in">
          {f.evidence_preview ? (
            <pre className="text-[11px] text-zinc-400 bg-zinc-900/50 p-3 rounded-lg whitespace-pre-wrap leading-relaxed border border-zinc-800/40 max-h-44 overflow-auto">
              {f.evidence_preview}
            </pre>
          ) : (
            <p className="text-[11px] text-zinc-600">No evidence preview for this finding.</p>
          )}
          <p className="text-[10px] text-zinc-700 mt-2">
            {f.source} · {f.source_ref}
          </p>
        </div>
      )}
    </div>
  );
}

export default function FindingsView({ data, onReload, onActed, batteryLoading, batteryIncluded }: {
  data: FindingsResponse | null;
  onReload: (includeBattery: boolean) => Promise<void>;
  onActed: (f: Finding) => void;
  batteryLoading: boolean;
  batteryIncluded: boolean;
}) {
  const [kindFilter, setKindFilter] = useState('all');

  if (!data) {
    return <div className="py-20 text-center text-zinc-500 text-sm">Loading findings…</div>;
  }

  const { findings, summary } = data;
  const critical = summary.by_severity.critical || 0;
  const warning = summary.by_severity.warning || 0;
  const info = summary.by_severity.info || 0;

  const kinds = KIND_ORDER.filter(k => (summary.by_kind[k] || 0) > 0);
  const visible = findings.filter(f => kindFilter === 'all' || f.kind === kindFilter);

  return (
    <div>
      {/* Header: N failed checks + severity split + deep battery check */}
      <div className="flex items-end justify-between mb-6 flex-wrap gap-3">
        <div>
          <div className="flex items-baseline gap-3">
            <span
              className="text-[34px] tabular-nums text-zinc-100"
              style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144" }}
            >
              {summary.total}
            </span>
            <span className="text-[13px] text-zinc-400">failed checks</span>
          </div>
          <p className="text-[11px] text-zinc-600 mt-1 tabular-nums">
            <span style={{ color: 'var(--helicon-accent)' }}>{critical} critical</span>
            <span className="text-zinc-700"> · </span>
            <span style={{ color: 'var(--helicon-stale)' }}>{warning} warning</span>
            {info > 0 && <span className="text-zinc-600"> · {info} info</span>}
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={() => onReload(true)}
            disabled={batteryLoading}
            className="text-[12px] px-3 py-1.5 rounded-lg border transition-all active:scale-95 disabled:opacity-40 shadow-sm bg-white"
            style={{ borderColor: 'rgba(194,94,58,0.3)', color: 'var(--helicon-accent)' }}
          >
            {batteryLoading ? 'Running…' : batteryIncluded ? 'Re-run deep battery check' : 'Run deep battery check'}
          </button>
          {batteryLoading && (
            <span className="text-[11px] text-zinc-600 animate-pulse-subtle">
              Running the context-quality battery — ~10s
            </span>
          )}
        </div>
      </div>

      {/* Kind filter chips — the old rules/projects/content confusion, resolved into clean kinds */}
      <div className="flex items-center gap-1.5 mb-4 flex-wrap">
        <button
          onClick={() => setKindFilter('all')}
          className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
            kindFilter === 'all' ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
          }`}
        >
          All<span className="ml-1 text-zinc-700 tabular-nums">{summary.total}</span>
        </button>
        {kinds.map(k => (
          <button
            key={k}
            onClick={() => setKindFilter(k)}
            title={KIND_HINT[k]}
            className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
              kindFilter === k ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
            }`}
          >
            {KIND_LABEL[k]}<span className="ml-1 text-zinc-700 tabular-nums">{summary.by_kind[k]}</span>
          </button>
        ))}
        {!batteryIncluded && !batteryLoading && (
          <span className="text-[10px] text-zinc-700 ml-auto">battery findings appear after a deep check</span>
        )}
      </div>

      {/* Finding rows */}
      {visible.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-zinc-600 text-[13px]">Nothing failing here. Memory is clean.</p>
        </div>
      ) : (
        <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/30 bg-white shadow-sm">
          {visible.slice(0, 50).map(f => (
            <FindingRow key={f.id} f={f} onGone={() => onActed(f)} />
          ))}
        </div>
      )}

      {visible.length > 50 && (
        <p className="text-[11px] text-zinc-700 mt-3 text-center">Showing 50 of {visible.length}</p>
      )}
    </div>
  );
}
