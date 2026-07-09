import { useState } from 'react';
import { api } from '../api';
import type { AuditFinding } from '../api';
import { Badge } from '@/components/ui/badge';

interface Props {
  findings: AuditFinding[];
  onRefresh: () => void;
}

function actionLabel(f: AuditFinding): { label: string; variant: 'critical' | 'warning' | 'default' } {
  if (f.audit_type === 'temporal') return { label: 'Kill stale', variant: 'critical' };
  if (f.audit_type === 'factual') return { label: 'Resolve', variant: 'critical' };
  if (f.audit_type === 'decay') return { label: 'Review', variant: 'warning' };
  if (f.audit_type === 'logical') return { label: 'Check', variant: 'default' };
  return { label: 'Review', variant: 'default' };
}

function shortSummary(f: AuditFinding): string {
  const text = f.finding;
  const match = text.match(/^'([^']+)'/);
  if (match) return match[1].slice(0, 60);
  if (text.length > 70) return text.slice(0, 67) + '...';
  return text;
}

function issueDescription(f: AuditFinding): string {
  if (f.audit_type === 'temporal') {
    const langMatch = f.finding.match(/time-relative language: (.+)$/);
    const ageMatch = f.finding.match(/(\d+) days? old/);
    if (langMatch && ageMatch) return `Says "${langMatch[1]}" but is ${ageMatch[1]} days old`;
    return 'Contains outdated time references';
  }
  if (f.audit_type === 'factual') return 'Contradicts another memory item';
  if (f.audit_type === 'decay') return 'Confidence dropped below threshold';
  if (f.audit_type === 'logical') return 'Pattern no longer supported by data';
  return f.proposed_action || 'Needs review';
}

// Names the health check the memory failed, so a Kill is never decided blind.
function failedCheck(f: AuditFinding): string {
  if (f.audit_type === 'temporal') return 'Temporal check, time-relative wording no longer matches the memory\'s age';
  if (f.audit_type === 'factual') return 'Factual check, this memory contradicts another stored memory';
  if (f.audit_type === 'decay') return 'Decay check, confidence has decayed below the keep threshold';
  if (f.audit_type === 'logical') return 'Logical check, the learned pattern is no longer supported by review data';
  return `${f.audit_type} check`;
}

export function AuditPanel({ findings, onRefresh }: Props) {
  const [acting, setActing] = useState<number | null>(null);
  const [dismissed, setDismissed] = useState<Set<number>>(new Set());
  const [filter, setFilter] = useState<string>('all');

  const handleAct = async (id: number, decision: string) => {
    setActing(id);
    await api.confirmAudit(id, decision);
    setActing(null);
    onRefresh();
  };

  const handleDismiss = (id: number) => {
    setDismissed(prev => new Set(prev).add(id));
    api.confirmAudit(id, 'dismissed');
  };

  if (findings.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-zinc-600 text-[13px]">No issues found. Memory is clean.</p>
      </div>
    );
  }

  const visible = findings
    .filter(f => !dismissed.has(f.id))
    .filter(f => filter === 'all' || f.audit_type === filter);

  const counts = {
    all: findings.length,
    temporal: findings.filter(f => f.audit_type === 'temporal').length,
    factual: findings.filter(f => f.audit_type === 'factual').length,
    supersession: findings.filter(f => f.audit_type === 'supersession').length,
    decay: findings.filter(f => f.audit_type === 'decay').length,
    logical: findings.filter(f => f.audit_type === 'logical').length,
  };

  const bySeverity = {
    critical: findings.filter(f => f.severity === 'critical').length,
    warning: findings.filter(f => f.severity === 'warning').length,
  };

  return (
    <div>
      {/* Filter row */}
      <div className="flex items-center gap-1.5 mb-4 flex-wrap">
        {(['all', 'factual', 'supersession', 'temporal', 'decay', 'logical'] as const).map(f => {
          const count = counts[f];
          if (f !== 'all' && count === 0) return null;
          return (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`text-[11px] px-2.5 py-1 rounded-md transition-colors ${
                filter === f
                  ? 'bg-zinc-800/60 text-zinc-300'
                  : 'text-zinc-600 hover:text-zinc-400 hover:bg-zinc-800/20'
              }`}
            >
              {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
              <span className="ml-1 text-zinc-700 tabular-nums">{count}</span>
            </button>
          );
        })}
        <div className="ml-auto flex items-center gap-2">
          <Badge variant="outline" className="text-[10px] border-[rgba(34,58,78,0.30)] text-[#223A4E] bg-[rgba(34,58,78,0.10)] px-1.5 py-0">
            {bySeverity.critical} critical
          </Badge>
          <Badge variant="outline" className="text-[10px] border-amber-200 text-amber-700 bg-amber-50 px-1.5 py-0">
            {bySeverity.warning} warning
          </Badge>
        </div>
      </div>

      {/* Finding rows */}
      <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/30 bg-white shadow-sm">
        {visible.slice(0, 25).map(f => (
          <FindingRow
            key={f.id}
            f={f}
            acting={acting === f.id}
            onAct={decision => handleAct(f.id, decision)}
            onDismiss={() => handleDismiss(f.id)}
          />
        ))}
      </div>

      {visible.length > 25 && (
        <p className="text-[11px] text-zinc-700 mt-3 text-center">
          Showing 25 of {visible.length}
        </p>
      )}
    </div>
  );
}

