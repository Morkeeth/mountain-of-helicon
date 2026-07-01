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
        {(['all', 'temporal', 'factual', 'decay', 'logical'] as const).map(f => {
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
          <Badge variant="outline" className="text-[10px] border-red-200 text-red-600 bg-red-50 px-1.5 py-0">
            {bySeverity.critical} critical
          </Badge>
          <Badge variant="outline" className="text-[10px] border-amber-200 text-amber-700 bg-amber-50 px-1.5 py-0">
            {bySeverity.warning} warning
          </Badge>
        </div>
      </div>

      {/* Finding rows */}
      <div className="border border-zinc-800/60 rounded-lg overflow-hidden divide-y divide-zinc-800/30 bg-white shadow-sm">
        {visible.slice(0, 25).map(f => {
          const { label, variant } = actionLabel(f);
          const btnColors = variant === 'critical'
            ? 'border-red-800/30 text-red-400/70 hover:bg-red-500/5'
            : variant === 'warning'
              ? 'border-amber-200 text-amber-700 hover:bg-amber-50'
              : 'border-zinc-800/50 text-zinc-500 hover:bg-zinc-800/30';

          return (
            <div
              key={f.id}
              className="flex items-center gap-3 py-2.5 px-4 hover:bg-zinc-800/10 transition-colors animate-fade-in"
            >
              <div className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                f.severity === 'critical' ? 'bg-red-500' : f.severity === 'warning' ? 'bg-amber-500' : 'bg-zinc-500'
              }`} />

              <div className="flex-1 min-w-0">
                <p className="text-[12px] text-zinc-300 truncate leading-snug">{shortSummary(f)}</p>
                <p className="text-[11px] text-zinc-600 leading-snug">{issueDescription(f)}</p>
              </div>

              <div className="flex gap-1 shrink-0">
                <button
                  onClick={() => handleAct(f.id, 'acted')}
                  disabled={acting === f.id}
                  className={`text-[11px] px-2.5 py-1 rounded-md border transition-all active:scale-95 disabled:opacity-30 ${btnColors}`}
                >
                  {acting === f.id ? '...' : label}
                </button>
                <button
                  onClick={() => handleDismiss(f.id)}
                  className="text-[11px] px-2 py-1 rounded-md text-zinc-700 hover:text-zinc-400 hover:bg-zinc-800/30 transition-colors"
                >
                  Skip
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {visible.length > 25 && (
        <p className="text-[11px] text-zinc-700 mt-3 text-center">
          Showing 25 of {visible.length}
        </p>
      )}
    </div>
  );
}
