import { useState, useEffect } from 'react';
import { api } from '../api';
import type { EvalResult, EvalRun, ScoreHistoryPoint } from '../api';
import { ScoreTimelineChart, EvalRadar, EvalTrendChart } from './Charts';

export function EvalView() {
  const [evalResult, setEvalResult] = useState<EvalResult | null>(null);
  const [history, setHistory] = useState<EvalRun[]>([]);
  const [scoreHistory, setScoreHistory] = useState<ScoreHistoryPoint[]>([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.getEvalHistory(),
      api.getScoreHistory(),
    ]).then(([evalH, scoreH]) => {
      setHistory(evalH.runs);
      setScoreHistory(scoreH.history);
      setLoading(false);
    }).catch(() => setLoading(false));

    api.backfillScoreHistory().catch(() => {});
  }, []);

  const runBenchmark = async () => {
    setRunning(true);
    try {
      const result = await api.runEval();
      setEvalResult(result);
      const h = await api.getEvalHistory();
      setHistory(h.runs);
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return <div className="py-20 text-center text-zinc-600 text-sm">Loading evaluation data...</div>;
  }

  return (
    <div className="space-y-8">
      {/* Score Timeline */}
      {scoreHistory.length > 0 && (
        <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-5 py-4">
          <ScoreTimelineChart points={scoreHistory} />
        </div>
      )}

      {/* Run benchmark */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-[15px] font-medium text-zinc-200">Evaluation Harness</h2>
          <p className="text-[12px] text-zinc-600 mt-0.5">Retrieval precision, forgetting accuracy, audit recall</p>
        </div>
        <button
          onClick={runBenchmark}
          disabled={running}
          className="px-4 py-1.5 text-[12px] border border-zinc-700/50 rounded hover:bg-zinc-800/50 text-zinc-400 disabled:opacity-40 transition-colors"
        >
          {running ? 'Running...' : 'Run Benchmarks'}
        </button>
      </div>

      {/* Latest result */}
      {evalResult && (
        <div className="space-y-4">
          <div className="grid grid-cols-4 gap-3">
            <MetricCard label="Composite" value={`${evalResult.composite_score}%`} />
            <MetricCard label="Precision@3" value={`${(evalResult.retrieval.precision_at_3 * 100).toFixed(0)}%`} />
            <MetricCard label="Forgetting" value={`${(evalResult.forgetting.forgetting_accuracy * 100).toFixed(0)}%`} />
            <MetricCard label="Audit Recall" value={`${(evalResult.audit.audit_recall * 100).toFixed(0)}%`} />
          </div>

          {/* Retrieval details */}
          <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-5 py-4">
            <h3 className="text-[12px] uppercase tracking-wider text-zinc-600 mb-3">
              Retrieval ({evalResult.retrieval.query_count} queries, MRR: {evalResult.retrieval.mrr.toFixed(3)})
            </h3>
            <div className="space-y-1.5">
              {evalResult.retrieval.details.slice(0, 10).map((d, i) => (
                <div key={i} className="flex items-center gap-2 text-[11px]">
                  <span className={`w-12 shrink-0 tabular-nums ${d.found_at_rank && d.found_at_rank <= 3 ? 'text-emerald-400/70' : d.found_at_rank ? 'text-amber-500/60' : 'text-red-400/60'}`}>
                    {d.found_at_rank ? `#${d.found_at_rank}` : 'miss'}
                  </span>
                  <span className="text-zinc-500 truncate flex-1">{d.query}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Forgetting breakdown */}
          <div className="grid grid-cols-2 gap-3">
            <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-4 py-3">
              <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-2">Kill Prediction</h3>
              <div className="text-[13px] text-zinc-300 tabular-nums">
                {evalResult.forgetting.killed_with_low_conf}/{evalResult.forgetting.killed_total} correct
              </div>
              <p className="text-[10px] text-zinc-700 mt-1">Items killed by human that Weibull predicted as low confidence</p>
            </div>
            <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-4 py-3">
              <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-2">Approve Prediction</h3>
              <div className="text-[13px] text-zinc-300 tabular-nums">
                {evalResult.forgetting.approved_with_ok_conf}/{evalResult.forgetting.approved_total} correct
              </div>
              <p className="text-[10px] text-zinc-700 mt-1">Items approved by human that still had reasonable confidence</p>
            </div>
          </div>
        </div>
      )}

      {/* Visual eval */}
      {history.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-5 py-4">
            <EvalRadar evalRun={history[0]} />
          </div>
          <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-5 py-4">
            <EvalTrendChart history={history} />
          </div>
        </div>
      )}

      {/* History */}
      {history.length > 0 && (
        <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-5 py-4">
          <h3 className="text-[12px] uppercase tracking-wider text-zinc-600 mb-3">Eval History</h3>
          <div className="space-y-1.5">
            <div className="grid grid-cols-6 text-[10px] text-zinc-700 uppercase tracking-wider pb-1 border-b border-zinc-800/30">
              <span>Date</span>
              <span className="text-right">P@3</span>
              <span className="text-right">P@5</span>
              <span className="text-right">MRR</span>
              <span className="text-right">Forget</span>
              <span className="text-right">Audit</span>
            </div>
            {history.slice(0, 10).map(r => (
              <div key={r.id} className="grid grid-cols-6 text-[11px] text-zinc-500 tabular-nums">
                <span>{r.run_at.slice(0, 10)}</span>
                <span className="text-right">{(r.precision_at_3 * 100).toFixed(0)}%</span>
                <span className="text-right">{(r.precision_at_5 * 100).toFixed(0)}%</span>
                <span className="text-right">{r.mrr.toFixed(3)}</span>
                <span className="text-right">{(r.forgetting_accuracy * 100).toFixed(0)}%</span>
                <span className="text-right">{(r.audit_recall * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-zinc-800/60 bg-white shadow-sm rounded-lg px-4 py-3 text-center">
      <span className="text-[10px] text-zinc-700 uppercase tracking-wider block">{label}</span>
      <span className="text-[20px] font-light text-zinc-200 tabular-nums">{value}</span>
    </div>
  );
}

