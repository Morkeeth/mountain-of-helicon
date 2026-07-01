import { useState, useEffect } from 'react';
import { api } from '../api';
import type { AuditFinding, Cube } from '../api';

interface ContradictionPair {
  finding: AuditFinding;
  cubeA: Cube | null;
  cubeB: Cube | null;
}

export function ContradictionView() {
  const [pairs, setPairs] = useState<ContradictionPair[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadContradictions();
  }, []);

  const loadContradictions = async () => {
    const { findings } = await api.getAudit(true);
    const factual = findings.filter(f => f.audit_type === 'factual');

    const loaded: ContradictionPair[] = [];
    for (const f of factual.slice(0, 15)) {
      void f.proposed_action;
      const idA = (f as unknown as { details?: { cube_a?: string } }).details?.cube_a || f.target_id;
      const idB = (f as unknown as { details?: { cube_b?: string } }).details?.cube_b;

      let cubeA: Cube | null = null;
      let cubeB: Cube | null = null;

      try {
        const resA = await fetch(`/api/cubes/${idA}`);
        if (resA.ok) cubeA = await resA.json();
      } catch { /* */ }

      if (idB) {
        try {
          const resB = await fetch(`/api/cubes/${idB}`);
          if (resB.ok) cubeB = await resB.json();
        } catch { /* */ }
      }

      loaded.push({ finding: f, cubeA, cubeB });
    }

    setPairs(loaded);
    setLoading(false);
  };

  if (loading) return <p className="text-zinc-600 text-sm py-10 text-center">Loading contradictions...</p>;

  if (pairs.length === 0) {
    return (
      <div className="py-16 text-center">
        <p className="text-zinc-500 text-sm mb-1">No contradictions found.</p>
        <p className="text-zinc-700 text-[12px]">Run an audit to check for factual inconsistencies.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[15px] font-medium text-zinc-200">Contradictions</h3>
        <span className="text-[11px] text-zinc-600">{pairs.length} potential conflicts</span>
      </div>

      {pairs.map((pair, i) => (
        <ContradictionCard key={i} pair={pair} onResolved={loadContradictions} />
      ))}
    </div>
  );
}

function ContradictionCard({ pair, onResolved }: { pair: ContradictionPair; onResolved: () => void }) {
  const [resolving, setResolving] = useState(false);

  const resolve = async (decision: 'keep_a' | 'keep_b' | 'keep_both' | 'dismiss') => {
    setResolving(true);
    await api.confirmAudit(pair.finding.id, decision);

    if (decision === 'keep_a' && pair.cubeB) {
      await api.submitReview(pair.cubeB.id, 'killed', 'Resolved contradiction: kept other version', 0);
    } else if (decision === 'keep_b' && pair.cubeA) {
      await api.submitReview(pair.cubeA.id, 'killed', 'Resolved contradiction: kept other version', 0);
    }

    setResolving(false);
    onResolved();
  };

  return (
    <div className="border border-zinc-800/60 rounded-lg p-5 animate-fade-in bg-white shadow-sm">
      <p className="text-[12px] text-zinc-500 mb-4">{pair.finding.finding}</p>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <CubeSide cube={pair.cubeA} label="A" />
        <CubeSide cube={pair.cubeB} label="B" />
      </div>

      <div className="flex gap-2 justify-end">
        <button
          onClick={() => resolve('keep_a')}
          disabled={resolving}
          className="text-[12px] px-3 py-1.5 rounded-md text-zinc-500 hover:text-emerald-600 hover:bg-emerald-50 border border-zinc-800/60 transition-colors disabled:opacity-30"
        >
          Keep A
        </button>
        <button
          onClick={() => resolve('keep_b')}
          disabled={resolving}
          className="text-[12px] px-3 py-1.5 rounded-md text-zinc-500 hover:text-emerald-600 hover:bg-emerald-50 border border-zinc-800/60 transition-colors disabled:opacity-30"
        >
          Keep B
        </button>
        <button
          onClick={() => resolve('keep_both')}
          disabled={resolving}
          className="text-[12px] px-3 py-1.5 rounded-md text-zinc-500 hover:text-violet-600 hover:bg-violet-50 border border-zinc-800/60 transition-colors disabled:opacity-30"
        >
          Keep Both
        </button>
        <button
          onClick={() => resolve('dismiss')}
          disabled={resolving}
          className="text-[12px] px-3 py-1.5 rounded-md text-zinc-500 hover:text-zinc-400 border border-zinc-800/40 transition-colors disabled:opacity-30"
        >
          Dismiss
        </button>
      </div>
    </div>
  );
}

function CubeSide({ cube, label }: { cube: Cube | null; label: string }) {
  if (!cube) {
    return (
      <div className="bg-zinc-900/40 rounded-md p-3">
        <span className="text-[11px] text-zinc-700">Cube not found</span>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900/40 rounded-md p-3">
      <div className="flex items-baseline justify-between mb-2">
        <span className="text-[11px] text-zinc-600 font-mono">{label}</span>
        <div className="flex gap-2 text-[11px] text-zinc-700">
          <span>{cube.source}</span>
          <span>{cube.type}</span>
          <span className="tabular-nums">{(cube.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>
      <p className="text-[13px] text-zinc-300 mb-2">{cube.title}</p>
      <pre className="text-[11px] text-zinc-600 whitespace-pre-wrap leading-relaxed max-h-32 overflow-y-auto">
        {cube.content.slice(0, 400)}
        {cube.content.length > 400 && '\n...'}
      </pre>
    </div>
  );
}
