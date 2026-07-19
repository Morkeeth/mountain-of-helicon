import { useState, useEffect, useCallback, lazy, Suspense } from 'react';
import FocusReview from './components/FocusReview';
import { motion, AnimatePresence } from 'framer-motion';
import { api } from './api';
import type { Score, Connector, ProjectRollup, Consolidation, Finding, FindingsResponse } from './api';
import FindingsView from './components/FindingsView';

/* What loads before first paint (Jul 15).
   The review device is a phone and the thing it is opened for is the ruling
   queue, so the queue — FocusReview and FindingsView — is the only view that
   ships in the main chunk. Every other tab is a route the thumb has not asked
   for yet, so it arrives on demand behind the shared Suspense in <main>.
   Switching tabs fetches a chunk that is already warm from the same origin.

   This is not premature: EvalView alone dragged recharts (393K) into the main
   bundle for a tab nobody opens on a phone, and Graph3D's three.js (1MB) was
   already split this way for the same reason. The rule is simple — if it is not
   the queue, it is lazy. */
const CausalLens = lazy(() => import('./components/CausalLens'));
const Graph3D = lazy(() => import('./components/Graph3D').then(m => ({ default: m.Graph3D })));
const EvalView = lazy(() => import('./components/EvalView').then(m => ({ default: m.EvalView })));
const ConnectorStatus = lazy(() => import('./components/ConnectorStatus').then(m => ({ default: m.ConnectorStatus })));
const SkillsAudit = lazy(() => import('./components/SkillsAudit'));
const LogView = lazy(() => import('./components/LogView'));
const RunsView = lazy(() => import('./components/RunsView'));
const ExamView = lazy(() => import('./components/ExamView'));
const JudgeView = lazy(() => import('./components/JudgeView'));
const RouteView = lazy(() => import('./components/RouteView'));
const GoldView = lazy(() => import('./components/GoldView'));
const ConflictMap = lazy(() => import('./components/ConflictMap'));
const Focus = lazy(() => import('./components/Focus'));
const Landing = lazy(() => import('./components/Landing'));
const SetupReportCard = lazy(() => import('./components/SetupReportCard'));
const StoreAudit = lazy(() => import('./components/StoreAudit'));
const Reading = lazy(() => import('./components/Reading'));
const MemoryHealthTrend = lazy(() => import('./components/MemoryHealthTrend'));
const Volatility = lazy(() => import('./components/Volatility'));
const Consistency = lazy(() => import('./components/Consistency'));

/* Findings-first IA (Jul 3): HEALTH · FINDINGS · LOG primary,
   Graph · Projects secondary. Review and Insights are gone, findings
   carry their own actions, the log carries the receipts. */

type Tab = 'reading' | 'tour' | 'focus' | 'health' | 'findings' | 'exam' | 'judge' | 'gold' | 'log' | 'graph' | 'projects' | 'routines' | 'evals' | 'lens' | 'runs' | 'route';

// The primary nav IS the loop, review first: what needs your ruling, the exam
// that found it, the rules your rulings compile into, and the memory underneath.
// Everything else — narrative, next moves, thin-evidence reads (runs/route),
// and the deeper surfaces — lives under More, so the hero is the decision, not a
// menu of capabilities.
const PRIMARY_TABS: { key: Tab; label: string }[] = [
  { key: 'findings', label: 'Needs Ruling' },
  { key: 'exam', label: 'The Exam' },
  { key: 'gold', label: 'Golden Rules' },
  { key: 'health', label: 'Memory' },
];

const SECONDARY_TABS: { key: Tab; label: string }[] = [
  { key: 'reading', label: 'The Reading' },
  { key: 'focus', label: 'Next Moves' },
  { key: 'runs', label: 'Runs' },
  { key: 'route', label: 'Route' },
  { key: 'tour', label: 'Tour' },
  { key: 'routines', label: 'Routines & Skills' },
  { key: 'evals', label: 'Evals' },
  { key: 'judge', label: 'Qwen as Judge' },
  { key: 'lens', label: 'Causal Lens' },
  { key: 'log', label: 'Log' },
  { key: 'graph', label: 'Graph' },
  { key: 'projects', label: 'Projects' },
];

