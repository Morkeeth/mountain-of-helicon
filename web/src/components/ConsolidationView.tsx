import { useState, useEffect } from 'react';
import { api } from '../api';
import type { Consolidation, Cluster } from '../api';

export function ConsolidationView() {
  const [consolidations, setConsolidations] = useState<Consolidation[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [running, setRunning] = useState(false);
  const [tab, setTab] = useState<'consolidated' | 'clusters'>('clusters');

  useEffect(() => {
    Promise.all([
      api.getConsolidations().then(r => setConsolidations(r.consolidations)),
      api.getClusters().then(r => setClusters(r.clusters)),
    ]);
  }, []);

  const runConsolidation = async () => {
    setRunning(true);
    const result = await api.runConsolidation(true, 10);
    setConsolidations(prev => [...result.results.map(r => ({
      id: r.id ?? '',
      title: r.title ?? '',
      summary: r.summary ?? '',
      cube_ids: [],
      cube_count: r.cube_count ?? 0,
      created_at: new Date().toISOString(),
      confidence: r.confidence ?? 0.5,
      topic: '',
    })), ...prev]);
    setRunning(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[15px] font-medium text-zinc-200">Memory Consolidation</h2>
          <span className="text-[11px] text-zinc-600">neuroscience-inspired "sleep" cycles</span>
        </div>
        <button
          onClick={runConsolidation}
          disabled={running}
          className="text-[12px] px-3 py-1.5 rounded-md border border-violet-200 text-violet-600 hover:bg-violet-50 transition-colors disabled:opacity-30 shadow-sm bg-white"
        >
          {running ? 'Consolidating...' : 'Run Sleep Cycle'}
        </button>
      </div>

      <div className="flex gap-1 mb-6">
        <button
          onClick={() => setTab('clusters')}
          className={`px-3 py-1.5 text-[12px] rounded-md transition-colors ${tab === 'clusters' ? 'bg-violet-50 text-violet-600 border border-violet-200' : 'text-zinc-500 hover:text-zinc-400'}`}
        >
          Clusters ({clusters.length})
        </button>
        <button
          onClick={() => setTab('consolidated')}
          className={`px-3 py-1.5 text-[12px] rounded-md transition-colors ${tab === 'consolidated' ? 'bg-violet-50 text-violet-600 border border-violet-200' : 'text-zinc-500 hover:text-zinc-400'}`}
        >
          Consolidated ({consolidations.length})
        </button>
      </div>

      {tab === 'clusters' && (
        <div className="space-y-1">
          {clusters.length === 0 ? (
            <p className="text-zinc-600 text-sm py-10 text-center">No clusters detected.</p>
          ) : (
            clusters.slice(0, 20).map((c, i) => (
              <ClusterRow key={i} cluster={c} />
            ))
          )}
        </div>
      )}

      {tab === 'consolidated' && (
        <div className="space-y-1">
          {consolidations.length === 0 ? (
            <div className="py-10 text-center">
              <p className="text-zinc-600 text-sm mb-1">No consolidations yet.</p>
              <p className="text-zinc-700 text-[12px]">Run a sleep cycle to merge related cubes into consolidated memories.</p>
            </div>
          ) : (
            consolidations.map(c => (
              <ConsolidationRow key={c.id} consolidation={c} />
            ))
          )}
        </div>
      )}
    </div>
  );
}

function ClusterRow({ cluster }: { cluster: Cluster }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="py-3 border-b border-zinc-800/30">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
        <div className="flex items-baseline justify-between">
          <div className="flex items-center gap-2">
            <span className="text-[13px] text-zinc-300">{cluster.topic}</span>
            <span className="text-[11px] text-zinc-700">{cluster.method.replace('_', ' ')}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-[12px] tabular-nums text-zinc-500">{cluster.count} cubes</span>
            <span className="text-[11px] text-zinc-700">{expanded ? '-' : '+'}</span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 ml-4 space-y-1.5 animate-fade-in">
          {cluster.cubes.slice(0, 10).map(c => (
            <div key={c.id} className="flex items-baseline justify-between text-[12px]">
              <div className="flex items-center gap-2 truncate max-w-[400px]">
                <span className="text-zinc-700">{c.source}</span>
                <span className="text-zinc-500">{c.title}</span>
              </div>
              <span className={`tabular-nums ${c.confidence < 0.1 ? 'text-red-500' : c.confidence < 0.3 ? 'text-amber-600' : 'text-zinc-500'}`}>
                {(c.confidence * 100).toFixed(0)}%
              </span>
            </div>
          ))}
          {cluster.count > 10 && (
            <p className="text-[11px] text-zinc-700">...and {cluster.count - 10} more</p>
          )}
        </div>
      )}
    </div>
  );
}

function ConsolidationRow({ consolidation }: { consolidation: Consolidation }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="py-3 border-b border-zinc-800/30">
      <button onClick={() => setExpanded(!expanded)} className="w-full text-left">
        <div className="flex items-baseline justify-between">
          <span className="text-[13px] text-zinc-300">{consolidation.title}</span>
          <div className="flex items-center gap-3">
            <span className="text-[12px] tabular-nums text-zinc-600">{consolidation.cube_count} cubes merged</span>
            <span className={`text-[12px] tabular-nums ${consolidation.confidence < 0.3 ? 'text-amber-600' : 'text-zinc-500'}`}>
              {(consolidation.confidence * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-3 animate-fade-in">
          <p className="text-[12px] text-zinc-500 leading-relaxed">{consolidation.summary}</p>
        </div>
      )}
    </div>
  );
}
