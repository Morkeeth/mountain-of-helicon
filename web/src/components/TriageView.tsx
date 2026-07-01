import { useState, useEffect } from 'react';
import { api } from '../api';
import type { TriageRule, TriageAction, TriageStats } from '../api';

export function TriageView({ onTriaged }: { onTriaged?: () => void }) {
  const [rules, setRules] = useState<TriageRule[]>([]);
  const [stats, setStats] = useState<TriageStats | null>(null);
  const [preview, setPreview] = useState<TriageAction[] | null>(null);
  const [running, setRunning] = useState(false);
  const [lastResult, setLastResult] = useState<{ triaged: number; actions: TriageAction[] } | null>(null);

  useEffect(() => {
    api.getTriageRules().then(r => setRules(r.rules));
    api.getTriageStats().then(setStats);
  }, []);

  const handlePreview = async () => {
    setRunning(true);
    const result = await api.runTriage(true);
    setPreview(result.actions);
    setRunning(false);
  };

  const handleExecute = async () => {
    setRunning(true);
    const result = await api.runTriage(false);
    setLastResult({ triaged: result.triaged, actions: result.actions });
    setPreview(null);
    api.getTriageStats().then(setStats);
    onTriaged?.();
    setRunning(false);
  };

  return (
    <div className="space-y-8">
      <div>
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-[15px] font-medium text-zinc-200">Auto-Triage</h2>
            <p className="text-[12px] text-zinc-600 mt-1">GLAZE makes its own decisions based on your review history</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handlePreview}
              disabled={running}
              className="text-[12px] px-3 py-1.5 rounded-md border border-zinc-800/60 text-zinc-500 hover:bg-zinc-800/30 transition-colors disabled:opacity-30"
            >
              {running ? 'Working...' : 'Preview'}
            </button>
            <button
              onClick={handleExecute}
              disabled={running || (preview !== null && preview.length === 0)}
              className="text-[12px] px-3 py-1.5 rounded-md border border-violet-200 text-violet-600 hover:bg-violet-50 transition-colors disabled:opacity-30 shadow-sm bg-white"
            >
              Execute
            </button>
          </div>
        </div>

        {lastResult && (
          <div className="mb-6 px-4 py-3 bg-emerald-50 border border-emerald-200 rounded-lg animate-fade-in">
            <span className="text-[13px] text-emerald-700">{lastResult.triaged} items auto-triaged</span>
            {lastResult.actions.length > 0 && (
              <div className="mt-2 space-y-1">
                {lastResult.actions.slice(0, 5).map(a => (
                  <div key={a.cube_id} className="flex items-center gap-2 text-[11px]">
                    <span className={a.action === 'kill' ? 'text-red-600' : 'text-emerald-600'}>
                      {a.action}
                    </span>
                    <span className="text-zinc-600 truncate">{a.title}</span>
                  </div>
                ))}
                {lastResult.actions.length > 5 && (
                  <span className="text-[11px] text-zinc-700">+{lastResult.actions.length - 5} more</span>
                )}
              </div>
            )}
          </div>
        )}

        {stats && stats.total_triaged > 0 && (
          <div className="grid grid-cols-3 gap-4 mb-8">
            <div>
              <span className="text-[11px] text-zinc-700 block">Total triaged</span>
              <span className="text-xl font-light text-zinc-200 tabular-nums">{stats.total_triaged}</span>
            </div>
            <div>
              <span className="text-[11px] text-zinc-700 block">Avg confidence</span>
              <span className="text-xl font-light text-zinc-300 tabular-nums">{(stats.avg_rule_confidence * 100).toFixed(0)}%</span>
            </div>
            <div>
              <span className="text-[11px] text-zinc-700 block">Actions</span>
              <div className="flex gap-2 mt-1">
                {Object.entries(stats.by_action).map(([action, count]) => (
                  <span key={action} className={`text-[12px] tabular-nums ${action === 'kill' ? 'text-red-600' : 'text-emerald-600'}`}>
                    {action}: {count}
                  </span>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {preview && (
        <div className="animate-fade-in">
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">
            Preview ({preview.length} items)
          </h3>
          {preview.length === 0 ? (
            <p className="text-[12px] text-zinc-700 py-4">No items match current triage rules. Need more review history.</p>
          ) : (
            <div className="space-y-1">
              {preview.map(a => (
                <div key={a.cube_id} className="py-2.5 border-b border-zinc-800/20 flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className={`text-[11px] px-1.5 py-0.5 rounded ${
                        a.action === 'kill'
                          ? 'bg-red-50 text-red-600'
                          : 'bg-emerald-50 text-emerald-600'
                      }`}>
                        {a.action}
                      </span>
                      <span className="text-[11px] text-zinc-700">{a.type}</span>
                      <span className="text-[11px] text-zinc-800">{a.source}</span>
                    </div>
                    <p className="text-[12px] text-zinc-400 truncate">{a.title}</p>
                    <p className="text-[11px] text-zinc-700 mt-0.5">{a.reason}</p>
                  </div>
                  <span className="text-[11px] text-zinc-600 tabular-nums shrink-0">
                    {(a.confidence * 100).toFixed(0)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="border-t border-zinc-800/40 pt-6">
        <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Active Rules</h3>
        {rules.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-[12px] text-zinc-700">No rules yet. Review more items to teach GLAZE your preferences.</p>
            <p className="text-[11px] text-zinc-800 mt-1">Rules emerge after 5+ reviews of the same type.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {rules.map((r, i) => (
              <div key={i} className="py-3 border-b border-zinc-800/20">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-[11px] px-1.5 py-0.5 rounded ${
                      r.action === 'kill'
                        ? 'bg-red-50 text-red-600'
                        : 'bg-emerald-50 text-emerald-600'
                    }`}>
                      auto-{r.action}
                    </span>
                    <span className="text-[12px] text-zinc-400">{r.cube_type}</span>
                  </div>
                  <span className="text-[11px] text-zinc-600 tabular-nums">{(r.rule_confidence * 100).toFixed(0)}% confident</span>
                </div>
                <p className="text-[11px] text-zinc-600">{r.evidence}</p>
                <p className="text-[11px] text-zinc-800 mt-0.5">
                  Threshold: confidence {r.action === 'kill' ? '<' : '>'} {(r.confidence_threshold * 100).toFixed(0)}%
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {stats && stats.recent.length > 0 && (
        <div className="border-t border-zinc-800/40 pt-6">
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-3">Recent Auto-Triage</h3>
          <div className="space-y-1.5">
            {stats.recent.slice(0, 10).map((r, i) => (
              <div key={i} className="flex items-center justify-between text-[11px] py-1.5">
                <div className="flex items-center gap-2 min-w-0">
                  <span className={r.action === 'kill' ? 'text-red-600' : 'text-emerald-600'}>{r.action}</span>
                  <span className="text-zinc-600 truncate">{r.reason}</span>
                </div>
                <span className="text-zinc-800 shrink-0 ml-2">{r.triaged_at.slice(0, 10)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
