import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from './api';
import type { Score, Cube, AuditFinding, DecayStats, Connector, ProjectRollup, Consolidation } from './api';
import { ReviewCard } from './components/ReviewCard';
import { AuditPanel } from './components/AuditPanel';
import { Graph3D } from './components/Graph3D';
import { ConsolidationView } from './components/ConsolidationView';
import { ContradictionView } from './components/ContradictionView';
import { TokenDashboard } from './components/TokenDashboard';
import { TriageView } from './components/TriageView';
import { EvalView } from './components/EvalView';
import { ConnectorStatus } from './components/ConnectorStatus';
import { DecayHeatmap } from './components/Charts';

type Tab = 'projects' | 'review' | 'insights' | 'graph' | 'system';

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'projects', label: 'Projects', icon: '◆' },
  { key: 'review', label: 'Review', icon: '○' },
  { key: 'insights', label: 'Insights', icon: '△' },
  { key: 'graph', label: 'Graph', icon: '◎' },
  { key: 'system', label: 'System', icon: '⚙' },
];

function App() {
  const [tab, setTab] = useState<Tab>('projects');
  const [score, setScore] = useState<Score | null>(null);
  const [cubes, setCubes] = useState<Cube[]>([]);
  const [total, setTotal] = useState(0);
  const [findings, setFindings] = useState<AuditFinding[]>([]);
  const [decayStats, setDecayStats] = useState<DecayStats | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [filter, setFilter] = useState({ source: '', type: '', sort: 'urgency' });
  const [loading, setLoading] = useState(true);
  const [focusIdx, setFocusIdx] = useState(0);
  const [search, setSearch] = useState('');
  const [triageCount, setTriageCount] = useState(0);
  const [showTriage, setShowTriage] = useState(false);

  // Project-centric state
  const [projects, setProjects] = useState<ProjectRollup[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [projectConsolidations, setProjectConsolidations] = useState<Consolidation[]>([]);
  const [copied, setCopied] = useState(false);

  const refresh = useCallback(async () => {
    const [s, d, c, t] = await Promise.all([
      api.getScore(),
      api.getDecayStats(),
      api.getConnectors(),
      api.getTriageStats().catch(() => ({ total_triaged: 0 })),
    ]);
    setScore(s);
    setDecayStats(d);
    setConnectors(c.connectors);
    setTriageCount(t.total_triaged);
  }, []);

  const loadCubes = useCallback(async () => {
    const params: Record<string, string | number> = { limit: 30, sort: filter.sort };
    if (filter.source) params.source = filter.source;
    if (filter.type) params.type = filter.type;
    params.status = 'pending';
    const res = await api.getCubes(params);
    setCubes(res.cubes);
    setTotal(res.total);
  }, [filter]);

  const loadFindings = useCallback(async () => {
    const res = await api.getAudit();
    setFindings(res.findings);
  }, []);

  const loadProjects = useCallback(async () => {
    const res = await api.getProjects().catch(() => ({ projects: [] }));
    setProjects(res.projects);
  }, []);

  const loadConsolidations = useCallback(async () => {
    const res = await api.getConsolidations().catch(() => ({ consolidations: [] }));
    setProjectConsolidations(res.consolidations);
  }, []);

  useEffect(() => {
    Promise.all([refresh(), loadCubes(), loadFindings(), loadProjects(), loadConsolidations()])
      .then(() => setLoading(false));
  }, [refresh, loadCubes, loadFindings, loadProjects, loadConsolidations]);

  const handleReviewed = async () => {
    await Promise.all([refresh(), loadCubes()]);
  };

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const idx = parseInt(e.key) - 1;
      if (idx >= 0 && idx < TABS.length) setTab(TABS[idx].key);
      if (tab === 'review') {
        if (e.key === 'j') setFocusIdx(i => Math.min(i + 1, cubes.length - 1));
        if (e.key === 'k' && !e.metaKey) { e.preventDefault(); setFocusIdx(i => Math.max(i - 1, 0)); }
        if (e.key === '/') { e.preventDefault(); document.getElementById('cube-search')?.focus(); }
      }
      if (tab === 'projects' && e.key === 'Escape') setSelectedProject(null);
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [tab, cubes.length]);

  const filteredCubes = search
    ? cubes.filter(c => c.title.toLowerCase().includes(search.toLowerCase()) || c.content.toLowerCase().includes(search.toLowerCase()))
    : cubes;

  const criticalCount = findings.filter(f => f.severity === 'critical').length;

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
              <h1 className="text-[15px] font-semibold tracking-tight qwen-gradient-text">GLAZE</h1>
              <span className="text-[10px] text-zinc-500 tracking-widest uppercase font-medium">Memory Audit</span>
              <span className="text-[9px] px-2 py-0.5 rounded-full bg-violet-100 text-violet-600 font-medium tracking-wide">
                Powered by Qwen
              </span>
            </div>
            {score && (
              <div className="flex items-center gap-3">
                {criticalCount > 0 && (
                  <span className="text-[11px] text-red-500/80 tabular-nums">{criticalCount} critical</span>
                )}
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 rounded-full bg-zinc-800/60 overflow-hidden">
                    <div
                      className="h-full rounded-full qwen-gradient-bg transition-all duration-700"
                      style={{ width: `${score.score}%` }}
                    />
                  </div>
                  <span className="text-[12px] text-zinc-400 tabular-nums font-medium">{score.score}%</span>
                </div>
              </div>
            )}
          </div>

          <nav className="flex gap-0 border-b border-zinc-800/60">
            {TABS.map((t, i) => (
              <button
                key={t.key}
                onClick={() => { setTab(t.key); if (t.key !== 'projects') setSelectedProject(null); }}
                className={`px-4 py-2.5 text-[13px] transition-colors relative ${
                  tab === t.key
                    ? 'text-zinc-200'
                    : 'text-zinc-500 hover:text-zinc-400'
                }`}
              >
                <span className="text-zinc-600 mr-1.5 text-[11px] tabular-nums">{i + 1}</span>
                {t.label}
                {t.key === 'projects' && projects.length > 0 && (
                  <span className="ml-1.5 text-[10px] text-zinc-600 tabular-nums">{projects.length}</span>
                )}
                {t.key === 'review' && total > 0 && (
                  <span className="ml-1.5 text-[10px] text-zinc-600 tabular-nums">{total}</span>
                )}
                {t.key === 'insights' && findings.length > 0 && (
                  <span className="ml-1.5 text-[10px] text-zinc-600 tabular-nums">{findings.length}</span>
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

        {tab === 'projects' && !selectedProject && (
          <ProjectsGrid
            projects={projects}
            score={score}
            connectors={connectors}
            triageCount={triageCount}
            onSelect={setSelectedProject}
            onRefresh={loadProjects}
          />
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

        {tab === 'review' && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px] gap-8 overflow-hidden">
            <div>
              <div className="flex items-center gap-2 mb-6 flex-wrap">
                <input
                  id="cube-search"
                  type="text"
                  value={search}
                  onChange={e => { setSearch(e.target.value); setFocusIdx(0); }}
                  placeholder="Search cubes... (/)"
                  className="text-[12px] bg-white border border-zinc-800/60 rounded-lg px-3 py-1.5 text-zinc-400 placeholder:text-zinc-600 focus:outline-none focus:border-violet-400 focus:ring-1 focus:ring-violet-200 w-44 shadow-sm"
                  onKeyDown={e => { if (e.key === 'Escape') { setSearch(''); e.currentTarget.blur(); } }}
                />
                <StyledSelect
                  value={filter.source}
                  onChange={v => setFilter({ ...filter, source: v })}
                  options={[
                    ['', 'All sources'],
                    ['claude-code', 'Claude Code'],
                    ['obsidian', 'Obsidian'],
                    ['git', 'Git'],
                  ]}
                />
                <StyledSelect
                  value={filter.type}
                  onChange={v => setFilter({ ...filter, type: v })}
                  options={[
                    ['', 'All types'],
                    ['code', 'Code'],
                    ['memory', 'Memory'],
                    ['project', 'Project'],
                    ['draft', 'Draft'],
                    ['file_created', 'File'],
                    ['idea', 'Idea'],
                  ]}
                />
                <StyledSelect
                  value={filter.sort}
                  onChange={v => setFilter({ ...filter, sort: v })}
                  options={[
                    ['urgency', 'Most urgent'],
                    ['confidence', 'Lowest confidence'],
                    ['age', 'Oldest'],
                    ['newest', 'Newest'],
                  ]}
                />
                <span className="text-[10px] text-zinc-700 ml-auto hidden lg:block">j/k navigate, a/r/k review</span>
              </div>

              <div className="space-y-0">
                {filteredCubes.map((cube, i) => (
                  <div key={cube.id} className="animate-fade-in" style={{ animationDelay: `${i * 20}ms` }}>
                    <ReviewCard
                      cube={cube}
                      onReviewed={handleReviewed}
                      focused={i === focusIdx}
                      onAction={() => setFocusIdx(j => Math.min(j, filteredCubes.length - 2))}
                    />
                  </div>
                ))}
                {filteredCubes.length === 0 && (
                  <div className="py-20 text-center">
                    <p className="text-zinc-500 text-sm">{search ? 'No matches.' : 'Nothing to review. Memory is clean.'}</p>
                  </div>
                )}
              </div>
            </div>

            <aside className="space-y-6">
              <div>
                <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-3">Score</h3>
                <div className="flex items-baseline gap-2 mb-2">
                  <span className="text-3xl font-light tabular-nums text-zinc-200">
                    {score?.score}
                  </span>
                  <span className="text-[12px] text-zinc-600">/ 100</span>
                </div>
                <p className="text-[11px] text-zinc-600 leading-relaxed">
                  Review items: <strong className="text-zinc-400">Keep</strong>, <strong className="text-zinc-400">Revise</strong>, or <strong className="text-zinc-400">Kill</strong>. Score climbs as you review.
                </p>
              </div>

              <div className="border-t border-zinc-800/40 pt-4">
                <button
                  onClick={() => setShowTriage(!showTriage)}
                  className="flex items-center justify-between w-full text-left"
                >
                  <h3 className="text-[11px] uppercase tracking-wider text-zinc-500">Auto-Triage</h3>
                  <span className="text-[11px] text-zinc-600">{showTriage ? '-' : '+'}</span>
                </button>
                {showTriage && (
                  <div className="mt-3 animate-fade-in">
                    <AutoTriageCompact onTriaged={() => { refresh(); loadCubes(); }} />
                  </div>
                )}
                {!showTriage && triageCount > 0 && (
                  <p className="text-[11px] text-zinc-600 mt-1">{triageCount} items auto-handled</p>
                )}
              </div>

              <DecayHeatmap stats={decayStats} />
              <RecentReviews />
            </aside>
          </div>
        )}

        {tab === 'insights' && (
          <div className="grid grid-cols-1 lg:grid-cols-[1fr_260px] gap-8">
            <div>
              <div className="flex items-center justify-between mb-5">
                <h2 className="text-[14px] font-medium text-zinc-300">Audit Findings</h2>
                <div className="flex gap-2">
                  <GhostButton onClick={async () => { await api.runDecay(); refresh(); }}>
                    Run Decay
                  </GhostButton>
                  <GhostButton onClick={async () => { await api.runAudit(); loadFindings(); }} accent>
                    Run Audit
                  </GhostButton>
                </div>
              </div>
              <AuditPanel findings={findings} onRefresh={loadFindings} />

              <div className="border-t border-zinc-800/40 mt-10 pt-8">
                <PatternView />
              </div>

              <div className="border-t border-zinc-800/40 mt-10 pt-8">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                  <ConsolidationView />
                  <ContradictionView />
                </div>
              </div>
            </div>
            <aside className="space-y-6">
              <div>
                <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-4">Audit Axes</h3>
                <div className="space-y-4">
                  {[
                    { type: 'temporal', label: 'Temporal', desc: 'Stale time references' },
                    { type: 'factual', label: 'Factual', desc: 'Contradictions' },
                    { type: 'decay', label: 'Decay', desc: 'Below threshold' },
                    { type: 'logical', label: 'Logical', desc: 'Weak patterns' },
                  ].map(a => {
                    const count = findings.filter(f => f.audit_type === a.type).length;
                    return (
                      <div key={a.type} className="flex items-baseline justify-between">
                        <div>
                          <span className="text-[13px] text-zinc-400">{a.label}</span>
                          <p className="text-[11px] text-zinc-600">{a.desc}</p>
                        </div>
                        <span className="text-[12px] tabular-nums text-zinc-500">{count}</span>
                      </div>
                    );
                  })}
                </div>
              </div>

              <SpinView />
              <KillCandidatesView />
            </aside>
          </div>
        )}

        {tab === 'graph' && <Graph3D />}

        {tab === 'system' && (
          <div className="space-y-10">
            <div className="max-w-2xl">
              <h2 className="text-[15px] font-medium text-zinc-200 mb-2">Setup</h2>
              <p className="text-[12px] text-zinc-600 mb-5">Three commands to go from zero to auditing your agent memory.</p>
              <div className="space-y-3 text-[12px] text-zinc-500 leading-relaxed">
                <div className="border border-zinc-800/60 rounded-lg p-4 bg-white shadow-sm">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-[10px] font-mono text-white bg-violet-500 px-1.5 py-0.5 rounded">1</span>
                    <h4 className="text-zinc-300 font-medium">Install and detect</h4>
                  </div>
                  <code className="block text-[11px] text-violet-600 bg-violet-50 border border-violet-100 rounded-md px-3 py-2 mb-2 font-mono">pip install glaze-audit && glaze init</code>
                  <p className="text-zinc-500">Auto-detects Claude Code, Cursor, Obsidian vaults, and git repos.</p>
                </div>
                <div className="border border-zinc-800/60 rounded-lg p-4 bg-white shadow-sm">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-[10px] font-mono text-white bg-violet-500 px-1.5 py-0.5 rounded">2</span>
                    <h4 className="text-zinc-300 font-medium">Scan and serve</h4>
                  </div>
                  <code className="block text-[11px] text-violet-600 bg-violet-50 border border-violet-100 rounded-md px-3 py-2 mb-2 font-mono">glaze scan && glaze serve</code>
                  <p className="text-zinc-500">Extracts memory items, computes confidence scores, starts the UI.</p>
                </div>
                <div className="border border-zinc-800/60 rounded-lg p-4 bg-white shadow-sm">
                  <div className="flex items-baseline gap-2 mb-2">
                    <span className="text-[10px] font-mono text-white bg-violet-500 px-1.5 py-0.5 rounded">3</span>
                    <h4 className="text-zinc-300 font-medium">Review and teach</h4>
                  </div>
                  <p className="text-zinc-500 mb-2">Review items: <strong className="text-zinc-400">Keep</strong>, <strong className="text-zinc-400">Revise</strong>, or <strong className="text-zinc-400">Kill</strong>. GLAZE learns your patterns and auto-triages the obvious stuff.</p>
                  <p className="text-zinc-500">Connect via MCP for agent self-audit: your agents can query their own memory health.</p>
                </div>
              </div>
            </div>

            <div className="border-t border-zinc-800/40 pt-8">
              <h3 className="text-[15px] font-medium text-zinc-200 mb-4">Auto-Triage</h3>
              <TriageView onTriaged={() => { refresh(); loadCubes(); }} />
            </div>

            <div className="border-t border-zinc-800/40 pt-8">
              <h3 className="text-[15px] font-medium text-zinc-200 mb-4">Evaluation</h3>
              <EvalView />
            </div>

            <div className="border-t border-zinc-800/40 pt-8">
              <h3 className="text-[15px] font-medium text-zinc-200 mb-6">Qwen Cloud</h3>
              <TokenDashboard />
            </div>

            <div className="border-t border-zinc-800/40 pt-8">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                <div>
                  <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-4">Stats</h3>
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

            <SessionDriftView />
          </div>
        )}

        </motion.div>
        </AnimatePresence>
      </main>
    </div>
  );
}

// ============================================================
// Project Grid - the primary landing view
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
          className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-800/60 text-zinc-500 hover:text-violet-600 hover:border-violet-300 transition-all active:scale-95 shadow-sm bg-white"
        >
          Refresh
        </button>
      </div>

      {/* Glaze explanation */}
      <div className="rounded-xl border border-violet-200 bg-gradient-to-r from-violet-50 to-indigo-50 px-5 py-4 qwen-shimmer">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[13px] text-zinc-300 font-medium">Select a project to start glazing</p>
            <p className="text-[11px] text-zinc-500 mt-0.5">
              View consolidated knowledge, then inject context into your next agent session.
            </p>
          </div>
          <span className="text-[10px] px-2.5 py-1 rounded-full bg-violet-100 text-violet-600 font-medium">
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
      className="text-left p-4 rounded-xl border border-zinc-800/60 bg-white hover:border-violet-300 hover:shadow-md hover:shadow-violet-100/50 transition-all group shadow-sm"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03, duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
    >
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          {isActive && (
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse-subtle" />
          )}
          <h3 className="text-[13px] font-medium text-zinc-200 group-hover:text-violet-600 transition-colors">
            {project.name}
          </h3>
        </div>
        <span className="text-[11px] text-zinc-600 tabular-nums">{project.cube_count}</span>
      </div>

      {/* Mini stats */}
      <div className="flex items-center gap-3 text-[11px] mb-3">
        <span className="text-zinc-500">{shipPct}% shipped</span>
        {project.pending > 0 && (
          <span className="text-violet-500">{project.pending} pending</span>
        )}
        {project.spin_score > 0 && (
          <span className="text-amber-600">{project.spin_score.toFixed(1)} spin</span>
        )}
      </div>

      {/* Confidence bar */}
      <div className="h-1 rounded-full bg-zinc-900/60 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{
            width: `${project.avg_confidence * 100}%`,
            background: `linear-gradient(90deg, #7C3AED ${Math.max(0, 100 - project.avg_confidence * 100)}%, #6366F1 100%)`,
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
        <button onClick={onBack} className="text-violet-500 text-sm mt-2 hover:text-violet-400">Back to projects</button>
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
            className="text-[12px] text-zinc-500 hover:text-violet-500 transition-colors flex items-center gap-1"
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
            className="text-[12px] px-3 py-1.5 rounded-lg border border-zinc-800/60 text-zinc-500 hover:text-violet-500 hover:border-violet-300 transition-all disabled:opacity-30 shadow-sm bg-white"
          >
            {running ? 'Consolidating...' : 'Run Sleep Cycle'}
          </button>
          <button
            onClick={() => onInject(project)}
            className="text-[12px] px-4 py-1.5 rounded-lg text-white font-medium transition-all active:scale-95 shadow-sm hover:shadow-md hover:shadow-violet-200/50"
            style={{ background: 'linear-gradient(135deg, #7C3AED 0%, #6366F1 100%)' }}
          >
            {copied ? 'Copied!' : 'Inject Context'}
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
          <span key={s} className="text-[11px] px-2.5 py-1 rounded-full bg-violet-50 text-violet-600 border border-violet-100">
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
              className="text-[11px] px-3 py-1 rounded-md text-violet-600 hover:bg-violet-50 border border-violet-200 transition-colors"
            >
              {copied ? 'Copied!' : 'Copy All'}
            </button>
          </div>
        </div>

        {displayConsolidations.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-zinc-500 text-[13px] mb-1">No consolidations yet.</p>
            <p className="text-zinc-600 text-[12px]">Run a Sleep Cycle to merge related cubes into consolidated knowledge.</p>
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
        ? 'border-violet-200 bg-violet-50'
        : 'border-zinc-800/60 bg-white'
    }`}>
      <span className="text-[10px] text-zinc-500 uppercase tracking-wider block">{label}</span>
      <span className={`text-[18px] font-light tabular-nums ${highlight ? 'text-violet-600' : 'text-zinc-200'}`}>{value}</span>
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
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left px-5 py-3.5 hover:bg-violet-50/50 transition-colors">
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
              className="text-[10px] text-zinc-600 hover:text-violet-500 transition-colors opacity-0 group-hover:opacity-100"
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

// ============================================================
// Shared UI components
// ============================================================

function StyledSelect({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  const [open, setOpen] = useState(false);
  const label = options.find(([v]) => v === value)?.[1] || options[0][1];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="text-[12px] bg-white border border-zinc-800/60 rounded-lg px-3 py-1.5 text-zinc-400 hover:border-violet-300 hover:text-zinc-300 transition-colors flex items-center gap-1.5 min-w-[100px] shadow-sm"
      >
        <span className="truncate">{label}</span>
        <svg width="10" height="6" viewBox="0 0 10 6" className="shrink-0 opacity-40">
          <path d="M1 1l4 4 4-4" stroke="currentColor" strokeWidth="1.5" fill="none" />
        </svg>
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setOpen(false)} />
          <div className="absolute top-full left-0 mt-1 z-20 bg-white border border-zinc-800/60 rounded-lg shadow-xl shadow-zinc-200/40 py-1 min-w-[140px] animate-fade-in">
            {options.map(([v, l]) => (
              <button
                key={v}
                onClick={() => { onChange(v); setOpen(false); }}
                className={`w-full text-left px-3 py-1.5 text-[12px] transition-colors ${
                  v === value ? 'text-violet-600 bg-violet-50' : 'text-zinc-400 hover:text-zinc-300 hover:bg-zinc-900/40'
                }`}
              >
                {l}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

function AutoTriageCompact({ onTriaged }: { onTriaged: () => void }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<{ triaged: number } | null>(null);

  const run = async (dryRun: boolean) => {
    setRunning(true);
    const r = await api.runTriage(dryRun);
    setResult({ triaged: r.triaged });
    if (!dryRun) onTriaged();
    setRunning(false);
  };

  return (
    <div className="space-y-2">
      <p className="text-[11px] text-zinc-600 leading-relaxed">
        Auto-kill/approve items that match learned patterns with high confidence.
      </p>
      <div className="flex gap-2">
        <button onClick={() => run(true)} disabled={running}
          className="text-[11px] px-2 py-1 rounded-md border border-zinc-800/60 text-zinc-500 hover:text-zinc-400 disabled:opacity-30 shadow-sm bg-white">
          Preview
        </button>
        <button onClick={() => run(false)} disabled={running}
          className="text-[11px] px-2 py-1 rounded-md border border-violet-200 text-violet-600 hover:bg-violet-50 disabled:opacity-30 shadow-sm bg-white">
          Execute
        </button>
      </div>
      {result && (
        <p className="text-[11px] text-emerald-600 animate-fade-in">{result.triaged} items processed</p>
      )}
    </div>
  );
}

function GhostButton({ children, onClick, accent }: { children: React.ReactNode; onClick: () => void; accent?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`text-[12px] px-3 py-1.5 rounded-lg border transition-all active:scale-95 shadow-sm bg-white ${
        accent
          ? 'border-violet-200 text-violet-600 hover:bg-violet-50'
          : 'border-zinc-800/60 text-zinc-500 hover:bg-zinc-900/40'
      }`}
    >
      {children}
    </button>
  );
}

function PatternView() {
  const [patterns, setPatterns] = useState<{ name: string; description: string; pattern_type: string; data_points: number; confidence: number }[]>([]);
  const [, setLoading] = useState(true);

  useEffect(() => {
    api.getPatterns().then(r => { setPatterns(r.patterns); setLoading(false); });
  }, []);

  const extract = async () => {
    setLoading(true);
    await api.extractPatterns();
    const r = await api.getPatterns();
    setPatterns(r.patterns);
    setLoading(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-[15px] font-medium text-zinc-200">Learned Patterns</h2>
        <GhostButton onClick={extract} accent>Extract</GhostButton>
      </div>
      {patterns.length === 0 ? (
        <div className="py-8 text-center">
          <p className="text-zinc-500 text-sm mb-1">No patterns yet.</p>
          <p className="text-zinc-600 text-[12px]">Review items first. GLAZE learns from your decisions.</p>
        </div>
      ) : (
        <div className="space-y-1">
          {patterns.map(p => (
            <div key={p.name} className="py-3 border-b border-zinc-800/30">
              <div className="flex items-baseline justify-between mb-0.5">
                <span className="text-[13px] text-zinc-300">{p.name}</span>
                <span className="text-[11px] text-zinc-600">{p.pattern_type}</span>
              </div>
              <p className="text-[12px] text-zinc-500">{p.description}</p>
              <div className="flex gap-4 mt-1 text-[11px] text-zinc-600">
                <span>{p.data_points} points</span>
                <span>{(p.confidence * 100).toFixed(0)}%</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SpinView() {
  const [spins, setSpins] = useState<{ tags: string[]; session_count: number; cube_count: number; unreviewed: number }[]>([]);

  useEffect(() => {
    fetch('/api/patterns/spin').then(r => r.json()).then(d => setSpins(d.spins?.slice(0, 5) || []));
  }, []);

  if (spins.length === 0) return null;

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-3">Spin Detection</h3>
      <div className="space-y-2">
        {spins.map((s, i) => (
          <div key={i} className="flex items-baseline justify-between text-[12px]">
            <span className="text-zinc-400 truncate max-w-[140px]">{s.tags.slice(0, 2).join(', ')}</span>
            <div className="flex items-center gap-3">
              <span className="text-amber-600 tabular-nums">{s.session_count}x</span>
              <span className="text-zinc-600 tabular-nums">{s.unreviewed}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function KillCandidatesView() {
  const [candidates, setCandidates] = useState<{ id: string; title: string; confidence: number; age_days: number; type: string }[]>([]);

  useEffect(() => {
    fetch('/api/patterns/kill-candidates').then(r => r.json()).then(d => setCandidates(d.candidates?.slice(0, 5) || []));
  }, []);

  if (candidates.length === 0) return null;

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-3">Kill Candidates</h3>
      <div className="space-y-2">
        {candidates.map(c => (
          <div key={c.id} className="text-[12px]">
            <div className="flex items-baseline justify-between">
              <span className="text-zinc-400 truncate max-w-[160px]">{c.title}</span>
              <span className="text-red-500/70 tabular-nums">{(c.confidence * 100).toFixed(1)}%</span>
            </div>
            <span className="text-[11px] text-zinc-600">{c.age_days.toFixed(0)}d - {c.type}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RecentReviews() {
  const [reviews, setReviews] = useState<{ id: number; cube_id: string; decision: string; cube_type: string; reviewed_at: string }[]>([]);

  useEffect(() => {
    api.getReviews(10).then(r => setReviews(r.reviews));
  }, []);

  if (reviews.length === 0) return null;

  const decisionColor = (d: string) => {
    if (d === 'approved') return 'text-green-600';
    if (d === 'killed') return 'text-red-500';
    return 'text-amber-600';
  };

  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-3">Recent Reviews</h3>
      <div className="space-y-1.5">
        {reviews.map(r => (
          <div key={r.id} className="flex items-center justify-between text-[11px]">
            <span className="text-zinc-500 truncate max-w-[160px]">{r.cube_type}</span>
            <span className={decisionColor(r.decision)}>{r.decision}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SessionDriftView() {
  const [sessions, setSessions] = useState<{ id: number; session_start: string; total_reviews: number; kill_rate: number; decisions: Record<string, number>; types_reviewed: Record<string, number> }[]>([]);
  const [drift, setDrift] = useState<{ sessions: number; drift_detected: boolean; kill_rate_trend?: { current: number; historical_avg: number; drift_magnitude: number; direction: string } } | null>(null);

  useEffect(() => {
    api.getSessions().then(r => setSessions(r.sessions));
    api.getReviewDrift().then(setDrift);
  }, []);

  if (sessions.length === 0) return null;

  return (
    <div className="border-t border-zinc-800/40 pt-8">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider text-zinc-500">Review Sessions</h3>
        {drift?.drift_detected && (
          <span className="text-[11px] px-2 py-0.5 bg-amber-50 text-amber-700 border border-amber-200 rounded">Drift detected</span>
        )}
      </div>
      {drift?.kill_rate_trend && (
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div>
            <span className="text-[11px] text-zinc-600 block">Current kill rate</span>
            <span className="text-[15px] text-zinc-300 tabular-nums">{(drift.kill_rate_trend.current * 100).toFixed(0)}%</span>
          </div>
          <div>
            <span className="text-[11px] text-zinc-600 block">Historical avg</span>
            <span className="text-[15px] text-zinc-400 tabular-nums">{(drift.kill_rate_trend.historical_avg * 100).toFixed(0)}%</span>
          </div>
          <div>
            <span className="text-[11px] text-zinc-600 block">Direction</span>
            <span className="text-[13px] text-zinc-500">{drift.kill_rate_trend.direction}</span>
          </div>
        </div>
      )}
      <div className="space-y-2">
        {sessions.map(s => (
          <div key={s.id} className="flex items-center justify-between text-[12px] py-2 border-b border-zinc-800/30">
            <span className="text-zinc-400">{s.session_start.slice(0, 10)}</span>
            <span className="text-zinc-300 tabular-nums">{s.total_reviews} reviews</span>
            <span className={`tabular-nums ${s.kill_rate > 0.5 ? 'text-red-500' : 'text-zinc-400'}`}>{(s.kill_rate * 100).toFixed(0)}% killed</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
