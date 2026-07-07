import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from './api';
import type { Score, Connector, ProjectRollup, Consolidation, Finding, FindingsResponse } from './api';
import { Graph3D } from './components/Graph3D';
import { EvalView } from './components/EvalView';
import { ConnectorStatus } from './components/ConnectorStatus';
import HeliconMountain from './components/HeliconMountain';
import SkillsAudit from './components/SkillsAudit';
import FindingsView from './components/FindingsView';
import LogView from './components/LogView';
import GoldView from './components/GoldView';
import ConflictMap from './components/ConflictMap';
import Focus from './components/Focus';

/* Findings-first IA (Jul 3): HEALTH · FINDINGS · LOG primary,
   Graph · Projects secondary. Review and Insights are gone — findings
   carry their own actions, the log carries the receipts. */

type Tab = 'focus' | 'health' | 'findings' | 'gold' | 'log' | 'graph' | 'projects' | 'routines' | 'evals';

// Focus leads — your next moves from the state of your memory. Then your memory
// itself, what needs ruling, what to feed the agent. Stack/evals/log secondary.
const PRIMARY_TABS: { key: Tab; label: string }[] = [
  { key: 'focus', label: 'Focus' },
  { key: 'health', label: 'Context' },
  { key: 'findings', label: 'Reviews' },
  { key: 'gold', label: 'Output' },
];

const SECONDARY_TABS: { key: Tab; label: string }[] = [
  { key: 'routines', label: 'Routines & Skills' },
  { key: 'evals', label: 'Evals' },
  { key: 'log', label: 'Log' },
];

const ALL_TABS: Tab[] = [...PRIMARY_TABS, ...SECONDARY_TABS].map(t => t.key);