const ALL_TABS: Tab[] = [...PRIMARY_TABS, ...SECONDARY_TABS].map(t => t.key);

/* Phone shell (Jul 15). The review device is a phone, so the thumb, not the
   cursor, is the input. The 110px rail ate 28% of a 390px screen and pushed the
   document to 559px, so the page scrolled sideways before you could rule on
   anything. Below md the rail is replaced by a bottom bar carrying the audit
   loop (what needs you · the record · the memory · the law) with everything else
   behind More. Four plus More is what fits at a 44px target on a 390px screen;
   a scrolling tab strip would have hidden the queue behind a swipe, and a
   hamburger would have hidden it behind a tap. The rail is untouched at md+.

   Bar labels are shortened, not shrunk: "Needs Ruling" and "Golden Rules" both
   truncated to "NEEDS RULI…" / "GOLDEN RU…" in a 78px slot, and the fix is
   fewer words, not 8px type on the surface that carries the verdict. */
const BAR_TABS: { key: Tab; short: string }[] = [
  { key: 'findings', short: 'Ruling' },
  { key: 'reading', short: 'Reading' },
  { key: 'health', short: 'Memory' },
  { key: 'gold', short: 'Rules' },
];
const BAR_KEYS: Tab[] = BAR_TABS.map(t => t.key);

// Left-rail nav item (brand book: numbered, calm, active = ink + accent bar)
function RailItem({ n, label, active, badge = 0, onClick }: {
  n: number; label: string; active: boolean; badge?: number; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="group relative text-left rounded-lg px-2.5 py-2 transition-colors"
      style={{ background: active ? 'var(--helicon-accent-dim)' : 'transparent' }}
    >
      {active && (
        <span className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full" style={{ background: 'var(--helicon-accent)' }} />
      )}
      <span className="block text-[9px] tabular-nums mb-0.5" style={{ color: 'var(--helicon-faint)' }}>{n}</span>
      <span
        className="block text-[10px] uppercase leading-tight"
        style={{ letterSpacing: '0.08em', color: active ? 'var(--helicon-ink)' : 'var(--helicon-muted)', fontWeight: active ? 600 : 500 }}
      >
        {label}
      </span>
      {badge > 0 && (
        <span className="absolute top-2 right-2 text-[9px] tabular-nums" style={{ color: 'var(--helicon-accent)' }}>{badge}</span>
      )}
    </button>
  );
}

/* Bottom-bar item. Same voice as the rail: micro-caps label, accent bar on the
   active edge, so the phone reads as the same instrument, not a second app.
   Icons were never in this language (the rail numbers instead), and emoji-as-icon
   is banned, so the bar stays typographic. 56px tall clears the 44px target. */
function BarItem({ label, active, badge = 0, onClick }: {
  label: string; active: boolean; badge?: number; onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      aria-current={active ? 'page' : undefined}
      className="relative flex-1 min-w-0 flex flex-col items-center justify-center gap-0.5"
      style={{ minHeight: 56, background: active ? 'var(--helicon-accent-dim)' : 'transparent' }}
    >
      {active && (
        <span className="absolute top-0 left-1/2 -translate-x-1/2 h-[2px] w-7 rounded-full" style={{ background: 'var(--helicon-accent)' }} />
      )}
      <span
        className="block text-[9.5px] uppercase leading-tight text-center px-1 truncate max-w-full"
        style={{ letterSpacing: '0.07em', color: active ? 'var(--helicon-ink)' : 'var(--helicon-muted)', fontWeight: active ? 600 : 500 }}
      >
        {label}
      </span>
      {badge > 0 && (
        <span className="text-[10px] tabular-nums leading-none" style={{ color: 'var(--helicon-accent)', fontWeight: 600 }}>{badge}</span>
      )}
    </button>
  );
}

