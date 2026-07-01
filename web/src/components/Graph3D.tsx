import { useRef, useMemo, useState, useEffect, useCallback } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Text } from '@react-three/drei';
import * as THREE from 'three';
import { api } from '../api';
import type { GraphNode, GraphLink } from '../api';

interface SimNode extends GraphNode {
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
}

const TYPE_COLORS: Record<string, string> = {
  project: '#f59e0b',
  person: '#a8a29e',
  tool: '#71717a',
  concept: '#a1a1aa',
};

function NodeSphere({ node, selected, onClick }: { node: SimNode; selected: boolean; onClick: () => void }) {
  const meshRef = useRef<THREE.Mesh>(null);
  const glowRef = useRef<THREE.Mesh>(null);

  const baseRadius = node.kind === 'entity'
    ? Math.min(0.15 + Math.sqrt(node.size) * 0.06, 0.6)
    : 0.08;

  const color = useMemo(() => {
    if (selected) return '#f59e0b';
    if (node.kind === 'entity') return TYPE_COLORS[node.type] || '#71717a';
    const conf = node.confidence ?? 1;
    if (conf < 0.1) return '#ef4444';
    if (conf < 0.3) return '#d97706';
    return '#52525b';
  }, [node, selected]);

  useFrame(() => {
    if (!meshRef.current) return;
    meshRef.current.position.set(node.x, node.y, node.z);
    if (glowRef.current) {
      glowRef.current.position.set(node.x, node.y, node.z);
      const s = 1 + Math.sin(Date.now() * 0.002) * 0.1;
      glowRef.current.scale.setScalar(selected ? s * 1.8 : s * 1.4);
      (glowRef.current.material as THREE.MeshBasicMaterial).opacity =
        selected ? 0.3 : 0.08 + (node.confidence ?? 0.5) * 0.07;
    }
    if (selected) {
      const s = 1 + Math.sin(Date.now() * 0.004) * 0.15;
      meshRef.current.scale.setScalar(s);
    } else {
      meshRef.current.scale.setScalar(1);
    }
  });

  return (
    <group>
      <mesh ref={glowRef} onClick={onClick}>
        <sphereGeometry args={[baseRadius * 2, 16, 16]} />
        <meshBasicMaterial color={color} transparent opacity={0.08} depthWrite={false} />
      </mesh>
      <mesh ref={meshRef} onClick={onClick}>
        <sphereGeometry args={[baseRadius, 16, 16]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={selected ? 0.8 : 0.3}
          roughness={0.3}
          metalness={0.1}
        />
      </mesh>
    </group>
  );
}

function NodeLabel({ node }: { node: SimNode }) {
  const ref = useRef<THREE.Group>(null);

  useFrame(() => {
    if (!ref.current) return;
    ref.current.position.set(node.x, node.y + (node.kind === 'entity' ? 0.5 : 0.3), node.z);
  });

  if (node.kind !== 'entity' || node.size < 4) return null;

  return (
    <group ref={ref}>
      <Text
        fontSize={0.15}
        color="#a1a1aa"
        anchorX="center"
        anchorY="bottom"
        maxWidth={2}
        outlineWidth={0.01}
        outlineColor="#09090b"
      >
        {node.label}
      </Text>
    </group>
  );
}

function EdgeLines({ links, nodeMap }: { links: GraphLink[]; nodeMap: Map<string, SimNode> }) {
  const linesRef = useRef<THREE.LineSegments>(null);
  const contradictionRef = useRef<THREE.LineSegments>(null);

  const { regular, contradictions } = useMemo(() => {
    const regular: GraphLink[] = [];
    const contradictions: GraphLink[] = [];
    for (const l of links) {
      if (l.relation === 'contradicts') contradictions.push(l);
      else regular.push(l);
    }
    return { regular, contradictions };
  }, [links]);

  useFrame(() => {
    if (linesRef.current) {
      const positions = new Float32Array(regular.length * 6);
      let idx = 0;
      for (const link of regular) {
        const s = nodeMap.get(link.source);
        const t = nodeMap.get(link.target);
        if (!s || !t) { idx += 6; continue; }
        positions[idx++] = s.x; positions[idx++] = s.y; positions[idx++] = s.z;
        positions[idx++] = t.x; positions[idx++] = t.y; positions[idx++] = t.z;
      }
      linesRef.current.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      linesRef.current.geometry.attributes.position.needsUpdate = true;
    }

    if (contradictionRef.current) {
      const positions = new Float32Array(contradictions.length * 6);
      let idx = 0;
      for (const link of contradictions) {
        const s = nodeMap.get(link.source);
        const t = nodeMap.get(link.target);
        if (!s || !t) { idx += 6; continue; }
        positions[idx++] = s.x; positions[idx++] = s.y; positions[idx++] = s.z;
        positions[idx++] = t.x; positions[idx++] = t.y; positions[idx++] = t.z;
      }
      contradictionRef.current.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
      contradictionRef.current.geometry.attributes.position.needsUpdate = true;

      const pulse = 0.3 + Math.sin(Date.now() * 0.005) * 0.2;
      (contradictionRef.current.material as THREE.LineBasicMaterial).opacity = pulse;
    }
  });

  return (
    <>
      <lineSegments ref={linesRef}>
        <bufferGeometry />
        <lineBasicMaterial color="#3f3f46" transparent opacity={0.15} />
      </lineSegments>
      <lineSegments ref={contradictionRef}>
        <bufferGeometry />
        <lineBasicMaterial color="#ef4444" transparent opacity={0.4} linewidth={2} />
      </lineSegments>
    </>
  );
}

function ForceSimulation({ nodes, links, nodeMap }: { nodes: SimNode[]; links: GraphLink[]; nodeMap: Map<string, SimNode> }) {
  const tickRef = useRef(0);

  useFrame(() => {
    tickRef.current++;
    const cooling = Math.max(0.001, 1 - tickRef.current / 200);
    if (cooling < 0.01) return;

    for (const node of nodes) {
      for (const other of nodes) {
        if (node === other) continue;
        const dx = node.x - other.x;
        const dy = node.y - other.y;
        const dz = node.z - other.z;
        const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
        const force = (3 / (dist * dist)) * cooling;
        node.vx += (dx / dist) * force;
        node.vy += (dy / dist) * force;
        node.vz += (dz / dist) * force;
      }
    }

    for (const link of links) {
      const s = nodeMap.get(link.source);
      const t = nodeMap.get(link.target);
      if (!s || !t) continue;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dz = t.z - s.z;
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1;
      const force = (dist - 2) * 0.005 * cooling;
      s.vx += (dx / dist) * force;
      s.vy += (dy / dist) * force;
      s.vz += (dz / dist) * force;
      t.vx -= (dx / dist) * force;
      t.vy -= (dy / dist) * force;
      t.vz -= (dz / dist) * force;
    }

    for (const node of nodes) {
      node.vx += -node.x * 0.003;
      node.vy += -node.y * 0.003;
      node.vz += -node.z * 0.003;
      node.vx *= 0.8;
      node.vy *= 0.8;
      node.vz *= 0.8;
      node.x += node.vx;
      node.y += node.vy;
      node.z += node.vz;
    }
  });

  return null;
}

function Scene({ nodes, links, nodeMap, selected, onSelect }: {
  nodes: SimNode[];
  links: GraphLink[];
  nodeMap: Map<string, SimNode>;
  selected: SimNode | null;
  onSelect: (node: SimNode | null) => void;
}) {
  return (
    <>
      <ambientLight intensity={0.4} />
      <pointLight position={[10, 10, 10]} intensity={0.6} />
      <pointLight position={[-10, -5, 5]} intensity={0.3} color="#f59e0b" />

      <ForceSimulation nodes={nodes} links={links} nodeMap={nodeMap} />
      <EdgeLines links={links} nodeMap={nodeMap} />

      {nodes.map(node => (
        <NodeSphere
          key={node.id}
          node={node}
          selected={selected?.id === node.id}
          onClick={() => onSelect(selected?.id === node.id ? null : node)}
        />
      ))}
      {nodes.map(node => (
        <NodeLabel key={`label-${node.id}`} node={node} />
      ))}

      <OrbitControls
        enableDamping
        dampingFactor={0.1}
        rotateSpeed={0.5}
        zoomSpeed={0.8}
        minDistance={3}
        maxDistance={30}
        autoRotate
        autoRotateSpeed={0.3}
      />

      <fog attach="fog" args={['#09090b', 15, 40]} />
    </>
  );
}

export function Graph3D() {
  const [nodes, setNodes] = useState<SimNode[]>([]);
  const [links, setLinks] = useState<GraphLink[]>([]);
  const [selected, setSelected] = useState<SimNode | null>(null);
  const [detail, setDetail] = useState<{
    entity: Record<string, unknown>;
    cubes: { id: string; title: string; type: string; confidence: number }[];
    related_entities: { name: string; entity_type: string }[];
  } | null>(null);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [stats, setStats] = useState({ nodes: 0, links: 0 });

  const nodeMap = useMemo(() => new Map(nodes.map(n => [n.id, n])), [nodes]);

  const loadGraph = useCallback(async () => {
    try {
      const data = await api.getGraph();
      if (data.nodes.length === 0) { setLoading(false); return; }

      const simNodes: SimNode[] = data.nodes.map((n, i) => {
        const phi = Math.acos(1 - 2 * (i + 0.5) / data.nodes.length);
        const theta = Math.PI * (1 + Math.sqrt(5)) * i;
        const r = 4 + Math.random() * 2;
        return {
          ...n,
          x: r * Math.sin(phi) * Math.cos(theta),
          y: r * Math.sin(phi) * Math.sin(theta),
          z: r * Math.cos(phi),
          vx: 0, vy: 0, vz: 0,
        };
      });

      setNodes(simNodes);
      setLinks(data.links);
      setStats({ nodes: data.nodes.length, links: data.links.length });
      setLoading(false);
    } catch {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadGraph(); }, [loadGraph]);

  const handleSelect = useCallback((node: SimNode | null) => {
    setSelected(node);
    if (node && node.kind === 'entity') {
      api.getEntityDetail(node.id).then(setDetail);
    } else {
      setDetail(null);
    }
  }, []);

  const handleBuild = async () => {
    setBuilding(true);
    await api.buildGraph();
    await loadGraph();
    setBuilding(false);
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
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
          <div className="h-[560px] flex items-center justify-center border border-zinc-800/40 rounded-xl bg-zinc-950/50">
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
          <div className="h-[560px] border border-zinc-800/40 rounded-xl overflow-hidden bg-[#050507]">
            <Canvas
              camera={{ position: [0, 0, 12], fov: 60 }}
              gl={{ antialias: true, alpha: false }}
              onCreated={({ gl }) => { gl.setClearColor('#050507'); }}
            >
              <Scene
                nodes={nodes}
                links={links}
                nodeMap={nodeMap}
                selected={selected}
                onSelect={handleSelect}
              />
            </Canvas>
          </div>
        )}

        {selected && (
          <div className="absolute top-4 right-4 w-72 bg-white/95 border border-zinc-800/60 rounded-xl p-5 backdrop-blur-md shadow-2xl shadow-zinc-300/60">
            <div className="flex items-baseline justify-between mb-3">
              <span className="text-[14px] text-zinc-100 font-medium">{selected.label}</span>
              <button
                onClick={() => { setSelected(null); setDetail(null); }}
                className="text-zinc-600 hover:text-zinc-300 text-[11px] w-5 h-5 flex items-center justify-center rounded hover:bg-zinc-800/60"
              >
                x
              </button>
            </div>
            <div className="flex gap-3 text-[11px] text-zinc-600 mb-3">
              <span className="px-1.5 py-0.5 rounded bg-zinc-800/50">{selected.kind}</span>
              <span className="px-1.5 py-0.5 rounded bg-zinc-800/50">{selected.type}</span>
              {selected.kind === 'entity' && <span>{selected.size} mentions</span>}
              {selected.confidence !== undefined && (
                <span className="tabular-nums">{(selected.confidence * 100).toFixed(0)}%</span>
              )}
            </div>

            {detail && (
              <div className="space-y-4 border-t border-zinc-800/40 pt-3">
                <div>
                  <p className="text-[10px] uppercase tracking-wider text-zinc-700 mb-1.5">
                    Cubes ({detail.cubes.length})
                  </p>
                  <div className="space-y-1 max-h-36 overflow-y-auto">
                    {detail.cubes.slice(0, 8).map(c => (
                      <div key={c.id} className="flex items-center gap-2 text-[11px]">
                        <span className={`w-1.5 h-1.5 rounded-full ${c.confidence > 0.5 ? 'bg-emerald-500/50' : c.confidence > 0.2 ? 'bg-amber-500/50' : 'bg-red-500/50'}`} />
                        <span className="text-zinc-500 truncate">{c.title}</span>
                      </div>
                    ))}
                  </div>
                </div>
                {detail.related_entities.length > 0 && (
                  <div>
                    <p className="text-[10px] uppercase tracking-wider text-zinc-700 mb-1.5">Related</p>
                    <div className="flex flex-wrap gap-1">
                      {detail.related_entities.slice(0, 10).map(r => (
                        <span key={r.name} className="text-[10px] text-zinc-500 bg-zinc-800/60 px-2 py-0.5 rounded-md">
                          {r.name}
                        </span>
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
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-violet-500" /> Project
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-400/70" /> Person
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-500/50" /> Tool
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-zinc-400/40" /> Concept
        </span>
        <span className="flex items-center gap-1.5">
          <span className="w-4 h-[2px] bg-red-400/50 rounded" /> Contradiction
        </span>
        <span className="text-zinc-800 ml-auto">drag to rotate, scroll to zoom</span>
      </div>
    </div>
  );
}
