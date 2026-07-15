const BASE = '/api';

// When the server sets HELICON_PASSWORD, pass it via ?token=... once; it is
// kept in localStorage and sent as a Bearer header on every call.
const urlToken = new URLSearchParams(window.location.search).get('token');
if (urlToken) localStorage.setItem('helicon_token', urlToken);

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('helicon_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// A few components call fetch('/api/...') directly; patch the global so every
// API call carries the token without touching each call site.
const rawFetch = window.fetch.bind(window);
window.fetch = (input, init) => {
  const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
  if (url.startsWith('/api')) {
    init = { ...init, headers: { ...authHeaders(), ...(init?.headers || {}) } };
  }
  return rawFetch(input, init);
};

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface Cube {
  id: string;
  source: string;
  type: string;
  title: string;
  content: string;
  confidence: number;
  review_status: string;
  created_at: string;
  tags: string[];
  review_count: number;
  spin_count: number;
}

export interface Score {
  score: number;
  total: number;
  reviewed: number;
  pending: number;
  by_source: Record<string, { total: number; reviewed: number; score: number }>;
  by_type: Record<string, { total: number; reviewed: number; score: number }>;
}

export interface AuditFinding {
  id: number;
  audit_type: string;
  finding: string;
  severity: string;
  proposed_action: string;
  target_id: string;
  human_decision: string | null;
  details?: {
    age_days?: number;
    matched_phrases?: string[];
    cube_type?: string;
    source?: string;
    confidence?: number;
  };
}

export interface Pattern {
  id: string;
  name: string;
  description: string;
  pattern_type: string;
  data_points: number;
  confidence: number;
}

export interface DecayStats {
  [type: string]: {
    avg_confidence: number;
    min_confidence: number;
    count: number;
  };
}

export interface Connector {
  name: string;
  enabled: boolean;
  cube_count: number;
}

export interface GraphNode {
  id: string;
  label: string;
  kind: 'entity' | 'cube';
  type: string;
  size: number;
  confidence?: number;
  review_status?: string;
  source?: string;
}

export interface GraphLink {
  source: string;
  target: string;
  relation: string;
  weight: number;
}

export interface GraphData {
  nodes: GraphNode[];
  links: GraphLink[];
}

// One row of the unified FINDINGS surface (/api/findings)
export interface Finding {
  id: string;                 // "audit-262" | "skill-thin-x" | "battery-0"
  kind: string;               // temporal | decay | factual | logical | skill | battery
  severity: string;           // critical | warning | info
  title: string;
  why: string;                // the human sentence — this IS the finding
  evidence_preview: string;
  source: string;
  source_ref: string;
  cube_id: string | null;
  suggested_action: string;   // kill_stale | fix_skill | reconcile | review
  created_at: string;
  lane: string;               // decision (needs your ruling) | ambient (age/mechanics)
}

export interface FindingsSummary {
  total: number;
  needs_you: number;          // decision-lane count — the real daily queue
  ambient: number;            // age/mechanics, auto-manageable
  by_kind: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface FindingsResponse {
  findings: Finding[];
  summary: FindingsSummary;
}

// One receipt of the LOG surface (/api/log)
export interface LogEntry {
  ts: string;
  actor: string;              // human | helicon | qwen
  action: string;
  detail: string;
  count?: number;
}

export interface Consolidation {
  id: string;
  title: string;
  summary: string;
  cube_ids: string[];
  cube_count: number;
  created_at: string;
  confidence: number;
  topic: string;
}

export interface Cluster {
  topic: string;
  method: string;
  count: number;
  cubes: { id: string; title: string; type: string; source: string; confidence: number }[];
}

export const api = {
  getCubes: (params?: { status?: string; source?: string; type?: string; sort?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params) Object.entries(params).forEach(([k, v]) => { if (v !== undefined) qs.set(k, String(v)); });
    return get<{ cubes: Cube[]; total: number }>(`/cubes?${qs}`);
  },
  getScore: () => get<Score>('/score'),
  submitReview: (cube_id: string, decision: string, notes: string, time_to_review_seconds: number) =>
    post<{ review_id: number }>('/review', { cube_id, decision, notes, time_to_review_seconds }),
  getAudit: (pending_only = true) =>
    get<{ findings: AuditFinding[] }>(`/audit?pending_only=${pending_only}`),
  runAudit: () => post<{ total_findings: number }>('/audit/run'),
  /* `notes` is the reason a dismissal carries, and it is the whole difference
     between a ruling that compiles into GOLDEN_RULES and one that closes
     quietly: the server answers `precedent: true` only when a reason made law.
     Typed so callers can read that answer instead of assuming it. */
  confirmAudit: <T = { finding_id: number; decision: string; precedent?: boolean }>(
    finding_id: number, decision: string, notes?: string,
  ) => post<T>('/audit/confirm', { finding_id, decision, notes }),
  resolveIdentity: (finding_id: number, canonical: string) =>
    post('/audit/resolve-identity', { finding_id, canonical }),
  resolveRelation: (finding_id: number, verdict: string) =>
    post('/audit/resolve-relation', { finding_id, verdict }),
  getPatterns: () => get<{ patterns: Pattern[] }>('/patterns'),
  extractPatterns: () => post<{ extracted: number }>('/patterns/extract'),
  getDecayStats: () => get<DecayStats>('/decay/stats'),
  runDecay: () => post('/decay'),
  getConnectors: () => get<{ connectors: Connector[] }>('/connectors'),
  triggerScan: () => post('/scan'),
  getReviews: (limit = 20) => get<{ reviews: { id: number; cube_id: string; decision: string; notes: string; cube_type: string; cube_source: string; reviewed_at: string; time_to_review_seconds: number }[] }>(`/reviews?limit=${limit}`),
  getTimeline: () => get<{
    ingestion: { day: string; added: number; avg_conf: number; source: string }[];
    reviews: { day: string; decision: string; count: number }[];
  }>('/timeline'),
  getReport: () => get<{
    stats: Record<string, unknown>;
    report: string | null;
  }>('/report'),
  search: (q: string, limit = 30) => get<{ results: Cube[]; total: number; query: string }>(`/search?q=${encodeURIComponent(q)}&limit=${limit}`),
  getGraph: () => get<GraphData>('/graph'),
  buildGraph: (useQwen = false) => post<{ entities: number; cubes_processed: number; edges: number }>(`/graph/build?use_qwen=${useQwen}`),
  getEntityDetail: (id: string) => get<{ entity: Record<string, unknown>; cubes: Cube[]; related_entities: { target_id: string; name: string; entity_type: string }[] }>(`/graph/entity/${id}`),
  getConsolidations: () => get<{ consolidations: Consolidation[] }>('/consolidations'),
  getClusters: () => get<{ clusters: Cluster[] }>('/consolidations/clusters'),
  runConsolidation: (useQwen = false, maxClusters = 10) => post<{ clusters_found: number; consolidated: number; results: Consolidation[] }>(`/consolidations/run?use_qwen=${useQwen}&max_clusters=${maxClusters}`),
  getQwenStats: () => get<QwenStats>('/qwen/stats'),
  getQwenModels: () => get<QwenModels>('/qwen/models'),
  getQwenCache: () => get<QwenCache>('/qwen/cache'),
  getQwenRouting: () => get<QwenRouting>('/qwen/routing'),
  getSessions: (limit = 10) => get<{ sessions: SessionSummary[] }>(`/sessions?limit=${limit}`),
  getReviewDrift: () => get<ReviewDrift>('/sessions/drift'),
  summarizeSession: () => post<{ status: string; summary?: SessionSummary }>('/sessions/summarize'),
  runTriage: (dryRun = false) => post<TriageResult>(`/triage/run?dry_run=${dryRun}`),
  getTriageStats: () => get<TriageStats>('/triage/stats'),
  getTriageRules: () => get<{ rules: TriageRule[]; total: number }>('/triage/rules'),
  getProjects: () => get<{ projects: ProjectRollup[] }>('/projects'),
  getProjectRecommendations: () => get<{ recommendations: ProjectRecommendation[]; weekly: WeeklySummary }>('/projects/recommend'),
  getContextSwitches: (weeks = 4) => get<ContextSwitchData>(`/projects/context-switches?weeks=${weeks}`),
  getBattery: () => get<BatteryReport>('/integrity/battery'),
  getBatteryHistory: () => get<BatteryHistory>('/integrity/history'),
  getSnapshots: () => get<SnapshotReport>('/integrity/snapshots'),
  getSkillsAudit: () => get<SkillsAudit>('/integrity/skills'),
  runEval: () => post<EvalResult>('/eval/run'),
  getEvalHistory: () => get<{ runs: EvalRun[] }>('/eval/history'),
  getScoreHistory: () => get<{ history: ScoreHistoryPoint[] }>('/score/history'),
  getFindings: (params?: { kind?: string; limit?: number; include?: string }) => {
    const qs = new URLSearchParams();
    if (params?.kind) qs.set('kind', params.kind);
    qs.set('limit', String(params?.limit ?? 500));
    if (params?.include) qs.set('include', params.include);
    return get<FindingsResponse>(`/findings?${qs}`);
  },
  getLog: (limit = 100) => get<{ entries: LogEntry[]; total: number }>(`/log?limit=${limit}`),
  backfillScoreHistory: () => post<{ status: string; points: number }>('/score/history/backfill'),
};

export interface BatteryTestResult {
  name: string;
  status: 'PASS' | 'FAIL';
  reason: string;
  critical: boolean;
}

export interface BatteryTask {
  task: string;
  verdict: 'HEALTHY' | 'DEGRADED' | 'BROKEN';
  results: BatteryTestResult[];
  retrieved: string[];
}

export interface BatteryReport {
  top_k: number;
  total: number;
  summary: { healthy: number; degraded: number; broken: number };
  tasks: BatteryTask[];
}

export interface BatteryHistoryPoint {
  recorded_at: string;
  total: number;
  healthy: number;
  degraded: number;
  broken: number;
  mean_tokens: number;
  source: string;
  healthy_share: number | null;
}

export interface BatteryHistory {
  points: BatteryHistoryPoint[];
  total: number;
}

export interface SnapshotResult {
  snapshot_id: number;
  task: string;
  regressed: boolean;
  overlap: number;
  dropped: string[];
  added: string[];
  reordered: boolean;
  stale: [string, string][];
  new_titles: string[];
}

export interface SnapshotReport {
  total: number;
  regressed: number;
  clean: number;
  snapshots: SnapshotResult[];
}

export interface SkillsAudit {
  roots: string[];
  files: number;
  unique: number;
  duplicates: { name: string; count: number; paths: string[] }[];
  collisions: { a: string; b: string; overlap: number }[];
  thin: { name: string; desc_len: number }[];
  summary: { duplicated: number; collisions: number; thin: number };
}

export interface QwenStats {
  total_calls: number;
  by_model: Record<string, { calls: number; cached_calls: number; input_tokens: number; output_tokens: number; avg_latency: number; cost_usd: number }>;
  cache: { hits: number; misses: number; rate?: number; entries?: number };
  total_cost_usd: number;
}

export interface QwenModels {
  routing: Record<string, string>;
  cost_per_1k_tokens: Record<string, number>;
  usage: Record<string, string>;
}

export interface QwenCache {
  cached_responses: number;
  tokens_saved_on_hits: number;
  by_model: Record<string, { cached: number; tokens: number }>;
  by_operation: Record<string, number>;
}

export interface SessionSummary {
  id: number;
  session_start: string;
  session_end: string;
  total_reviews: number;
  kill_rate: number;
  decisions: Record<string, number>;
  types_reviewed: Record<string, number>;
  sources_reviewed: Record<string, number>;
  insights: Record<string, string>;
}

export interface ReviewDrift {
  sessions: number;
  drift_detected: boolean;
  kill_rate_trend?: { current: number; historical_avg: number; drift_magnitude: number; direction: string };
  type_evolution?: { new_types_reviewed: string[]; dropped_types: string[] };
  session_history?: { date: string; reviews: number; kill_rate: number }[];
}

export interface QwenRouting {
  operations: Record<string, { calls: number; models_used: Record<string, number>; avg_latency: number; total_cost: number; total_tokens: number }>;
  recommendations: { operation: string; current_model: string; suggested: string; reason: string; estimated_savings_usd: number }[];
}

export interface TriageAction {
  cube_id: string;
  title: string;
  type: string;
  confidence: number;
  source: string;
  action: string;
  reason: string;
  rule_confidence: number;
}

export interface TriageResult {
  triaged: number;
  rules_applied: number;
  dry_run: boolean;
  actions: TriageAction[];
  rules: TriageRule[];
}

export interface TriageRule {
  action: string;
  condition: string;
  cube_type: string;
  confidence_threshold: number;
  rule_confidence: number;
  evidence: string;
}

export interface TriageStats {
  total_triaged: number;
  by_action: Record<string, number>;
  avg_rule_confidence: number;
  recent: { cube_id: string; action: string; reason: string; rule_confidence: number; triaged_at: string }[];
}

export interface ProjectRollup {
  name: string;
  cube_count: number;
  session_count: number;
  ship_rate: number;
  shipped: number;
  killed: number;
  revised: number;
  pending: number;
  spin_score: number;
  days_since_output: number | null;
  avg_confidence: number;
  decay_velocity: number;
  sources: string[];
  types: Record<string, number>;
}

export interface ProjectRecommendation {
  name: string;
  score: number;
  action: string;
  reasons: string[];
  cube_count: number;
  ship_rate: number;
  spin_score: number;
  days_since_output: number | null;
  pending: number;
  avg_confidence: number;
}

export interface WeeklySummary {
  touched: string[];
  touched_count: number;
  shipped_from: string[];
  shipped_count: number;
  week_start: string;
}

export interface ContextSwitchData {
  weeks_analyzed: number;
  avg_switch_index: number;
  weekly: {
    week: string;
    sessions: number;
    multi_project_sessions: number;
    zero_ship_multi: number;
    projects_touched: number;
    switch_index: number;
  }[];
  flagged_sessions: {
    session_id: string;
    project_tags: string[];
    cube_count: number;
    approved: number;
  }[];
}

export interface EvalResult {
  composite_score: number;
  retrieval: {
    precision_at_3: number;
    precision_at_5: number;
    mrr: number;
    query_count: number;
    details: { query: string; expected: string; found_at_rank: number | null; top_3_titles?: string[] }[];
  };
  forgetting: {
    forgetting_accuracy: number;
    total_reviewed: number;
    correct_predictions: number;
    killed_with_low_conf: number;
    killed_total: number;
    approved_with_ok_conf: number;
    approved_total: number;
  };
  audit: {
    audit_recall: number;
    total_findings: number;
    human_confirmed: number;
    stale_cubes_found: number;
    stale_cubes_actual: number;
  };
}

export interface EvalRun {
  id: number;
  run_at: string;
  precision_at_3: number;
  precision_at_5: number;
  mrr: number;
  forgetting_accuracy: number;
  audit_recall: number;
  query_count: number;
}

export interface ScoreHistoryPoint {
  id: number;
  recorded_at: string;
  score: number;
  total: number;
  reviewed: number;
  event_label: string | null;
}
