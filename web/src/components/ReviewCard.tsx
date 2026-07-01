import { useState, useCallback, useEffect } from 'react';
import { api } from '../api';
import type { Cube } from '../api';
import { VoiceInput } from './VoiceInput';

function confColor(c: number): string {
  if (c < 0.1) return 'text-red-400/60';
  if (c < 0.3) return 'text-amber-600';
  return 'text-zinc-500';
}

function daysAgo(dateStr: string): string {
  const d = new Date(dateStr);
  const days = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (days === 0) return 'today';
  if (days === 1) return '1d';
  return `${days}d`;
}

interface Props {
  cube: Cube;
  onReviewed: () => void;
  focused?: boolean;
  onAction?: (decision: string) => void;
}

export function ReviewCard({ cube, onReviewed, focused, onAction }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [notes, setNotes] = useState('');
  const startTime = Date.now();

  const handleReview = async (decision: string) => {
    setReviewing(true);
    const elapsed = (Date.now() - startTime) / 1000;
    await api.submitReview(cube.id, decision, notes, elapsed);
    setReviewing(false);
    onReviewed();
  };

  useEffect(() => {
    if (focused && onAction) {
      const handler = (e: KeyboardEvent) => {
        if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
        if (e.key === 'a') { handleReview('approved'); onAction('approved'); }
        if (e.key === 'r') { handleReview('revised'); onAction('revised'); }
        if (e.key === 'k') { handleReview('killed'); onAction('killed'); }
        if (e.key === 'e' || e.key === 'Enter') setExpanded(v => !v);
      };
      window.addEventListener('keydown', handler);
      return () => window.removeEventListener('keydown', handler);
    }
  }, [focused, onAction]);

  const confWidth = Math.max(cube.confidence * 100, 2);

  return (
    <div className={`group relative py-3.5 border-b transition-all duration-200 ${
      focused
        ? 'border-violet-200 bg-violet-50/50'
        : 'border-zinc-800/30 hover:border-zinc-700/50'
    }`}>
      {focused && (
        <div className="absolute left-0 top-2 bottom-2 w-[2px] rounded-full" style={{ background: 'linear-gradient(180deg, #3f3f46, #5c5c66)' }} />
      )}
      <div className="flex items-start justify-between gap-4 pl-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-[11px] text-zinc-600">{cube.source}</span>
            <span className="text-zinc-800/40">|</span>
            <span className="text-[11px] text-zinc-700">{cube.type}</span>
            <span className="text-[11px] text-zinc-800 tabular-nums">{daysAgo(cube.created_at)}</span>
            {cube.spin_count > 0 && (
              <span className="text-[10px] px-1 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">{cube.spin_count}x spin</span>
            )}
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-[13px] text-zinc-300 hover:text-zinc-100 transition-colors text-left truncate max-w-full block leading-snug"
          >
            {cube.title}
          </button>
          <div className="mt-1.5 w-full h-[2px] bg-zinc-800/30 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 bg-zinc-500/30"
              style={{ width: `${confWidth}%` }}
            />
          </div>
        </div>
        <span className={`text-[12px] font-mono tabular-nums shrink-0 ${confColor(cube.confidence)}`}>
          {(cube.confidence * 100).toFixed(0)}%
        </span>
      </div>

      {expanded && (
        <div className="mt-3 pl-3 animate-fade-in-scale">
          <pre className="text-[12px] text-zinc-400 bg-zinc-900/50 p-4 rounded-lg overflow-auto max-h-48 whitespace-pre-wrap leading-relaxed border border-zinc-800/40">
            {cube.content.slice(0, 800)}
            {cube.content.length > 800 && '\n...'}
          </pre>
          {cube.tags.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2.5">
              {cube.tags.map(t => (
                <span key={t} className="text-[10px] px-1.5 py-0.5 rounded-full bg-zinc-800/40 text-zinc-600">{t}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mt-3 pl-3 flex items-center gap-2">
        <VoiceInput onTranscript={useCallback((t: string) => setNotes(n => n ? `${n} ${t}` : t), [])} disabled={reviewing} />
        <input
          type="text"
          value={notes}
          onChange={e => setNotes(e.target.value)}
          placeholder="Notes"
          className="flex-1 text-[12px] bg-white border border-zinc-800/60 rounded-lg px-2.5 py-1.5 text-zinc-400 placeholder:text-zinc-700 focus:outline-none focus:border-violet-300 focus:ring-1 focus:ring-violet-200 transition-colors shadow-sm"
        />
        <div className="flex gap-0.5">
          <button
            onClick={() => handleReview('approved')}
            disabled={reviewing}
            className="text-[12px] px-3 py-1.5 rounded-lg text-zinc-500 hover:text-emerald-600 hover:bg-emerald-50 active:scale-95 transition-all disabled:opacity-30"
          >
            Keep
          </button>
          <button
            onClick={() => handleReview('revised')}
            disabled={reviewing}
            className="text-[12px] px-3 py-1.5 rounded-lg text-zinc-500 hover:text-violet-600 hover:bg-violet-50 active:scale-95 transition-all disabled:opacity-30"
          >
            Revise
          </button>
          <button
            onClick={() => handleReview('killed')}
            disabled={reviewing}
            className="text-[12px] px-3 py-1.5 rounded-lg text-zinc-500 hover:text-red-600 hover:bg-red-50 active:scale-95 transition-all disabled:opacity-30"
          >
            Kill
          </button>
        </div>
      </div>
    </div>
  );
}