function App() {
  // deep-linkable tabs: /#health jumps straight to a surface (demo + docs)
  const initialTab = (): Tab => {
    const h = window.location.hash.replace('#', '') as Tab;
    return ALL_TABS.includes(h) ? h : 'focus';
  };
  const [tab, setTab] = useState<Tab>(initialTab);
  const [score, setScore] = useState<Score | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [triageCount, setTriageCount] = useState(0);
  const [loading, setLoading] = useState(true);

  // Findings (the heart) — owned here so the header attention bar shares it
  const [findingsData, setFindingsData] = useState<FindingsResponse | null>(null);
  const [batteryIncluded, setBatteryIncluded] = useState(false);
  const [batteryLoading, setBatteryLoading] = useState(false);

  // Project-centric state (secondary surface, unchanged)
  const [projects, setProjects] = useState<ProjectRollup[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [projectConsolidations, setProjectConsolidations] = useState<Consolidation[]>([]);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    const [s, c, t] = await Promise.all([
      api.getScore(),
      api.getConnectors(),
      api.getTriageStats().catch(() => ({ total_triaged: 0 })),
    ]);
    setScore(s);
    setConnectors(c.connectors);
    setTriageCount(t.total_triaged);
  }, []);

  const loadFindings = useCallback(async (includeBattery: boolean) => {
    if (includeBattery) setBatteryLoading(true);
    try {
      const res = await api.getFindings({ limit: 500, include: includeBattery ? 'battery' : '' });
      setFindingsData(res);
      setBatteryIncluded(includeBattery);
    } finally {
      if (includeBattery) setBatteryLoading(false);
    }
  }, []);

  // Optimistic removal after Kill/Skip/Keep so acting on a row never re-runs
  // the expensive battery; counts stay honest by decrementing the summary.
  const handleFindingActed = useCallback((f: Finding) => {
    setFindingsData(prev => {
      if (!prev) return prev;
      const findings = prev.findings.filter(x => x.id !== f.id);
      const by_kind = { ...prev.summary.by_kind, [f.kind]: Math.max(0, (prev.summary.by_kind[f.kind] || 1) - 1) };
      const by_severity = { ...prev.summary.by_severity, [f.severity]: Math.max(0, (prev.summary.by_severity[f.severity] || 1) - 1) };
      return { findings, summary: { ...prev.summary, total: Math.max(0, prev.summary.total - 1), by_kind, by_severity } };
    });
    refresh(); // review decisions move the Helicon Score
  }, [refresh]);

  const loadProjects = useCallback(async () => {
    const res = await api.getProjects().catch(() => ({ projects: [] }));
    setProjects(res.projects);
  }, []);

  const loadConsolidations = useCallback(async () => {
    const res = await api.getConsolidations().catch(() => ({ consolidations: [] }));
    setProjectConsolidations(res.consolidations);
  }, []);

  useEffect(() => {
    Promise.all([refresh(), loadFindings(false), loadProjects(), loadConsolidations()])
      .then(() => setLoading(false));
  }, [refresh, loadFindings, loadProjects, loadConsolidations]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const idx = parseInt(e.key) - 1;
      if (idx >= 0 && idx < ALL_TABS.length) setTab(ALL_TABS[idx]);
      if (tab === 'projects' && e.key === 'Escape') setSelectedProject(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [tab]);

  const criticalCount = findingsData?.summary.by_severity.critical || 0;
  const warningCount = findingsData?.summary.by_severity.warning || 0;

  // Get consolidations for a project
  const getProjectConsolidations = (projectName: string) => {
    const normalized = projectName.toLowerCase();
    return projectConsolidations.filter(c =>
      c.title.toLowerCase().includes(normalized) ||
      c.topic.toLowerCase().includes(normalized)
    );
  };

  // Build inject context for a project
  const buildInjectContext = (project: ProjectRollup) => {
    const cons = getProjectConsolidations(project.name);
    let ctx = `# ${project.name} - Consolidated Context\n\n`;
    ctx += `## Overview\n`;
    ctx += `- ${project.cube_count} memory items from ${project.sources.join(', ')}\n`;
    ctx += `- Ship rate: ${(project.ship_rate * 100).toFixed(0)}% (${project.shipped} shipped, ${project.killed} killed)\n`;
    ctx += `- Avg confidence: ${(project.avg_confidence * 100).toFixed(0)}%\n`;
    if (project.days_since_output !== null) {
      ctx += `- Last output: ${project.days_since_output} days ago\n`;
    }
    ctx += `\n`;

    if (cons.length > 0) {
      ctx += `## Consolidated Knowledge\n\n`;
      cons.forEach(c => {
        ctx += `### ${c.title}\n`;
        ctx += `${c.summary}\n`;
        ctx += `(${c.cube_count} items merged, ${(c.confidence * 100).toFixed(0)}% confidence)\n\n`;
      });
    }

    return ctx;
  };

  const handleInjectContext = (project: ProjectRollup) => {
    const ctx = buildInjectContext(project);
    navigator.clipboard.writeText(ctx).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--bg)' }}>
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-1 rounded-full qwen-gradient-bg opacity-60 animate-pulse-subtle" />
          <span className="text-zinc-500 text-sm tracking-wide">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg)' }}>
      <header className="px-8 pt-6 pb-0" style={{ background: 'var(--bg)' }}>
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between mb-5">
            <div className="flex items-center gap-3">
              <h1
                className="text-[19px] tracking-tight text-zinc-100"
                style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, textTransform: 'uppercase', letterSpacing: '0.04em', fontVariationSettings: "'opsz' 144" }}
              >
                Mount Helicon
              </h1>
              <span className="text-[10px] text-zinc-500 tracking-widest uppercase font-medium">Memory Audit</span>
              <span
                className="text-[9px] px-2 py-0.5 rounded-full font-medium tracking-wide border"
                style={{ background: 'rgba(194, 94, 58, 0.08)', color: 'var(--helicon-accent)', borderColor: 'rgba(194, 94, 58, 0.25)' }}
              >
                Powered by Qwen
              </span>
            </div>
            <div className="flex items-center gap-3">
              {/* Attention bar: live findings severity split, click-through to FINDINGS */}
              {findingsData && (criticalCount > 0 || warningCount > 0) && (
                <button
                  onClick={() => setTab('findings')}
                  className="text-[11px] tabular-nums transition-opacity hover:opacity-70"
                >
                  <span style={{ color: 'var(--helicon-accent)' }}>{criticalCount} critical</span>
                  <span className="text-zinc-700"> · </span>
                  <span style={{ color: 'var(--helicon-stale)' }}>{warningCount} warning</span>
                </button>
              )}
              {score && (
                <div className="flex items-center gap-1.5" title={`${score.reviewed} of ${score.total} memory items triaged — review coverage, not a health grade`}>
                  <div className="w-16 h-1.5 rounded-full bg-zinc-800/60 overflow-hidden">
                    <div
                      className="h-full rounded-full qwen-gradient-bg transition-all duration-700"
                      style={{ width: `${score.score}%` }}
                    />
                  </div>
                  <span className="text-[12px] text-zinc-400 tabular-nums font-medium">{score.score}%</span>
                  <span className="text-[10px] text-zinc-600">reviewed</span>
                </div>
              )}
            </div>
          </div>

          <nav className="flex items-stretch gap-0 border-b border-zinc-800/60">
            {PRIMARY_TABS.map((t, i) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`px-4 py-2.5 text-[12px] uppercase tracking-[0.12em] transition-colors relative ${
                  tab === t.key ? 'text-zinc-200' : 'text-zinc-500 hover:text-zinc-400'
                }`}
              >
                <span className="text-zinc-600 mr-1.5 text-[11px] tabular-nums tracking-normal">{i + 1}</span>
                {t.label}
                {t.key === 'findings' && findingsData && findingsData.summary.total > 0 && (
                  <span className="ml-1.5 text-[10px] tabular-nums tracking-normal" style={{ color: 'var(--helicon-accent)' }}>
                    {findingsData.summary.total}
                  </span>
                )}
                {tab === t.key && (
                  <motion.span
                    layoutId="tab-indicator"
                    className="absolute bottom-0 left-4 right-4 h-[2px] rounded-full qwen-gradient-bg"
                    transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                  />
                )}
              </button>
            ))}
            <div className="ml-auto flex items-stretch">
              {SECONDARY_TABS.map((t, i) => (
                <button
                  key={t.key}
                  onClick={() => { setTab(t.key); if (t.key !== 'projects') setSelectedProject(null); }}
                  className={`px-3 py-2.5 text-[11px] transition-colors relative ${
                    tab === t.key ? 'text-zinc-400' : 'text-zinc-600 hover:text-zinc-500'
                  }`}
                >
                  <span className="text-zinc-700 mr-1 text-[10px] tabular-nums">{PRIMARY_TABS.length + i + 1}</span>
                  {t.label}
                  {t.key === 'projects' && projects.length > 0 && (
                    <span className="ml-1 text-[10px] text-zinc-700 tabular-nums">{projects.length}</span>
                  )}
                  {tab === t.key && (
                    <motion.span
                      layoutId="tab-indicator"
                      className="absolute bottom-0 left-3 right-3 h-[2px] rounded-full qwen-gradient-bg opacity-60"
                      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                    />
                  )}
                </button>
              ))}
            </div>
          </nav>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-8 py-6">
        <AnimatePresence mode="wait">
        <motion.div
          key={tab + (selectedProject || '')}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >

        {tab === 'focus' && <Focus />}

        {tab === 'health' && (
          <div className="space-y-10">
            <ContextHero
              score={score}
              needsYou={findingsData?.summary?.needs_you ?? 0}
              onReview={() => setTab('findings')}
            />

            <HeliconMountain />

            <div className="border-t border-zinc-800/40 pt-8">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div>
                  <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-4">Review coverage by source</h3>
                  {score && (
                    <div className="space-y-3">
                      {Object.entries(score.by_source).map(([src, data]) => (
                        <div key={src} className="flex items-center justify-between">
                          <span className="text-[13px] text-zinc-400">{src}</span>
                          <div className="flex items-center gap-4">
                            <span className="text-[11px] text-zinc-600 tabular-nums">{data.reviewed}/{data.total}</span>
                            <span className="text-[13px] text-zinc-300 tabular-nums w-10 text-right">{data.score}%</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <ConnectorStatus connectors={connectors} />
              </div>
            </div>
          </div>
        )}

        {tab === 'findings' && (
          <>
          <TabPurpose>What Helicon caught in your memory — drift, staleness, and things worth sharpening. You rule once; it sticks.</TabPurpose>
          <FindingsView
            data={findingsData}
            onReload={loadFindings}
            onActed={handleFindingActed}
            batteryLoading={batteryLoading}
            batteryIncluded={batteryIncluded}
          />
          </>
        )}

        {tab === 'gold' && (
          <>
          <TabPurpose>What you feed the agent next — your rulings, compiled into GOLDEN RULES with provenance. Copy it into the next session.</TabPurpose>
          <GoldView />
          </>
        )}

        {tab === 'routines' && (
          <>
          <TabPurpose>The stack around your memory — the routines that feed it and the skills your agent loads. Silent crons and duplicate skills surface here.</TabPurpose>
          <SkillsAudit />
          </>
        )}

        {tab === 'evals' && (
          <>
          <TabPurpose>Talk to your agent — test what a task retrieves, run the battery, then transfer the compiled context into your next session.</TabPurpose>
          <EvalView />
          </>
        )}

          {tab === 'log' && (
          <>
          <TabPurpose>What Helicon did and what you decided — every action is a receipt.</TabPurpose>
          <LogView />
          </>
        )}

        {tab === 'graph' && <ConflictMap />}
        {false && (
          <>
          <TabPurpose>Where the rot lives in your knowledge graph.</TabPurpose>
          <Graph3D />
          </>
        )}

        {tab === 'projects' && !selectedProject && (
          <>
          <TabPurpose>Compiled knowledge per project — copy it into your agent's context.</TabPurpose>
          <ProjectsGrid
            projects={projects}
            score={score}
            connectors={connectors}
            triageCount={triageCount}
            onSelect={setSelectedProject}
            onRefresh={loadProjects}
          />
          </>
        )}

        {tab === 'projects' && selectedProject && (
          <ProjectDetail
            project={projects.find(p => p.name === selectedProject)!}
            consolidations={getProjectConsolidations(selectedProject)}
            allConsolidations={projectConsolidations}
            onBack={() => setSelectedProject(null)}
            onInject={handleInjectContext}
            copied={copied}
          />
        )}

        </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

// One muted line under each tab's top bar stating what the screen is for.
function TabPurpose({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] text-zinc-600 mb-5 leading-relaxed">{children}</p>;
}

// ============================================================
// Helicon Score strip (HEALTH tab)
// ============================================================

/* The front door. States the promise, the loop, and the two honest numbers:
   what needs a human ruling now (the alarm, terracotta) and how much of the
   memory has been triaged (coverage — deliberately NOT framed as a health grade,
   because it is just reviewed/total). Daily-use framing kills the "do I live
   in this dashboard?" question up front. */
function ContextHero({ score, needsYou, onReview }: { score: Score | null; needsYou: number; onReview: () => void }) {
  const coverage = score?.score ?? 0;
  const reviewed = score?.reviewed ?? 0;
  const total = score?.total ?? 0;
  const step = (label: string) => <b style={{ color: 'var(--helicon-ink)', fontWeight: 600 }}>{label}</b>;

  return (
    <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
      <div className="text-[10px] uppercase tracking-[0.3em]" style={{ color: 'var(--helicon-muted)' }}>
        Agent memory audit
      </div>

      <p className="mt-2.5 text-[15px] leading-relaxed" style={{ color: 'var(--helicon-ink)', maxWidth: '56ch' }}>
        Your agent repeats corrections you already made, and its memory files rot silently.
        Helicon tests that memory for rot and hands the corrections back so they stick.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]" style={{ color: 'var(--helicon-muted)' }}>
        {step('Reads')} <span>your memory</span>
        <span style={{ opacity: 0.4 }}>→</span>
        {step('tests')} <span>it on a timer</span>
        <span style={{ opacity: 0.4 }}>→</span>
        {step('you rule')} <span>what's rotting</span>
        <span style={{ opacity: 0.4 }}>→</span>
        {step('compiles')} <span>GOLDEN RULES you paste into the next session</span>
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-x-10 gap-y-4">
        <div className="flex items-center gap-4">
          <div className="flex items-baseline gap-2">
            <span
              className="text-[40px] tabular-nums leading-none"
              style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, fontVariationSettings: "'opsz' 144", color: needsYou > 0 ? 'var(--helicon-accent)' : 'var(--helicon-ink)' }}
            >
              {needsYou}
            </span>
            <span className="text-[13px]" style={{ color: 'var(--helicon-muted)' }}>need your ruling</span>
          </div>
          {needsYou > 0 && (
            <button
              onClick={onReview}
              className="text-[12px] font-medium px-3.5 py-1.5 rounded-lg text-white transition-opacity hover:opacity-90"
              style={{ background: 'var(--helicon-accent)' }}
            >
              Review →
            </button>
          )}
        </div>

        <div className="flex items-baseline gap-2">
          <span className="text-[22px] tabular-nums" style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, color: 'var(--helicon-ink)' }}>
            {coverage}%
          </span>
          <span className="text-[12px]" style={{ color: 'var(--helicon-muted)' }}>
            reviewed <span style={{ opacity: 0.75 }}>({reviewed.toLocaleString()} of {total.toLocaleString()} triaged — coverage, not a health grade)</span>
          </span>
        </div>
      </div>

      <p className="mt-5 text-[11px]" style={{ color: 'var(--helicon-muted)' }}>
        Helicon runs on a timer and pings you when something needs a call. You don't live here — you drop in when it does.
      </p>
    </div>
  );
}

