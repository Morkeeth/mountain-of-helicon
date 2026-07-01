import { useState, useEffect } from 'react';
import { api } from '../api';
import type { QwenStats, QwenModels, QwenCache, QwenRouting } from '../api';

export function TokenDashboard() {
  const [stats, setStats] = useState<QwenStats | null>(null);
  const [models, setModels] = useState<QwenModels | null>(null);
  const [cache, setCache] = useState<QwenCache | null>(null);
  const [routing, setRouting] = useState<QwenRouting | null>(null);

  useEffect(() => {
    Promise.all([
      api.getQwenStats().catch(() => null),
      api.getQwenModels().catch(() => null),
      api.getQwenCache().catch(() => null),
      api.getQwenRouting().catch(() => null),
    ]).then(([s, m, c, r]) => {
      if (s) setStats(s);
      if (m) setModels(m);
      if (c) setCache(c);
      if (r) setRouting(r);
    });
  }, []);

  if (!stats) return (
    <div className="text-zinc-600 text-sm py-20 text-center">
      <p>No Qwen API activity yet.</p>
      <p className="text-[11px] text-zinc-700 mt-1">Token stats appear after Qwen Cloud calls (scan with API key, run audit, extract patterns).</p>
    </div>
  );

  // Backend returns cache:{hits,misses}; rate/entries are derived defensively.
  const hits = stats.cache.hits ?? 0;
  const misses = stats.cache.misses ?? 0;
  const cacheRate = (stats.cache.rate ?? (hits + misses > 0 ? hits / (hits + misses) : 0)) * 100;
  const cacheEntries = stats.cache.entries ?? hits;

  return (
    <div className="space-y-10">
      <div className="grid grid-cols-4 gap-6">
        <Stat label="Total Calls" value={stats.total_calls.toString()} />
        <Stat label="Cache Hit Rate" value={`${cacheRate.toFixed(1)}%`} color={cacheRate > 50 ? 'text-green-400' : cacheRate > 20 ? 'text-amber-400' : 'text-zinc-400'} />
        <Stat label="Cached Entries" value={cacheEntries.toString()} />
        <Stat label="Total Cost" value={`$${stats.total_cost_usd.toFixed(4)}`} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
        <div>
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Model Usage</h3>
          <div className="space-y-3">
            {Object.entries(stats.by_model).map(([model, data]) => {
              const totalTokens = data.input_tokens + data.output_tokens;
              const costPer1k = models?.cost_per_1k_tokens?.[model] || 0;
              return (
                <div key={model} className="border border-zinc-800/60 bg-white shadow-sm rounded-lg p-3">
                  <div className="flex items-baseline justify-between mb-2">
                    <span className="text-[13px] text-zinc-300 font-mono">{model}</span>
                    <span className="text-[11px] text-zinc-600">${costPer1k}/1k tokens</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-[11px]">
                    <div>
                      <span className="text-zinc-700 block">Calls</span>
                      <span className="text-zinc-400 tabular-nums">{data.calls}</span>
                    </div>
                    <div>
                      <span className="text-zinc-700 block">Cached</span>
                      <span className="text-green-500/60 tabular-nums">{data.cached_calls}</span>
                    </div>
                    <div>
                      <span className="text-zinc-700 block">Tokens</span>
                      <span className="text-zinc-400 tabular-nums">{totalTokens.toLocaleString()}</span>
                    </div>
                    <div>
                      <span className="text-zinc-700 block">Latency</span>
                      <span className="text-zinc-400 tabular-nums">{data.avg_latency}s</span>
                    </div>
                  </div>
                  {data.calls > 0 && (
                    <div className="mt-2 h-1.5 bg-zinc-800/60 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full"
                        style={{
                          background: 'linear-gradient(90deg, #3f3f46, #5c5c66)',
                          width: `${(data.cached_calls / data.calls) * 100}%`,
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
            {Object.keys(stats.by_model).length === 0 && (
              <p className="text-zinc-700 text-[12px]">No Qwen calls yet this session.</p>
            )}
          </div>
        </div>

        <div>
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Model Routing</h3>
          {models && (
            <div className="space-y-3 mb-6">
              {Object.entries(models.routing).map(([tier, model]) => (
                <div key={tier} className="flex items-baseline justify-between">
                  <div>
                    <span className="text-[13px] text-zinc-300">{tier}</span>
                    <span className="text-[11px] text-zinc-700 ml-2 font-mono">{model}</span>
                  </div>
                  <span className="text-[11px] text-zinc-700 max-w-[140px] text-right">{models.usage[tier]}</span>
                </div>
              ))}
            </div>
          )}

          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4 mt-8">Cache by Operation</h3>
          {cache && Object.keys(cache.by_operation).length > 0 ? (
            <div className="space-y-2">
              {Object.entries(cache.by_operation).map(([op, count]) => (
                <div key={op} className="flex items-baseline justify-between text-[12px]">
                  <span className="text-zinc-400 font-mono">{op}</span>
                  <span className="text-zinc-600 tabular-nums">{count} cached</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-zinc-700 text-[12px]">No cached operations yet.</p>
          )}
        </div>
      </div>

      {routing && routing.operations && Object.keys(routing.operations).length > 0 && (
        <div className="border-t border-zinc-800/40 pt-8">
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Route Learning</h3>
          <div className="space-y-3">
            {Object.entries(routing.operations).map(([op, data]) => (
              <div key={op} className="border border-zinc-800/60 bg-white shadow-sm rounded-lg p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-[13px] text-zinc-300 font-mono">{op}</span>
                  <span className="text-[11px] text-zinc-600">{data.calls} calls, ${data.total_cost.toFixed(4)}</span>
                </div>
                <div className="flex gap-2 flex-wrap">
                  {Object.entries(data.models_used).map(([model, count]) => (
                    <span key={model} className="text-[11px] px-2 py-0.5 bg-zinc-800/40 rounded text-zinc-500 font-mono">
                      {model}: {count}x
                    </span>
                  ))}
                </div>
                <div className="text-[11px] text-zinc-700 mt-1">
                  {data.avg_latency}s avg, {data.total_tokens.toLocaleString()} tokens
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {routing && routing.recommendations && routing.recommendations.length > 0 && (
        <div className="border-t border-zinc-800/40 pt-8">
          <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Routing Recommendations</h3>
          <div className="space-y-2">
            {routing.recommendations.map((rec, i) => (
              <div key={i} className="border border-violet-200 bg-violet-50 rounded-lg p-3">
                <div className="flex items-baseline justify-between mb-1">
                  <span className="text-[13px] text-violet-600 font-mono">{rec.operation}</span>
                  <span className="text-[11px] text-green-500/60">save ~${rec.estimated_savings_usd.toFixed(4)}</span>
                </div>
                <p className="text-[12px] text-zinc-500">
                  {rec.current_model} &rarr; {rec.suggested}: {rec.reason}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wider text-zinc-600 mb-1">{label}</p>
      <p className={`text-2xl font-light tabular-nums ${color || 'text-zinc-200'}`}>{value}</p>
    </div>
  );
}