/* The rest of the nav. A sheet rather than a full page so ruling stays the thing
   you came back to; it dismisses on backdrop, Escape, or pick. */
function MoreSheet({ tab, onPick, onClose, needsYou }: {
  tab: Tab; onPick: (t: Tab) => void; onClose: () => void; needsYou: number;
}) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  const rest = PRIMARY_TABS.filter(t => !BAR_KEYS.includes(t.key));
  const row = (t: { key: Tab; label: string }, n: number) => (
    <button
      key={t.key}
      onClick={() => { onPick(t.key); onClose(); }}
      className="w-full flex items-center gap-3 px-5 text-left"
      style={{ minHeight: 48, background: tab === t.key ? 'var(--helicon-accent-dim)' : 'transparent' }}
    >
      <span className="text-[10px] tabular-nums w-4" style={{ color: 'var(--helicon-faint)' }}>{n}</span>
      <span
        className="text-[12px] uppercase"
        style={{ letterSpacing: '0.07em', color: tab === t.key ? 'var(--helicon-ink)' : 'var(--helicon-muted)', fontWeight: tab === t.key ? 600 : 500 }}
      >
        {t.label}
      </span>
      {t.key === 'findings' && needsYou > 0 && (
        <span className="ml-auto text-[11px] tabular-nums" style={{ color: 'var(--helicon-accent)' }}>{needsYou}</span>
      )}
    </button>
  );

  return (
    <div className="fixed inset-0 z-50 md:hidden" role="dialog" aria-modal="true" aria-label="All surfaces">
      <motion.div
        className="absolute inset-0" onClick={onClose}
        style={{ background: 'rgba(23,40,58,0.32)' }}
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}
      />
      <motion.div
        className="absolute left-0 right-0 bottom-0 rounded-t-[18px] overflow-hidden"
        style={{
          background: 'var(--helicon-panel)', borderTop: '1px solid var(--helicon-line)',
          boxShadow: 'var(--helicon-shadow)', paddingBottom: 'env(safe-area-inset-bottom)',
          maxHeight: '82vh',
        }}
        initial={{ y: '100%' }} animate={{ y: 0 }} exit={{ y: '100%' }}
        transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
      >
        <div className="flex justify-center pt-2.5 pb-1">
          <span className="h-1 w-9 rounded-full" style={{ background: 'var(--helicon-line-2)' }} />
        </div>
        <div className="overflow-y-auto pb-4" style={{ maxHeight: 'calc(82vh - 24px)' }}>
          {rest.map((t) => row(t, PRIMARY_TABS.findIndex(p => p.key === t.key) + 1))}
          {rest.length > 0 && <div className="my-2 mx-5 border-t" style={{ borderColor: 'var(--helicon-line)' }} />}
          {/* Derived, never hardcoded: these numbers ARE the keyboard shortcuts
              and must match the rail exactly. A literal `i + 8` here was correct
              only while PRIMARY_TABS had 7 entries, and silently drifted the
              moment one was added. */}
          {SECONDARY_TABS.map((t, i) => row(t, PRIMARY_TABS.length + i + 1))}
        </div>
      </motion.div>
    </div>
  );
}