// ============================================================
// Project Grid - compiled-context export (secondary surface)
// ============================================================

function ProjectsGrid({ projects, score, connectors, triageCount, onSelect, onRefresh }: {
  projects: ProjectRollup[];
  score: Score | null;
  connectors: Connector[];
  triageCount: number;
  onSelect: (name: string) => void;
  onRefresh: () => void;
}) {
  const sorted = [...projects].sort((a, b) => {
    // Active projects first (recent output), then by cube count
    const aActive = a.days_since_output !== null && a.days_since_output < 14;
    const bActive = b.days_since_output !== null && b.days_since_output < 14;
    if (aActive && !bActive) return -1;
    if (!aActive && bActive) return 1;
    return b.cube_count - a.cube_count;
  });

  return (
    <div className="space-y-6">
      {/* Stats bar */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-5">
          <div>
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">Projects</span>
            <span className="text-[22px] font-light tabular-nums text-zinc-200">{projects.length}</span>
          </div>
          <div className="h-8 w-px bg-zinc-800/60" />
          <div>
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">Total Items</span>
            <span className="text-[22px] font-light tabular-nums text-zinc-200">{score?.total.toLocaleString() || 0}</span>
          </div>
          <div className="h-8 w-px bg-zinc-800/60" />
          <div>
            <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">Sources</span>
            <span className="text-[22px] font-light tabular-nums text-zinc-200">{connectors.length}</span>
          </div>
          {triageCount > 0 && (
            <>
              <div className="h-8 w-px bg-zinc-800/60" />
              <div>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 block">Auto-triaged</span>
                <span className="text-[22px] font-light tabular-nums text-emerald-600">{triageCount}</span>
              </div>
            </>
          )}
        </div>
        <button
          onClick={onRefresh}
          className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-800/60 text-zinc-500 hover:text-zinc-800 hover:border-zinc-400 transition-all active:scale-95 shadow-sm bg-white"
        >
          Refresh
        </button>
      </div>

      {/* Helicon explanation */}
      <div className="rounded-xl border border-zinc-300 bg-gradient-to-r from-zinc-50 to-zinc-100 px-5 py-4 qwen-shimmer">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[13px] text-zinc-300 font-medium">Select a project</p>
            <p className="text-[11px] text-zinc-500 mt-0.5">
              View consolidated knowledge, then inject context into your next agent session.
            </p>
          </div>
          <span className="text-[10px] px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-700 font-medium">
            {score?.score || 0}% reviewed
          </span>
        </div>
      </div>

      {/* Project cards grid */}
      {sorted.length === 0 ? (
        <div className="py-20 text-center">
          <p className="text-zinc-500 text-sm mb-1">No projects detected yet.</p>
          <p className="text-zinc-600 text-[12px]">Run a scan to extract projects from your agent output.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {sorted.map((project, i) => (
            <ProjectCard
              key={project.name}
              project={project}
              index={i}
              onClick={() => onSelect(project.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({ project, index, onClick }: { project: ProjectRollup; index: number; onClick: () => void }) {
  const isActive = project.days_since_output !== null && project.days_since_output < 14;
  const shipPct = (project.ship_rate * 100).toFixed(0);

  return (
    <motion.button
      onClick={onClick}
      className="text-left p-4 rounded-xl border border-zinc-800/60 bg-white hover:border-zinc-400 hover:shadow-md hover:shadow-zinc-200/60 transition-all group shadow-sm"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {isActive && (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-subtle" />
          )}
          <h3 className="text-[13px] font-medium text-zinc-200 group-hover:text-zinc-800 transition-colors">
            {project.name}
          </h3>
        </div>
        <span className="text-[11px] text-zinc-600 tabular-nums">{project.cube_count}</span>
      </div>

      {/* Mini stats */}
      <div className="flex items-center gap-3 text-[11px] mb-3">
        <span className="text-zinc-500">{shipPct}% shipped</span>
        {project.pending > 0 && (
          <span className="text-zinc-600">{project.pending} pending</span>
        )}
        {project.spin_score > 0 && (
          <span className="text-amber-600" title="spin = sessions spent per item shipped. Above 3, this project is circling: lots of activity, nothing landing.">{project.spin_score.toFixed(1)} spin</span>
        )}
      </div>

      {/* Confidence bar */}
      <div className="h-1 rounded-full bg-zinc-900/60 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${project.avg_confidence * 100}%`,
            background: 'var(--helicon-accent)', opacity: 0.75,
          }}
        />
      </div>
      <div className="flex justify-between mt-1.5">
        <span className="text-[10px] text-zinc-600">
          {project.sources.slice(0, 2).join(', ')}
        </span>
        <span className="text-[10px] text-zinc-600 tabular-nums">
          {(project.avg_confidence * 100).toFixed(0)}%
        </span>
      </div>
    </motion.button>
  );
}

// ============================================================
// Project Detail - consolidation + inject context
// ============================================================

function ProjectDetail({ project, consolidations, allConsolidations, onBack, onInject, copied }: {
  project: ProjectRollup;
  consolidations: Consolidation[];
  allConsolidations: Consolidation[];
  onBack: () => void;
  onInject: (p: ProjectRollup) => void;
  copied: boolean;
}) {
  const [running, setRunning] = useState(false);

  if (!project) {
    return (
      <div className="py-20 text-center">
        <p className="text-zinc-500">Project not found.</p>
        <button onClick={onBack} className="text-zinc-600 text-sm mt-2 hover:text-zinc-700">Back to projects</button>
      </div>
    );
  }

  const handleConsolidate = async () => {
    setRunning(true);
    try {
      await api.runConsolidation(true, 5);
    } catch {}
    setRunning(false);
  };

  // Show project-relevant consolidations, or all if none match
  const displayConsolidations = consolidations.length > 0 ? consolidations : allConsolidations.slice(0, 8);
  const showingAll = consolidations.length === 0 && allConsolidations.length > 0;

  return (
    <div className="space-y-6">
      {/* Back + header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <button
            onClick={onBack}
            className="text-[12px] text-zinc-500 hover:text-zinc-600 transition-colors flex items-center gap-1"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Projects
          </button>
          <span className="text-zinc-700">/</span>
          <h2 className="text-[16px] font-medium text-zinc-200">{project.name}</h2>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleConsolidate}
            disabled={running}
            className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-800/60 text-zinc-500 hover:text-zinc-600 hover:border-zinc-400 transition-all disabled:opacity-30 shadow-sm bg-white"
          >
            {running ? 'Consolidating...' : 'Run Sleep Cycle'}
          </button>
          <button
            onClick={() => onInject(project)}
            title="Paste into your agent (CLAUDE.md, system prompt)"
            className="text-[12px] px-4 py-1.5 rounded-lg text-white font-medium transition-all active:scale-95 shadow-sm hover:shadow-md hover:shadow-violet-200/50"
            style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #6366F1 100%)' }}
          >
            {copied ? 'Copied!' : 'Copy compiled context'}
          </button>
        </div>
      </div>

      {/* Project stats */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <StatCard label="Items" value={project.cube_count.toString()} />
        <StatCard label="Shipped" value={`${(project.ship_rate * 100).toFixed(0)}%`} sub={`${project.shipped} items`} />
        <StatCard label="Pending" value={project.pending.toString()} highlight={project.pending > 10} />
        <StatCard label="Confidence" value={`${(project.avg_confidence * 100).toFixed(0)}%`} />
        <StatCard
          label="Last Output"
          value={project.days_since_output !== null ? `${project.days_since_output}d` : 'n/a'}
        />
      </div>

      {/* Source breakdown */}
      <div className="flex items-center gap-2 flex-wrap">
        {project.sources.map(s => (
          <span key={s} className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-700 border border-violet-100">
            {s}
          </span>
        ))}
        {Object.entries(project.types).map(([type, count]) => (
          <span key={type} className="text-[11px] px-2.5 py-1 rounded-full bg-zinc-900/60 text-zinc-500 border border-zinc-800/60">
            {type}: {count}
          </span>
        ))}
      </div>

      {/* Consolidated knowledge */}
      <div className="border border-zinc-800/60 rounded-xl bg-white shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-zinc-800/40">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-[14px] font-medium text-zinc-200">
                {showingAll ? 'All Consolidated Knowledge' : 'Project Knowledge'}
              </h3>
              <p className="text-[11px] text-zinc-500 mt-0.5">
                {showingAll
                  ? `No project-specific consolidations yet. Showing all ${displayConsolidations.length} topics.`
                  : `${displayConsolidations.length} consolidated topics from ${project.name}`
                }
              </p>
            </div>
            <button
              onClick={() => onInject(project)}
              title="Paste into your agent (CLAUDE.md, system prompt)"
              className="text-[11px] px-3 py-1 rounded-md text-zinc-700 hover:bg-zinc-100 border border-zinc-300 transition-colors"
            >
              {copied ? 'Copied!' : 'Copy compiled context'}
            </button>
          </div>
        </div>

        {displayConsolidations.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-zinc-500 text-[13px] mb-1">No consolidations yet.</p>
            <p className="text-zinc-600 text-[12px]">Run a Sleep Cycle to merge related memories into consolidated knowledge.</p>
          </div>
        ) : (
          <div className="divide-y divide-zinc-800/30">
            {displayConsolidations.map(c => (
              <ConsolidationDetailRow key={c.id} consolidation={c} />
            ))}
          </div>
        )}
      </div>

      {/* Type breakdown */}
      {Object.keys(project.types).length > 0 && (
        <div className="border border-zinc-800/60 rounded-xl bg-white shadow-sm p-5">
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-4">Memory Types</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {Object.entries(project.types)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => (
                <div key={type} className="text-center">
                  <span className="text-[18px] font-light tabular-nums text-zinc-300">{count}</span>
                  <p className="text-[11px] text-zinc-500 mt-0.5">{type}</p>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, sub, highlight }: { label: string; value: string; sub?: string; highlight?: boolean }) {
  return (
    <div className={`rounded-xl border px-4 py-3 text-center shadow-sm ${
      highlight
        ? 'border-zinc-300 bg-zinc-100'
        : 'border-zinc-800/60 bg-white'
    }`}>
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">{label}</span>
      <span className={`text-[18px] font-light tabular-nums ${highlight ? 'text-zinc-700' : 'text-zinc-200'}`}>{value}</span>
      {sub && <span className="text-[10px] text-zinc-600 block">{sub}</span>}
    </div>
  );
}

function ConsolidationDetailRow({ consolidation }: { consolidation: Consolidation }) {
  const [expanded, setExpanded] = useState(false);
  const [itemCopied, setItemCopied] = useState(false);

  const handleCopy = (e: React.MouseEvent) => {
    e.stopPropagation();
    const text = `## ${consolidation.title}\n\n${consolidation.summary}\n\n(${consolidation.cube_count} items merged)`;
    navigator.clipboard.writeText(text).then(() => {
      setItemCopied(true);
      setTimeout(() => setItemCopied(false), 1500);
    });
  };

  return (
    <div className="group">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-5 py-3.5 hover:bg-zinc-100/50 transition-colors">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5 min-w-0">
            <span className="text-[13px] text-zinc-300 truncate">{consolidation.title}</span>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <span className="text-[10px] text-zinc-600 tabular-nums">{consolidation.cube_count} merged</span>
            <span className={`text-[11px] tabular-nums ${consolidation.confidence < 0.3 ? 'text-amber-600' : 'text-zinc-500'}`}>
              {(consolidation.confidence * 100).toFixed(0)}%
            </span>
            <button
              onClick={handleCopy}
              className="text-[10px] text-zinc-600 hover:text-zinc-600 transition-colors opacity-0 group-hover:opacity-100"
            >
              {itemCopied ? 'Copied' : 'Copy'}
            </button>
            <svg
              width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              className={`text-zinc-600 transition-transform ${expanded ? 'rotate-180' : ''}`}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </div>
        </div>
      </button>
      {expanded && (
        <div className="px-5 pb-4 animate-fade-in">
          <p className="text-[12px] text-zinc-400 leading-relaxed bg-zinc-900/40 rounded-lg p-3 border border-zinc-800/30">
            {consolidation.summary}
          </p>
        </div>
      )}
    </div>
  );
}

export default App;