// Expandable finding row: click to see the memory's content and WHY it was
// flagged before deciding Kill/Skip.
function FindingRow({ f, acting, onAct, onDismiss }: {
  f: AuditFinding;
  acting: boolean;
  onAct: (decision: string) => void;
  onDismiss: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [preview, setPreview] = useState<string | null>(null);
  const [previewLoaded, setPreviewLoaded] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);

  const { label, variant } = actionLabel(f);
  const btnColors = variant === 'critical'
    ? 'border-[rgba(34,58,78,0.30)] text-[#223A4E]/70 hover:bg-[rgba(34,58,78,0.05)]'
    : variant === 'warning'
      ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
      : 'border-zinc-800/50 text-zinc-500 hover:bg-zinc-800/30';

  const toggle = async () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !previewLoaded && !previewLoading && f.target_id) {
      setPreviewLoading(true);
      try {
        const res = await fetch(`/api/cubes/${f.target_id}`);
        if (res.ok) {
          const cube = await res.json();
          if (typeof cube?.content === 'string') setPreview(cube.content);
        }
      } catch { /* memory may not exist for this finding */ }
      setPreviewLoaded(true);
      setPreviewLoading(false);
    }
  };

  return (
    <div className="animate-fade-in">
      <div
        role="button"
        tabIndex={0}
        onClick={toggle}
        onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(); } }}
        className="flex items-center gap-3 py-2.5 px-4 hover:bg-zinc-800/10 transition-colors cursor-pointer"
      >
        <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
          f.severity === 'critical' ? 'bg-[#223A4E]' : f.severity === 'warning' ? 'bg-amber-500' : 'bg-zinc-500'
        }`} />

        <div className="flex-1 min-w-0">
          <p className="text-[12px] text-zinc-300 truncate leading-snug">{shortSummary(f)}</p>
          <p className="text-[11px] text-zinc-600 leading-snug">{issueDescription(f)}</p>
        </div>

        <svg
          width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
          className={`text-zinc-600 shrink-0 transition-transform ${expanded ? 'rotate-180' : ''}`}
        >
          <path d="M6 9l6 6 6-6" />
        </svg>

        <div className="flex gap-1 shrink-0" onClick={e => e.stopPropagation()}>
          <button
            onClick={() => onAct('acted')}
            disabled={acting}
            className={`text-[11px] px-2.5 py-1 rounded-md border transition-all active:scale-95 disabled:opacity-30 ${btnColors}`}
          >
            {acting ? '...' : label}
          </button>
          <button
            onClick={onDismiss}
            className="text-[11px] px-2 py-1 rounded-md text-zinc-700 hover:text-zinc-400 hover:bg-zinc-800/30 transition-colors"
          >
            Skip
          </button>
        </div>
      </div>

      {expanded && (
        <div className="px-4 pb-3 pl-9 animate-fade-in">
          <p className="text-[11px] text-zinc-500 mb-2">
            <span className="text-zinc-400 font-medium">Why: </span>{failedCheck(f)}.
            {f.finding && <span className="text-zinc-600"> Evidence: {f.finding}</span>}
          </p>
          {previewLoading && (
            <p className="text-[11px] text-zinc-600">Loading memory content...</p>
          )}
          {!previewLoading && preview !== null && (
            <pre className="text-[11px] text-zinc-400 bg-zinc-900/50 p-3 rounded-lg whitespace-pre-wrap leading-relaxed border border-zinc-800/40 max-h-40 overflow-auto">
              {preview.slice(0, 300)}
              {preview.length > 300 && '...'}
            </pre>
          )}
          {!previewLoading && previewLoaded && preview === null && (
            <p className="text-[11px] text-zinc-600">No memory content available for this finding.</p>
          )}
        </div>
      )}
    </div>
  );
}