function App() {
  // deep-linkable tabs: /#health jumps straight to a surface (demo + docs)
  const initialTab = (): Tab => {
    const h = window.location.hash.replace('#', '') as Tab;
    return ALL_TABS.includes(h) ? h : 'findings';
  };
  const [tab, setTab] = useState<Tab>(initialTab);
  const [score, setScore] = useState<Score | null>(null);
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [triageCount, setTriageCount] = useState(0);
  const [loading, setLoading] = useState(true);

  // Findings (the heart), owned here so the header attention bar shares it
  const [findingsData, setFindingsData] = useState<FindingsResponse | null>(null);
  const [batteryIncluded, setBatteryIncluded] = useState(false);
  const [batteryLoading, setBatteryLoading] = useState(false);
  const [reviewMode, setReviewMode] = useState<'focus' | 'all'>('focus');

  // Project-centric state (secondary surface, unchanged)
  const [projects, setProjects] = useState<ProjectRollup[]>([]);
  const [selectedProject, setSelectedProject] = useState<string | null>(null);
  const [projectConsolidations, setProjectConsolidations] = useState<Consolidation[]>([]);
  const [copied, setCopied] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);

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
    <div className="min-h-screen flex" style={{ background: 'var(--bg)' }}>
      {/* Atmosphere — a faint watercolor peak at the page foot (brand book:
          "use as atmosphere, not decoration"). pointer-events:none, imperceptibly
          low so it can never sit over or block content. */}
      <img
        src="/mountain-3.png" alt="" aria-hidden
        className="pointer-events-none select-none"
        style={{
          position: 'fixed', bottom: 0, right: 0, width: 'min(460px, 100vw)', maxWidth: '100vw', zIndex: 0, opacity: 0.05,
          WebkitMaskImage: 'linear-gradient(180deg, transparent, #000 70%)', maskImage: 'linear-gradient(180deg, transparent, #000 70%)',
        }}
      />
      {/* Left rail, brand book 88-120px numbered nav. Desktop/tablet only; the
          phone gets the bottom bar below. */}
      <nav className="hidden md:flex flex-none flex-col" style={{ width: 110, borderRight: '1px solid var(--helicon-line)' }}>
        <div className="px-5 pt-6 pb-5">
          <svg width="30" height="18" viewBox="0 0 44 26" fill="none" stroke="var(--helicon-ink)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true">
            <path d="M2.5 23 L14 5 L22 16.5" opacity="0.5" />
            <path d="M15 23 L27.5 4 L41.5 23" />
          </svg>
        </div>
        <div className="flex-1 flex flex-col gap-0.5 px-2.5">
          {PRIMARY_TABS.map((t, i) => (
            <RailItem key={t.key} n={i + 1} label={t.label} active={tab === t.key}
              badge={t.key === 'findings' ? (findingsData?.summary.needs_you || 0) : 0}
              onClick={() => setTab(t.key)} />
          ))}
          <div className="my-3 mx-2 border-t" style={{ borderColor: 'var(--helicon-line)' }} />
          {/* Numbered from the primary count, not a hardcoded offset: with 7
              primary tabs a literal +6 restarted the sequence at 6, so two tabs
              read 6 and two read 7, and every rail number past the divider
              disagreed with the keyboard shortcut that actually jumps there
              (shortcuts index ALL_TABS, i.e. primary then secondary). */}
          {SECONDARY_TABS.map((t, i) => (
            <RailItem key={t.key} n={PRIMARY_TABS.length + i + 1} label={t.label} active={tab === t.key}
              onClick={() => { setTab(t.key); if (t.key !== 'projects') setSelectedProject(null); }} />
          ))}
        </div>
        <div className="relative mt-2" style={{ height: 96, overflow: 'hidden' }}>
          <img src="/mountain-2.png" alt="" aria-hidden className="absolute bottom-0 left-0 w-full object-cover"
            style={{ height: 96, opacity: 0.85, WebkitMaskImage: 'linear-gradient(180deg, transparent, #000 62%)', maskImage: 'linear-gradient(180deg, transparent, #000 62%)' }} />
        </div>
      </nav>

      {/* Right column */}
      <div className="flex-1 min-w-0 flex flex-col">
      <header className="px-4 md:px-8 pt-4 md:pt-6 pb-3 md:pb-4" style={{ borderBottom: '1px solid var(--helicon-line)' }}>
        <div className="max-w-5xl mx-auto">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              {/* the mark rides the header on phones, where the rail that carried it is gone */}
              <svg width="22" height="13" viewBox="0 0 44 26" fill="none" stroke="var(--helicon-ink)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" className="md:hidden shrink-0">
                <path d="M2.5 23 L14 5 L22 16.5" opacity="0.5" />
                <path d="M15 23 L27.5 4 L41.5 23" />
              </svg>
              <h1
                className="text-[15px] md:text-[19px] tracking-tight text-zinc-100 whitespace-nowrap"
                style={{ fontFamily: 'var(--helicon-serif)', fontWeight: 300, textTransform: 'uppercase', letterSpacing: '0.04em', fontVariationSettings: "'opsz' 144" }}
              >
                Mount Helicon
              </h1>
              {/* tagline + badge are desktop furniture: on a phone they pushed the
                  header 169px past the viewport and shore the score clean off */}
              <span className="hidden lg:inline text-[10px] text-zinc-500 tracking-widest uppercase font-medium">Court of record for agent memory</span>
              <span
                className="hidden lg:inline text-[9px] px-2 py-0.5 rounded-full font-medium tracking-wide border"
                style={{ background: 'var(--helicon-accent-dim)', color: 'var(--helicon-accent)', borderColor: 'rgba(34,58,78, 0.25)' }}
              >
                Powered by Qwen
              </span>
            </div>
            <div className="flex items-center gap-2 md:gap-3 shrink-0">
              {/* Attention bar: live findings severity split, click-through to FINDINGS */}
              {/* the phone carries this count on the bottom bar already */}
              {findingsData && (criticalCount > 0 || warningCount > 0) && (
                <button
                  onClick={() => setTab('findings')}
                  className="hidden md:block text-[11px] tabular-nums transition-opacity hover:opacity-70"
                >
                  <span style={{ color: 'var(--helicon-accent)' }}>{criticalCount} critical</span>
                  <span className="text-zinc-700"> · </span>
                  <span style={{ color: 'var(--helicon-stale)' }}>{warningCount} warning</span>
                </button>
              )}
              {score && (
                <div className="flex items-center gap-1.5" title={`${score.reviewed} of ${score.total} memory items triaged, review coverage, not a health grade`}>
                  <div className="hidden sm:block w-16 h-1.5 rounded-full bg-zinc-800/60 overflow-hidden">
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
        </div>
      </header>

      {/* bottom padding clears the fixed bar (56px + safe area) so the last
          ruling in a queue is never parked under it */}
      <main className="w-full max-w-5xl mx-auto px-4 md:px-8 py-5 md:py-6 pb-[calc(72px+env(safe-area-inset-bottom))] md:pb-6">
        <AnimatePresence mode="wait">
        <motion.div
          key={tab + (selectedProject || '')}
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        >
        {/* One boundary for every lazy tab. The fallback is empty height rather
            than a spinner: the chunk lands in a blink on a warm origin, and a
            flashing spinner would be louder than the wait it describes. */}
        <Suspense fallback={<div className="py-12" />}>

        {tab === 'exam' && <ExamView onGoToFindings={() => setTab('findings')} />}
        {tab === 'judge' && <JudgeView />}

        {tab === 'reading' && <Reading />}
        {tab === 'runs' && <RunsView />}
        {tab === 'route' && <RouteView />}
        {tab === 'lens' && <CausalLens />}

        {tab === 'tour' && <Landing onEnter={() => setTab('focus')} />}

        {tab === 'focus' && <Focus />}

        {tab === 'health' && (
          <MemoryTab
            score={score}
            connectors={connectors}
            needsYou={findingsData?.summary?.needs_you ?? 0}
            onReview={() => setTab('findings')}
          />
        )}

        {tab === 'findings' && reviewMode === 'focus' && (
          <>
          <TabPurpose>One ruling at a time. Handle what needs you; the rest is auto-managed.</TabPurpose>
          <FocusReview
            data={findingsData}
            onActed={handleFindingActed}
            onSeeAll={() => setReviewMode('all')}
          />
          </>
        )}
        {tab === 'findings' && reviewMode === 'all' && (
          <>
          <button onClick={() => setReviewMode('focus')} className="text-[12px] mb-3 transition-colors hover:opacity-70" style={{ color: 'var(--helicon-accent)' }}>← back to focus</button>
          <TabPurpose>What Helicon caught in your memory, drift, staleness, and things worth sharpening. You rule once; it sticks.</TabPurpose>
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
          <TabPurpose>Your agent's operating law. Every rule here you ruled true, and each carries its receipt, this is what your agent should already know, kept in sync as your memory changes. Not a doc you paste; infrastructure it obeys.</TabPurpose>
          <GoldView />
          </>
        )}

        {tab === 'routines' && (
          <>
          <TabPurpose>The stack around your memory, the routines that feed it and the skills your agent loads. Silent crons and duplicate skills surface here.</TabPurpose>
          <SkillsAudit />
          </>
        )}

        {tab === 'evals' && (
          <>
          <TabPurpose>Talk to your agent, test what a task retrieves, run the battery, then transfer the compiled context into your next session.</TabPurpose>
          <EvalView />
          </>
        )}

          {tab === 'log' && (
          <>
          <TabPurpose>What Helicon did and what you decided, every action is a receipt.</TabPurpose>
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
          <TabPurpose>Compiled knowledge per project, copy it into your agent's context.</TabPurpose>
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

        </Suspense>
        </motion.div>
        </AnimatePresence>
      </main>
      </div>

      {/* Phone nav: the audit loop under the thumb, everything else behind More */}
      <nav
        className="md:hidden fixed bottom-0 left-0 right-0 z-40 flex items-stretch"
        style={{
          background: 'var(--helicon-panel)',
          borderTop: '1px solid var(--helicon-line)',
          boxShadow: '0 -6px 24px rgba(23,40,58,0.06)',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}
      >
        {BAR_TABS.map(t => (
          <BarItem
            key={t.key}
            label={t.short}
            active={tab === t.key && !moreOpen}
            badge={t.key === 'findings' ? (findingsData?.summary.needs_you || 0) : 0}
            onClick={() => { setTab(t.key); setMoreOpen(false); }}
          />
        ))}
        <BarItem
          label="More"
          active={moreOpen || !BAR_KEYS.includes(tab)}
          onClick={() => setMoreOpen(o => !o)}
        />
      </nav>
      <AnimatePresence>
        {moreOpen && (
          <MoreSheet
            tab={tab}
            needsYou={findingsData?.summary.needs_you || 0}
            onPick={t => { setTab(t); if (t !== 'projects') setSelectedProject(null); }}
            onClose={() => setMoreOpen(false)}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

// One muted line under each tab's top bar stating what the screen is for.
function TabPurpose({ children }: { children: React.ReactNode }) {
  return <p className="text-[12px] text-zinc-600 mb-5 leading-relaxed">{children}</p>;
}


// ============================================================
// Memory tab: the record's health, with its truth gates as sub-views
// ============================================================

/* Volatility and Consistency are gates ON the memory, not separate journeys, so
   they live here under a local segmented sub-nav rather than in the top bar. */
function MemoryTab({ score, connectors, needsYou, onReview }: {
  score: Score | null;
  connectors: Connector[];
  needsYou: number;
  onReview: () => void;
}) {
  const SUBS: { key: 'health' | 'volatility' | 'consistency'; label: string }[] = [
    { key: 'health', label: 'Health' },
    { key: 'volatility', label: 'Volatility' },
    { key: 'consistency', label: 'Consistency' },
  ];
  const [sub, setSub] = useState<'health' | 'volatility' | 'consistency'>('health');

  return (
    <div>
      <nav className="flex items-stretch gap-0 border-b border-zinc-800/60 mb-8">
        {SUBS.map(s => (
          <button
            key={s.key}
            onClick={() => setSub(s.key)}
            className={`px-4 py-2 text-[11px] uppercase tracking-[0.14em] relative transition-colors ${
              sub === s.key ? 'text-zinc-200' : 'text-zinc-500 hover:text-zinc-400'
            }`}
          >
            {s.label}
            {sub === s.key && (
              <span className="absolute bottom-[-1px] left-3 right-3 h-[2px] rounded-full" style={{ background: 'var(--helicon-accent)' }} />
            )}
          </button>
        ))}
      </nav>

      {sub === 'health' && (
        <div className="space-y-10">
          <ContextHero score={score} needsYou={needsYou} onReview={onReview} />

          <MemoryHealthTrend />

          <SetupReportCard />

          <StoreAudit />

          <div className="border-t border-zinc-800/40 pt-8">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
              <div>
                <h3 className="text-[11px] uppercase tracking-wider text-zinc-500 mb-4">Review coverage by source</h3>
                {score && (
                  <div className="space-y-3.5">
                    {Object.entries(score.by_source).map(([src, data]) => (
                      <div key={src} className="grid items-center gap-4" style={{ gridTemplateColumns: '128px 64px 1fr 40px' }}>
                        <span className="text-[13px]" style={{ color: 'var(--helicon-ink)' }}>{src}</span>
                        <span className="text-[11px] tabular-nums text-right" style={{ color: 'var(--helicon-muted)' }}>{data.reviewed}/{data.total}</span>
                        <span className="relative h-[5px] rounded-full overflow-hidden" style={{ background: 'rgba(46,58,71,0.09)' }}>
                          <span
                            className="absolute left-0 top-0 h-full rounded-full"
                            style={{ width: `${Math.min(100, data.score)}%`, background: data.score >= 100 ? 'var(--helicon-conflict)' : 'var(--helicon-ink)', opacity: 0.55, transition: 'width .8s cubic-bezier(0.16,1,0.3,1)' }}
                          />
                        </span>
                        <span className="text-[13px] tabular-nums text-right" style={{ color: 'var(--helicon-ink)' }}>{data.score}%</span>
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

      {sub === 'volatility' && <Volatility />}

      {sub === 'consistency' && <Consistency />}
    </div>
  );
}

// ============================================================
// Helicon Score strip (HEALTH tab)
// ============================================================

/* The front door. States the promise, the loop, and the two honest numbers:
   what needs a human ruling now (the alarm, terracotta) and how much of the
   memory has been triaged (coverage, deliberately NOT framed as a health grade,
   because it is just reviewed/total). Daily-use framing kills the "do I live
   in this dashboard?" question up front. */
function ContextHero({ score, needsYou, onReview }: { score: Score | null; needsYou: number; onReview: () => void }) {
  const coverage = score?.score ?? 0;
  const reviewed = score?.reviewed ?? 0;
  const total = score?.total ?? 0;
  const step = (label: string) => <b style={{ color: 'var(--helicon-ink)', fontWeight: 600 }}>{label}</b>;

  return (
    <div className="relative overflow-hidden rounded-2xl bg-white shadow-sm border border-zinc-800/50 px-7 py-6">
      <img
        src="/mountain.png"
        alt=""
        aria-hidden
        className="absolute right-0 top-0 h-full w-[48%] object-cover pointer-events-none select-none"
        style={{
          objectPosition: 'center 42%',
          WebkitMaskImage: 'linear-gradient(90deg, transparent 0%, #000 46%)',
          maskImage: 'linear-gradient(90deg, transparent 0%, #000 46%)',
          animation: 'heliconMist 32s ease-in-out infinite',
        }}
      />
      <div className="relative" style={{ maxWidth: '58%' }}>
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
            reviewed <span style={{ opacity: 0.75 }}>({reviewed.toLocaleString()} of {total.toLocaleString()} triaged, coverage, not a health grade)</span>
          </span>
        </div>
      </div>

      <p className="mt-5 text-[11px]" style={{ color: 'var(--helicon-muted)' }}>
        Helicon runs on a timer and pings you when something needs a call. You don't live here, you drop in when it does.
      </p>
      </div>
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
      {/* Stats bar. Wraps: four stat groups plus Refresh in one unwrapping row
          pushed the button to x=427 on a 390px screen, where the page guard
          clipped it and the only way to refresh went off the side of the phone. */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-4 md:gap-5 flex-wrap">
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
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
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
