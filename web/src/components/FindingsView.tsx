import { useState } from 'react';
import { api } from '../api';
import type { Finding, FindingsResponse } from '../api';
import { PrecedentReason } from './PrecedentReason';

/* FINDINGS, the heart of the dashboard. One list of everything that failed
   a check, unified across audit / skills / battery. The WHY sentence leads;
   the title is context. Every row carries its fix. Real data only. */

// Three story lanes a human can hold in their head, not nine taxonomy classes.
const GROUPS: { key: string; label: string; kinds: string[]; hint: string }[] = [
  { key: 'drift', label: 'Drift', kinds: ['factual', 'supersession'],
    hint: 'two sources disagree, or a renamed thing is still called its old name' },
  { key: 'stale', label: 'Stale', kinds: ['temporal', 'decay', 'battery', 'logical', 'routine', 'output', 'context', 'nightly'],
    hint: 'aged past its truth, memory past its half-life, dead paths, silent routines' },
  { key: 'smartness', label: 'Smartness', kinds: ['regret', 'agent-flag', 'skill'],
    hint: 'not an error, a memory worth restoring, or a skill worth sharpening' },
];

function HowItWorks() {
  const [hidden, setHidden] = useState(localStorage.getItem('hm-guide') === '1');
  if (hidden) return null;
  return (
    <div className="rounded-xl border border-zinc-300 bg-white px-5 py-4 mb-5 shadow-sm">
      <div className="flex items-baseline justify-between">
        <b className="text-[13px] text-zinc-800">How Mount Helicon works</b>
        <button className="text-[11px] text-zinc-500 hover:text-zinc-800"
          onClick={() => { localStorage.setItem('hm-guide', '1'); setHidden(true); }}>got it, hide</button>
      </div>
      <ol className="mt-2 text-[12.5px] leading-relaxed text-zinc-600 list-decimal ml-4 space-y-0.5">
        <li><b className="text-zinc-800">It reads your memory</b>, transcripts, vault, rules files, git, read-only, into its own store.</li>
        <li><b className="text-zinc-800">Checks run on a timer</b>, twelve documented failure classes (contradictions, staleness, dead names…). No LLM needed for the core.</li>
        <li><b className="text-zinc-800">Everything below failed a check</b>, each row carries its evidence. Nothing here is a suggestion; it is a receipt.</li>
        <li><b className="text-zinc-800">You rule, once</b>, confirm it's still true, correct it with the truth, or retire it. Rulings stick: the same rot re-alarms if it returns. Every decision is reversible.</li>
      </ol>
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  factual: 'Drift',
  supersession: 'Dead name',
  regret: 'Worth restoring',
  'agent-flag': 'Flagged in use',
  temporal: 'Stale',
  decay: 'Faded',
  logical: 'Stale pattern',
  skill: 'Skill',
  battery: 'Broken context',
};

function sevColor(sev: string): string {
  if (sev === 'critical' || sev === 'high') return 'var(--helicon-accent)';
  if (sev === 'warning' || sev === 'medium') return 'var(--helicon-stale)';
  return '#a1a1aa';
}

// Copyable CLI one-liner chip, the fix for skill/reconcile findings.
function ActionButton({ label, tone, disabled, onClick }: {
  label: string;
  tone: 'kill' | 'keep' | 'muted';
  disabled?: boolean;
  onClick: () => void;
}) {
  const isKeep = tone === 'keep';
  const styles =
    tone === 'kill'
      ? { borderColor: 'var(--helicon-line-2)', color: 'var(--helicon-ink)' }
      : isKeep
        ? { border: 'none', color: '#F4EFE7',
            backgroundImage: 'linear-gradient(180deg, #35526d 0%, #223A4E 100%)' }
        : { borderColor: 'transparent', color: 'var(--helicon-muted)' };
  return (
    <button
      onClick={e => { e.stopPropagation(); onClick(); }}
      disabled={disabled}
      /* 11px/py-1 is a ~24px target: right for a cursor, unusable for a thumb.
         Tall on a phone, unchanged for the dense desktop row. */
      className={`text-[11px] px-3 md:px-2.5 py-1 rounded-md border transition-all active:scale-95 disabled:opacity-30 shadow-sm min-h-[44px] md:min-h-0 ${isKeep ? '' : 'bg-white'}`}
      style={styles}
    >
      {label}
    </button>
  );
}

function FindingRow({ f, onGone }: { f: Finding; onGone: () => void }) {
  const [expanded, setExpanded] = useState(false);
  const [acting, setActing] = useState(false);
  // a dismissal opens the reason step: without one it compiles to no law
  const [reasoning, setReasoning] = useState(false);

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
    if (f.suggested_action === 'resolve_identity' && auditId !== null) {
      return <IdentityResolve auditId={auditId} onGone={onGone} />;
    }
    if (f.suggested_action === 'resolve_relation' && auditId !== null) {
      return <RelationResolve auditId={auditId} onGone={onGone} />;
    }
    if ((f.suggested_action === 'fix_skill' || f.suggested_action === 'reconcile') && auditId !== null) {
      // Ruled like every other finding — the verdict compiles into GOLDEN_RULES
      // and never alarms again. The old copy-this-shell-command chip is gone: a
      // review surface tells the operator to decide, not to run maintenance.
      return (
        <>
          <ActionButton label="Rule it" tone="keep" disabled={acting} onClick={() => { setReasoning(true); setExpanded(true); }} />
          <ActionButton label="Later" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />
        </>
      );
    }
    if (f.suggested_action === 'kill_stale' && auditId !== null) {
      return (
        <>
          <ActionButton label={acting ? '...' : 'Retire'} tone="kill" disabled={acting} onClick={() => confirmAudit('acted')} />
          {/* Keep = "not rot", the verdict that can carry a precedent */}
          <ActionButton label="Keep" tone="keep" disabled={acting} onClick={() => { setReasoning(true); setExpanded(true); }} />
        </>
      );
    }
    // review (and battery kill_stale rows, which carry a cube): confirm/retire the cube itself
    if (f.cube_id) {
      return (
        <>
          <ActionButton label={acting ? '...' : 'Confirm'} tone="keep" disabled={acting} onClick={() => review('approved')} />
          <ActionButton label={acting ? '...' : 'Retire'} tone="kill" disabled={acting} onClick={() => review('killed')} />
          {auditId !== null && <ActionButton label="Later" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />}
        </>
      );
    }
    if (auditId !== null) {
      return <ActionButton label="Later" tone="muted" disabled={acting} onClick={() => confirmAudit('dismissed')} />;
    }
    return null;
  })();

  return (
    <div className="animate-fade-in">
      {/* On a phone the actions drop BELOW the finding. Held beside it, a
          shrink-0 button cluster (a mono CLI chip is ~200px) left the text
          column about 40px wide and wrapped the finding one word per line,
          unreadable, on the surface whose whole job is to be read before a
          ruling. Unchanged from md up. */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => setExpanded(x => !x)}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setExpanded(x => !x); } }}
        className="flex flex-col md:flex-row md:items-start gap-2 md:gap-3 py-3 px-4 hover:bg-zinc-800/10 transition-colors cursor-pointer"
      >
        <div className="flex items-start gap-3 flex-1 min-w-0">
          <span
            className="w-1.5 h-1.5 rounded-full shrink-0 mt-[7px]"
            style={{ background: sevColor(f.severity) }}
          />

          <div className="flex-1 min-w-0">
            {/* The WHY sentence is the finding, it leads. The title (which doc /
                cube) is the differentiator when the why repeats across findings,
                so keep it legible and un-truncated rather than a faint gray line. */}
            <p className="text-[13px] text-zinc-200 leading-snug break-words">{f.why}</p>
            <p className="text-[12px] text-zinc-400 leading-snug mt-1 break-words">
              {f.title}
              <span className="text-zinc-600"> · {KIND_LABEL[f.kind] || f.kind}</span>
            </p>
          </div>

          <svg
            width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
            className={`text-zinc-600 shrink-0 mt-1.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
          >
            <path d="M6 9l6 6 6-6" />
          </svg>
        </div>

        <div className="flex gap-1.5 md:shrink-0 items-center flex-wrap pl-[18px] md:pl-0" onClick={e => e.stopPropagation()}>
          {actions}
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-4 pl-4 md:pl-9 animate-fade-in">
          {f.evidence_preview ? (
            <pre className="text-[11px] text-zinc-400 bg-zinc-900/50 p-3 rounded-lg whitespace-pre-wrap leading-relaxed border border-zinc-800/40 max-h-44 overflow-auto">
              {f.evidence_preview}
            </pre>
          ) : (
            <p className="text-[11px] text-zinc-600">No evidence preview for this finding.</p>
          )}
          <p className="text-[10px] text-zinc-700 mt-2 break-words">
            {f.source} · {f.source_ref}
          </p>
          {reasoning && auditId !== null && (
            <div className="mt-4 pt-4 border-t" style={{ borderColor: 'var(--helicon-line)' }}>
              <PrecedentReason
                auditId={auditId}
                findingWhy={f.why}
                compact
                onCancel={() => setReasoning(false)}
                onFiled={() => onGone()}
              />
            </div>
          )}
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
  // Default to the decision lane, the handful that need a human ruling, not
  // the whole pile. Oscar's Jul-3 verdict: CI shows failing checks, not every line.
  const [kindFilter, setKindFilter] = useState('needs');

  if (!data) {
    return <div className="py-20 text-center text-zinc-500 text-sm">Loading findings…</div>;
  }

  const { findings, summary } = data;
  const critical = summary.by_severity.critical || 0;
  const warning = summary.by_severity.warning || 0;
  const info = summary.by_severity.info || 0;

  const groupCount = (g: { kinds: string[] }) => g.kinds.reduce((n, k) => n + (summary.by_kind[k] || 0), 0);
  const groups = GROUPS.filter(g => groupCount(g) > 0);
  const activeKinds = GROUPS.find(g => g.key === kindFilter)?.kinds;
  const visible = findings.filter(f => {
    if (kindFilter === 'needs') return f.lane === 'decision';
    if (kindFilter === 'aging') return f.lane === 'ambient';
    if (kindFilter === 'all') return true;
    return activeKinds ? activeKinds.includes(f.kind) : f.kind === kindFilter;
  });

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
              {summary.needs_you}
            </span>
            <span className="text-[13px] text-zinc-400">need your ruling</span>
          </div>
          <p className="text-[11px] text-zinc-600 mt-1 tabular-nums">
            <span style={{ color: 'var(--helicon-accent)' }}>{critical} critical</span>
            <span className="text-zinc-700"> · </span>
            <span style={{ color: 'var(--helicon-stale)' }}>{warning} warning</span>
            {info > 0 && <span className="text-zinc-600"> · {info} info</span>}
            <span className="text-zinc-700"> · </span>
            <span className="text-zinc-600">{summary.ambient} aging, auto-managed</span>
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <button
            onClick={() => onReload(true)}
            disabled={batteryLoading}
            title="LLM-judged tests on whether the context your agent retrieves is any good — relevance, freshness, grounding. The slow, deep pass."
            className="text-[12px] px-3 py-1.5 rounded-lg border transition-all active:scale-95 disabled:opacity-40 shadow-sm bg-white"
            style={{ borderColor: 'var(--helicon-line-2)', color: 'var(--helicon-ink)' }}
          >
            {batteryLoading ? 'Running…' : batteryIncluded ? 'Re-run deep quality check' : 'Run deep quality check'}
          </button>
          {batteryLoading && (
            <span className="text-[11px] text-zinc-600 animate-pulse-subtle">
              Checking retrieval quality, ~10s
            </span>
          )}
        </div>
      </div>

      <HowItWorks />
      {/* Kind filter chips, the old rules/projects/content confusion, resolved into clean kinds */}
      <div className="flex items-center gap-1.5 mb-4 flex-wrap">
        <button
          onClick={() => setKindFilter('needs')}
          title="Findings only a human can rule on, contradictions, wrong evictions, skills"
          className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
            kindFilter === 'needs' ? 'bg-zinc-800/60 text-zinc-200' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
          }`}
        >
          Needs you<span className="ml-1 text-zinc-700 tabular-nums">{summary.needs_you}</span>
        </button>
        <button
          onClick={() => setKindFilter('aging')}
          title="Age & mechanics, stale notes, decayed commits, moved paths. Auto-manageable in bulk."
          className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
            kindFilter === 'aging' ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
          }`}
        >
          Aging<span className="ml-1 text-zinc-700 tabular-nums">{summary.ambient}</span>
        </button>
        <span className="text-zinc-800">·</span>
        <button
          onClick={() => setKindFilter('all')}
          className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
            kindFilter === 'all' ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
          }`}
        >
          All<span className="ml-1 text-zinc-700 tabular-nums">{summary.total}</span>
        </button>
        {groups.map(g => (
          <button
            key={g.key}
            onClick={() => setKindFilter(g.key)}
            title={g.hint}
            className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
              kindFilter === g.key ? 'bg-zinc-800/60 text-zinc-300' : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
            }`}
          >
            {g.label}<span className="ml-1 text-zinc-700 tabular-nums">{groupCount(g)}</span>
          </button>
        ))}
        {!batteryIncluded && !batteryLoading && (
          <span className="text-[10px] text-zinc-700 ml-auto">quality findings appear after a deep check</span>
        )}
      </div>

      {/* Plain-English description of whatever lane is selected, so a first-time
          reader always knows what this list is, without a tooltip. */}
      {(() => {
        const desc = kindFilter === 'needs'
          ? 'Decisions only you can make, contradictions, dead names, and memory you retired that retrieval keeps pulling back.'
          : kindFilter === 'aging'
            ? 'Age and mechanics, notes past their freshness window, decayed commits, moved paths. Safe to accept or bulk-manage; nothing here is urgent.'
            : kindFilter === 'all'
              ? 'Everything flagged, the decisions that need you and the ambient age findings together.'
              : (GROUPS.find(g => g.key === kindFilter)?.hint || '');
        return desc ? <p className="text-[12px] mb-4" style={{ color: 'var(--helicon-muted)' }}>{desc}</p> : null;
      })()}

      {/* Finding rows, grouped by severity so the hierarchy is legible and each tier self-explains */}
      {visible.length === 0 ? (
        <div className="py-16 text-center">
          <p className="text-zinc-600 text-[13px]">Nothing failing here. Memory is clean.</p>
        </div>
      ) : (() => {
        const TIERS = [
          { sev: 'critical', t: 'Critical', d: 'Rule on these first, the record is actively wrong.' },
          { sev: 'warning', t: 'Warnings', d: 'Worth a ruling when you have a moment.' },
          { sev: 'info', t: 'Aging \u00b7 auto-managed', d: 'Age and mechanics, safe to leave; open if curious.' },
        ];
        let shown = 0;
        return TIERS.map(tier => {
          const items = visible.filter(x => (x.severity || 'info') === tier.sev);
          if (items.length === 0 || shown >= 50) return null;
          const slice = items.slice(0, 50 - shown);
          shown += slice.length;
          return (
            <div key={tier.sev} className="mb-6">
              <div className="flex items-baseline gap-2 mb-2">
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: sevColor(tier.sev) }} />
                <span className="text-[13px] font-medium" style={{ color: 'var(--helicon-ink)' }}>{tier.t}</span>
                <span className="text-[12px] tabular-nums" style={{ color: 'var(--helicon-faint)' }}>{items.length}</span>
                <span className="text-[11px] ml-1.5" style={{ color: 'var(--helicon-muted)' }}>{tier.d}</span>
              </div>
              <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/30 bg-white shadow-sm">
                {slice.map(x => <FindingRow key={x.id} f={x} onGone={() => onActed(x)} />)}
              </div>
            </div>
          );
        });
      })()}

      {visible.length > 50 && (
        <p className="text-[11px] text-zinc-700 mt-3 text-center">Showing the first 50 of {visible.length}</p>
      )}
    </div>
  );
}


function IdentityResolve({ auditId, onGone }: { auditId: number; onGone: () => void }) {
  const [canon, setCanon] = useState('');
  const [busy, setBusy] = useState(false);
  const resolve = async () => {
    if (!canon.trim()) return;
    setBusy(true);
    try { await api.resolveIdentity(auditId, canon.trim()); } finally { setBusy(false); }
    onGone();
  };
  const dismiss = async () => {
    setBusy(true);
    try { await api.confirmAudit(auditId, 'dismissed'); } finally { setBusy(false); }
    onGone();
  };
  return (
    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
      <input value={canon} onChange={e => setCanon(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') resolve(); }}
        placeholder="canonical definition…"
        className="text-[11px] px-2 py-1 rounded border w-44 outline-none"
        style={{ background: 'var(--helicon-panel-2)', color: 'var(--helicon-ink)', borderColor: 'var(--helicon-line)' }} />
      <ActionButton label="Set canonical" tone="keep" disabled={busy || !canon.trim()} onClick={resolve} />
      <ActionButton label="Not a fork" tone="muted" disabled={busy} onClick={dismiss} />
    </div>
  );
}


function RelationResolve({ auditId, onGone }: { auditId: number; onGone: () => void }) {
  const [busy, setBusy] = useState(false);
  const rule = async (verdict: string) => {
    setBusy(true);
    try { await api.resolveRelation(auditId, verdict); } finally { setBusy(false); }
    onGone();
  };
  return (
    <div className="flex items-center gap-1.5" onClick={e => e.stopPropagation()}>
      <ActionButton label="Confirm phantom" tone="keep" disabled={busy} onClick={() => rule('phantom')} />
      <ActionButton label="It's real" tone="muted" disabled={busy} onClick={() => rule('real')} />
    </div>
  );
}
