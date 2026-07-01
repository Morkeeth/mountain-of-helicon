import type { Connector } from '../api';

export function ConnectorStatus({ connectors }: { connectors: Connector[] }) {
  return (
    <div>
      <h3 className="text-[11px] uppercase tracking-wider text-zinc-600 mb-4">Connectors</h3>
      <div className="space-y-3">
        {connectors.map(c => (
          <div key={c.name} className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`w-1.5 h-1.5 rounded-full ${c.enabled ? 'bg-emerald-500' : 'bg-zinc-600'}`} />
              <span className="text-[13px] text-zinc-400">{c.name}</span>
            </div>
            <span className="text-[12px] text-zinc-600 tabular-nums">{c.cube_count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
