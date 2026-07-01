import { useState, useEffect } from 'react';
import { api } from '../api';
import type { Score, AuditFinding, Connector, Consolidation } from '../api';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

interface DashboardProps {
  score: Score | null;
  findings: AuditFinding[];
  connectors: Connector[];
  triageCount: number;
  onNavigate: (tab: string) => void;
}

interface Tiers {
  hot: number;
  warm: number;
  cold: number;
  consolidations: number;
  total_merged: number;
}

export function Dashboard({ score, findings, connectors, triageCount, onNavigate }: DashboardProps) {
  const [tiers, setTiers] = useState<Tiers | null>(null);
  const [consolidations, setConsolidations] = useState<Consolidation[]>([]);
  const [running, setRunning] = useState(false);
  const [acting, setActing] = useState<number | null>(null);
  const [killedIds, setKilledIds] = useState<Set<number>>(new Set());

  useEffect(() => {
    fetch('/api/consolidations/tiers').then(r => r.json()).then(setTiers).catch(() => {});
    api.getConsolidations().then(r => setConsolidations(r.consolidations || [])).catch(() => {});
  }, []);

  if (!score) return null;

  const deadFindings = findings
    .filter(f => f.audit_type === 'decay' && !killedIds.has(f.id))
    .slice(0, 4);

  const handleKill = async (finding: AuditFinding) => {
    setActing(finding.id);
    await api.confirmAudit(finding.id, 'acted');
    setKilledIds(prev => new Set(prev).add(finding.id));
    setActing(null);
  };

  const runSleepCycle = async () => {
    setRunning(true);
    try {
      const result = await api.runConsolidation(true, 10);
      const newCons = result.results?.map((r: any) => ({
        id: r.id ?? '',
        title: r.title ?? '',
        summary: r.summary ?? '',
        cube_ids: [],
        cube_count: r.cube_count ?? 0,
        created_at: new Date().toISOString(),
        confidence: r.confidence ?? 0.5,
        topic: '',
      })) || [];
      setConsolidations(prev => [...newCons, ...prev]);
      fetch('/api/consolidations/tiers').then(r => r.json()).then(setTiers);
    } catch {
    }
    setRunning(false);
  };

  const total = tiers ? tiers.hot + tiers.warm + tiers.cold : score.total;
  const hotPct = tiers ? Math.round((tiers.hot / Math.max(total, 1)) * 100) : 0;
  const warmPct = tiers ? Math.round((tiers.warm / Math.max(total, 1)) * 100) : 0;
  const coldPct = tiers ? Math.round((tiers.cold / Math.max(total, 1)) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Memory tiers + sleep cycle */}
      <div className="flex items-start justify-between">
        <div className="flex-1">
          {tiers && (
            <div className="flex items-center gap-6">
              <TierPill label="Hot" count={tiers.hot} pct={hotPct} color="text-red-400/80" bg="bg-red-400/10" desc="< 7 days" />
              <TierPill label="Warm" count={tiers.warm} pct={warmPct} color="text-amber-400/80" bg="bg-amber-400/10" desc="7-30 days" />
              <TierPill label="Cold" count={tiers.cold} pct={coldPct} color="text-blue-400/60" bg="bg-blue-400/10" desc="> 30 days" />
              <div className="h-8 w-px bg-zinc-800/40" />
              <div className="text-center">
                <span className="text-[18px] font-light tabular-nums text-zinc-300">{tiers.consolidations}</span>
                <p className="text-[10px] text-zinc-600">consolidated</p>
              </div>
            </div>
          )}
        </div>
        <button
          onClick={runSleepCycle}
          disabled={running}
          className="text-[12px] px-4 py-2 rounded-lg border border-violet-200 text-violet-600 hover:bg-violet-50 transition-all active:scale-95 disabled:opacity-30 flex items-center gap-2 shadow-sm bg-white"
        >
          {running ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse" />
              Consolidating...
            </>
          ) : (
            'Run Sleep Cycle'
          )}
        </button>
      </div>

      {/* Tier bar visualization */}
      {tiers && total > 0 && (
        <div className="h-1.5 rounded-full bg-zinc-800/30 flex overflow-hidden">
          <div className="bg-red-400/40 transition-all" style={{ width: `${hotPct}%` }} />
          <div className="bg-amber-400/30 transition-all" style={{ width: `${warmPct}%` }} />
          <div className="bg-blue-400/20 transition-all" style={{ width: `${coldPct}%` }} />
        </div>
      )}

      {/* Consolidated knowledge */}
      {consolidations.length > 0 && (
        <Card className="bg-white border-zinc-800/60 shadow-sm">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-[13px] font-medium text-zinc-300">Consolidated knowledge</h3>
                <p className="text-[11px] text-zinc-600 mt-0.5">Synthesized from {tiers?.total_merged || 0} cubes across {consolidations.length} topics</p>
              </div>
              <button
                onClick={() => onNavigate('insights')}
                className="text-[11px] text-zinc-600 hover:text-zinc-400 transition-colors"
              >
                View all &rarr;
              </button>
            </div>
            <div className="space-y-0 divide-y divide-zinc-800/20">
              {consolidations.slice(0, 5).map(c => (
                <ConsolidationItem key={c.id} consolidation={c} />
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Dead items */}
      {deadFindings.length > 0 && (
        <Card className="bg-white border-zinc-800/60 shadow-sm">
          <CardContent className="pt-5 pb-4 px-5">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-[13px] font-medium text-zinc-300">Needs attention</h3>
                <p className="text-[11px] text-zinc-600 mt-0.5">Low confidence items and stale references</p>
              </div>
              <Badge variant="outline" className="text-[10px] border-zinc-700/40 text-zinc-600">
                {findings.length} issues
              </Badge>
            </div>
            <div className="space-y-0 divide-y divide-zinc-800/20">
              {deadFindings.map(f => {
                const age = f.details?.age_days ? `${Math.round(f.details.age_days)}d old` : '';
                const conf = f.details?.confidence != null ? `${(f.details.confidence * 100).toFixed(0)}%` : '0%';
                return (
                  <div key={f.id} className="flex items-center gap-3 py-2.5 group">
                    <div className="flex-1 min-w-0">
                      <p className="text-[12px] text-zinc-400 truncate">{extractTitle(f.finding)}</p>
                      <p className="text-[11px] text-zinc-700">{conf} confidence, {age}</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => handleKill(f)}
                        disabled={acting === f.id}
                        className="text-[11px] px-2.5 py-1 rounded-md border border-red-800/30 text-red-400/70 hover:bg-red-500/5 transition-all active:scale-95 disabled:opacity-30"
                      >
                        {acting === f.id ? '...' : 'Kill'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
            <button
              onClick={() => onNavigate('insights')}
              className="text-[11px] text-zinc-600 hover:text-zinc-400 mt-3 transition-colors"
            >
              View all {findings.length} findings &rarr;
            </button>
          </CardContent>
        </Card>
      )}

      {/* Status footer */}
      <div className="flex items-center justify-between text-[11px] text-zinc-700 pt-2">
        <span>{score.total.toLocaleString()} total items from {connectors.length} sources</span>
        <div className="flex items-center gap-4">
          {triageCount > 0 && (
            <span className="flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500/50" />
              {triageCount} auto-handled
            </span>
          )}
          <span className="tabular-nums">{score.score}% reviewed</span>
        </div>
      </div>
    </div>
  );
}

function TierPill({ label, count, pct, color, bg, desc }: {
  label: string; count: number; pct: number; color: string; bg: string; desc: string;
}) {
  return (
    <div className="text-center">
      <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md ${bg}`}>
        <span className={`text-[16px] font-light tabular-nums ${color}`}>{count}</span>
        <span className={`text-[10px] ${color} opacity-60`}>{pct}%</span>
      </div>
      <p className="text-[10px] text-zinc-600 mt-1">{label} ({desc})</p>
    </div>
  );
}

function ConsolidationItem({ consolidation }: { consolidation: Consolidation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="py-3">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
        <div className="flex items-center justify-between">
          <span className="text-[12px] text-zinc-300">{consolidation.title}</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-zinc-700 tabular-nums">{consolidation.cube_count} merged</span>
            <span className="text-[10px] text-zinc-800">{expanded ? '-' : '+'}</span>
          </div>
        </div>
      </button>
      {expanded && (
        <p className="text-[11px] text-zinc-500 leading-relaxed mt-2 animate-fade-in">
          {consolidation.summary}
        </p>
      )}
    </div>
  );
}

function extractTitle(finding: string): string {
  const match = finding.match(/^\[([^\]]+)\]\s*(.+?)(?:\s+has\s+decayed|\s+is\s+\d+\s+days)/);
  if (match) return `${match[1]}: ${match[2]}`;
  const quoted = finding.match(/^'([^']+)'/);
  if (quoted) return quoted[1].slice(0, 70);
  return finding.slice(0, 70);
}
