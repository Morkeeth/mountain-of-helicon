import { useRef, useEffect, useState, useCallback } from 'react';
import { api } from '../api';
import type { GraphNode, GraphLink } from '../api';

interface SimNode extends GraphNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
}

export function GraphView() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [detail, setDetail] = useState<{ entity: Record<string, unknown>; cubes: { id: string; title: string; type: string; confidence: number }[]; related_entities: { name: string; entity_type: string }[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [stats, setStats] = useState({ nodes: 0, links: 0 });
  const animRef = useRef<number>(0);
  const dragRef = useRef<{ node: SimNode | null; offsetX: number; offsetY: number }>({ node: null, offsetX: 0, offsetY: 0 });
  const panRef = useRef({ x: 0, y: 0 });
  const zoomRef = useRef(1);

  const loadGraph = useCallback(async () => {
    try {
      const data = await api.getGraph();
      if (data.nodes.length === 0) return;

      const w = 800;
      const h = 500;
      const simNodes: SimNode[] = data.nodes.map((n, i) => ({
        ...n,
        x: w / 2 + (Math.cos(i * 2.399) * 150) + (Math.random() - 0.5) * 100,
        y: h / 2 + (Math.sin(i * 2.399) * 150) + (Math.random() - 0.5) * 100,
        vx: 0,
        vy: 0,
      }));

      setNodes(simNodes);
      setLinks(data.links);
      setStats({ nodes: data.nodes.length, links: data.links.length });
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  useEffect(() => {
    if (nodes.length === 0) return;

    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const nodeMap = new Map(nodes.map(n => [n.id, n]));
    let tick = 0;

    const simulate = () => {
      tick++;
      const cooling = Math.max(0.001, 1 - tick / 120);

      if (cooling < 0.01) {
        for (const node of nodes) { node.vx = 0; node.vy = 0; }
      } else {
        for (const node of nodes) {
          for (const other of nodes) {
            if (node === other) continue;
            const dx = node.x - other.x;
            const dy = node.y - other.y;
            const dist = Math.sqrt(dx * dx + dy * dy) || 1;
            const force = (500 / (dist * dist)) * cooling;
            node.vx += (dx / dist) * force;
            node.vy += (dy / dist) * force;
          }
        }

        for (const link of links) {
          const s = nodeMap.get(link.source);
          const t = nodeMap.get(link.target);
          if (!s || !t) continue;
          const dx = t.x - s.x;
          const dy = t.y - s.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - 80) * 0.003 * cooling;
          s.vx += (dx / dist) * force;
          s.vy += (dy / dist) * force;
          t.vx -= (dx / dist) * force;
          t.vy -= (dy / dist) * force;
        }

        const cx = canvas.width / 2;
        const cy = canvas.height / 2;
        for (const node of nodes) {
          node.vx += (cx - node.x) * 0.002;
          node.vy += (cy - node.y) * 0.002;
          node.vx *= 0.75;
          node.vy *= 0.75;
          if (node !== dragRef.current.node) {
            node.x += node.vx;
            node.y += node.vy;
          }
        }
      }

      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.save();
      ctx.translate(panRef.current.x, panRef.current.y);
      ctx.scale(zoomRef.current, zoomRef.current);

      for (const link of links) {
        const s = nodeMap.get(link.source);
        const t = nodeMap.get(link.target);
        if (!s || !t) continue;
        ctx.beginPath();
        ctx.moveTo(s.x, s.y);
        ctx.lineTo(t.x, t.y);
        if (link.relation === 'contradicts') {
          ctx.strokeStyle = 'rgba(239, 68, 68, 0.4)';
          ctx.lineWidth = 1.5;
        } else if (link.relation === 'co_occurs') {
          ctx.strokeStyle = 'rgba(113, 113, 122, 0.12)';
          ctx.lineWidth = 0.5;
        } else {
          ctx.strokeStyle = 'rgba(113, 113, 122, 0.08)';
          ctx.lineWidth = 0.5;
        }
        ctx.stroke();
      }

      for (const node of nodes) {
        const radius = node.kind === 'entity'
          ? Math.min(3 + Math.sqrt(node.size) * 1.5, 14)
          : 2.5;

        ctx.beginPath();
        ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);

        if (node === selected) {
          ctx.fillStyle = '#f59e0b';
        } else if (node.kind === 'entity') {
          const typeColors: Record<string, string> = {
            project: 'rgba(245, 158, 11, 0.7)',
            person: 'rgba(168, 162, 158, 0.7)',
            tool: 'rgba(113, 113, 122, 0.5)',
            concept: 'rgba(161, 161, 170, 0.4)',
          };
          ctx.fillStyle = typeColors[node.type] || 'rgba(113, 113, 122, 0.4)';
        } else {
          const conf = node.confidence ?? 1;
          ctx.fillStyle = conf < 0.1
            ? 'rgba(239, 68, 68, 0.3)'
            : conf < 0.3
              ? 'rgba(245, 158, 11, 0.3)'
              : 'rgba(113, 113, 122, 0.25)';
        }
        ctx.fill();

        if (node.kind === 'entity' && node.size > 5) {
          ctx.fillStyle = 'rgba(228, 228, 231, 0.5)';
          ctx.font = '9px Inter, sans-serif';
          ctx.textAlign = 'center';
          ctx.fillText(node.label, node.x, node.y + radius + 10);
        }
      }

      ctx.restore();
      animRef.current = requestAnimationFrame(simulate);
    };

    animRef.current = requestAnimationFrame(simulate);
    return () => cancelAnimationFrame(animRef.current);
  }, [nodes, links, selected]);

  const handleCanvasClick = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = (e.clientX - rect.left - panRef.current.x) / zoomRef.current;
    const my = (e.clientY - rect.top - panRef.current.y) / zoomRef.current;

    let closest: SimNode | null = null;
    let minDist = 20;
    for (const node of nodes) {
      const dx = node.x - mx;
      const dy = node.y - my;
      const dist = Math.sqrt(dx * dx + dy * dy);
      if (dist < minDist) {
        minDist = dist;
        closest = node;
      }
    }

    setSelected(closest);
    if (closest && closest.kind === 'entity') {
      api.getEntityDetail(closest.id).then(setDetail);
    } else {
      setDetail(null);
    }
  }, [nodes]);

  const handleBuild = async () => {
    setBuilding(true);
    await api.buildGraph();
    await loadGraph();
    setBuilding(false);
  };

  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    zoomRef.current = Math.max(0.3, Math.min(3, zoomRef.current * delta));
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-baseline gap-3">
          <h2 className="text-[15px] font-medium text-zinc-200">Knowledge Graph</h2>
          <span className="text-[11px] text-zinc-600">{stats.nodes} nodes, {stats.links} edges</span>
        </div>
        <button
          onClick={handleBuild}
          disabled={building}
          className="text-[12px] px-3 py-1.5 rounded-md border border-violet-200 text-violet-600 hover:bg-violet-50 transition-colors disabled:opacity-30 shadow-sm bg-white"
        >
          {building ? 'Building...' : 'Rebuild Graph'}
        </button>
      </div>

      <div className="relative">
        {loading || nodes.length === 0 ? (
          <div className="h-[500px] flex items-center justify-center border border-zinc-800/40 rounded-lg">
            <div className="text-center">
              <p className="text-zinc-500 text-sm mb-2">{loading ? 'Loading graph...' : 'No graph data yet.'}</p>
              {!loading && (
                <button onClick={handleBuild} className="text-[12px] text-violet-600 hover:text-violet-500">
                  Build graph from cubes
                </button>
              )}
            </div>
          </div>
        ) : (
          <canvas
            ref={canvasRef}
            width={900}
            height={500}
            className="w-full h-[500px] border border-zinc-800/40 rounded-lg cursor-crosshair"
            onClick={handleCanvasClick}
            onWheel={handleWheel}
          />
        )}

        {selected && (
          <div className="absolute top-3 right-3 w-64 bg-white/95 border border-zinc-800/60 rounded-lg p-4 backdrop-blur-sm shadow-lg">
            <div className="flex items-baseline justify-between mb-2">
              <span className="text-[13px] text-zinc-200 font-medium">{selected.label}</span>
              <button onClick={() => { setSelected(null); setDetail(null); }} className="text-zinc-600 hover:text-zinc-400 text-[11px]">x</button>
            </div>
            <div className="flex gap-3 text-[11px] text-zinc-600 mb-3">
              <span>{selected.kind}</span>
              <span>{selected.type}</span>
              {selected.kind === 'entity' && <span>{selected.size} mentions</span>}
              {selected.confidence !== undefined && <span>{(selected.confidence * 100).toFixed(0)}%</span>}
            </div>

            {detail && (
              <div className="space-y-3 border-t border-zinc-800/40 pt-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-zinc-700 mb-1">Cubes ({detail.cubes.length})</p>
                  <div className="space-y-1 max-h-32 overflow-y-auto">
                    {detail.cubes.slice(0, 8).map(c => (
                      <div key={c.id} className="text-[11px] text-zinc-500 truncate">{c.title}</div>
                    ))}
                  </div>
                </div>
                {detail.related_entities.length > 0 && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-700 mb-1">Related</p>
                    <div className="flex flex-wrap gap-1">
                      {detail.related_entities.slice(0, 8).map(r => (
                        <span key={r.name} className="text-[10px] text-zinc-600 bg-zinc-800/40 px-1.5 py-0.5 rounded">{r.name}</span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex gap-6 mt-4 text-[11px] text-zinc-700">
        <span><span className="inline-block w-2 h-2 rounded-full bg-violet-500 mr-1" />Project</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-zinc-400/70 mr-1" />Person</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-zinc-500/50 mr-1" />Tool</span>
        <span><span className="inline-block w-2 h-2 rounded-full bg-zinc-400/40 mr-1" />Concept</span>
        <span><span className="inline-block w-1.5 h-[2px] bg-red-400/50 mr-1" />Contradiction</span>
      </div>
    </div>
  );
}
