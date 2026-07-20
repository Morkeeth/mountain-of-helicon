/* The front door, a full tour of Mount Helicon across the three surfaces
   (terminal, IDE/MCP, dashboard), built with the real Court design tokens so it
   matches the app exactly. Real command output only. */

const SERIF = { fontFamily: 'var(--helicon-serif)', fontVariationSettings: "'opsz' 144" } as const;

function Term({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl overflow-hidden shadow-lg" style={{ background: '#141b2b' }}>
      <div className="flex gap-1.5 px-3.5 py-2.5" style={{ borderBottom: '1px solid rgba(255,255,255,0.07)' }}>
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#e05a4e' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#e0b23a' }} />
        <span className="w-2.5 h-2.5 rounded-full" style={{ background: '#3f627d' }} />
      </div>
      <pre className="m-0 px-4 py-3.5 overflow-x-auto leading-relaxed" style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: 12, color: '#e7e9f0' }}>
        {children}
      </pre>
    </div>
  );
}
const P = ({ c }: { c: string }) => <span style={{ color: '#C5A25A' }}>{c}</span>;
const CMD = ({ c }: { c: string }) => <span style={{ color: '#e7e9f0', fontWeight: 600 }}>{c}</span>;
const ROT = ({ c }: { c: string }) => <span style={{ color: '#e08a72' }}>{c}</span>;
const OK = ({ c }: { c: string }) => <span style={{ color: '#8fbf8a' }}>{c}</span>;
const DIM = ({ c }: { c: string }) => <span style={{ color: '#8b93a7' }}>{c}</span>;
const NUM = ({ c }: { c: string }) => <span style={{ color: '#e0b23a' }}>{c}</span>;

function Exhibit({ n, title, sub, children }: { n: string; title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-white shadow-sm border border-zinc-800/50 p-6 space-y-4">
      <div className="flex items-baseline gap-3 flex-wrap">
        <span className="text-[13px]" style={{ ...SERIF, color: 'var(--helicon-stale)' }}>{n}</span>
        <h3 className="text-[20px]" style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>{title}</h3>
        <span className="text-[12px] ml-auto" style={{ color: 'var(--helicon-muted)' }}>{sub}</span>
      </div>
      {children}
    </div>
  );
}

const CARDS_DASH = [
  ['Next Moves', 'Memory → your move', 'Qwen turns the state of your memory into 2-4 cited next prompts. Uncited ones are dropped.'],
  ['Memory', 'Setup report card', 'Graded live against the MemoryAgent criteria: storage, forgetting, recall, cross-session accuracy.'],
  ['Needs Ruling', 'The cases', 'Every finding as a case: the why leads, evidence follows. Rule once, it sticks.'],
  ['Golden Rules', 'The precedent', "Your rulings compiled into your agent's operating law, each with provenance."],
];
const STACK = [
  ['Retrieval', 'retrieve → rerank', 'text-embedding-v4 (1024-dim) + FTS, fused by Reciprocal Rank Fusion, reranked by qwen3-rerank. Fully Qwen-native.'],
  ['Two-judge court', 'κ, not one voice', 'Each contradiction adjudicated by qwen3.6-plus and a decorrelated second judge (deepseek-v4). Splits escalate to you; Cohen’s κ reported.'],
  ['Tiered + honest', 'flash / plus / max', 'Routed by difficulty, structured outputs, response-cached, cost-tracked. Degrades honestly without a key.'],
  ['Alibaba proof', 'runs in Cloud Shell', 'scripts/cloudshell-run.sh boots the backend inside Alibaba Cloud Shell. Local-first everywhere else.'],
];

export default function Landing({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="space-y-14 pb-8">
      {/* HERO */}
      <div className="rounded-2xl overflow-hidden" style={{ background: '#141b2b' }}>
        <div className="px-8 py-12">
          <div className="text-[10px] uppercase tracking-[0.3em] mb-5" style={{ color: '#C5A25A' }}>The court of record for agent memory</div>
          <h1 className="text-[clamp(30px,5vw,52px)] leading-[1.1] max-w-[16ch] m-0" style={{ ...SERIF, color: '#f6f1e9', fontWeight: 500 }}>
            Memory stores remember. Mount Helicon knows what's <span style={{ color: '#C5A25A', fontStyle: 'italic' }}>still true.</span>
          </h1>
          <p className="text-[17px] mt-5 max-w-[60ch]" style={{ color: '#c3cad9' }}>
            It runs a twelve-class rot exam across your agent's live memory, context, and output, turns your rulings into precedent, and hands back your next move, every answer citing the memory it came from.
          </p>
          <div className="flex gap-3 mt-7 flex-wrap">
            <button onClick={onEnter} className="text-[14px] font-semibold px-4 py-2.5 rounded-lg" style={{ background: '#C5A25A', color: '#141b2b' }}>
              Enter the dashboard →
            </button>
            <span className="text-[13px] px-4 py-2.5 rounded-lg" style={{ color: '#eef0f4', border: '1px solid rgba(255,255,255,0.22)', fontFamily: 'var(--font-mono, monospace)' }}>
              github.com/MorkeethHQ/mount-helicon
            </span>
          </div>
        </div>
      </div>

      {/* THE PROBLEM */}
      <section>
        <div className="text-[11px] uppercase tracking-[0.24em] mb-2" style={{ color: 'var(--helicon-muted)' }}>The problem</div>
        <h2 className="text-[clamp(24px,3.2vw,32px)] max-w-[26ch] m-0 mb-3" style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>
          Agents are good at remembering. They have no idea when what they remember has rotted.
        </h2>
        <div className="grid sm:grid-cols-2 gap-x-8 gap-y-3 mt-5">
          {[
            'Two files disagree about the same fact, the agent picks one, confidently, for days.',
            'A project gets renamed; the dead name survives in "current" claims across the store.',
            'Context you killed keeps getting retrieved back into the prompt.',
            'CLAUDE.md / AGENTS.md instructions drift from what the code actually does.',
          ].map((t, i) => (
            <div key={i} className="flex gap-2.5 text-[14.5px]" style={{ color: 'var(--helicon-ink)' }}>
              <span className="w-2 h-2 rounded-sm mt-2 shrink-0" style={{ background: 'var(--helicon-accent)' }} />
              <span>{t}</span>
            </div>
          ))}
        </div>
      </section>

      {/* THREE SURFACES */}
      <section className="space-y-5">
        <div>
          <div className="text-[11px] uppercase tracking-[0.24em] mb-2" style={{ color: 'var(--helicon-muted)' }}>Explore it, three ways to run it</div>
          <h2 className="text-[clamp(24px,3.2vw,32px)] m-0" style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>The dashboard is optional. It meets you where you work.</h2>
        </div>

        <Exhibit n="i." title="In the terminal" sub="the 10-second daily check">
          <p className="text-[14px] m-0 mb-3" style={{ color: 'var(--helicon-muted)' }}>Twelve documented rot classes against your real store, no key, no LLM, free to run daily and in CI.</p>
          <Term>{`$ `}<CMD c="helicon rot" />{`
The rot exam, 12 documented failure classes, checked live

   R1  Cross-source contradiction   `}<ROT c="ROT FOUND" />{`
       wins[hackathon]: 4 vs 9 · decision-status: executed vs open
   R4  Supersession / rename        `}<ROT c="ROT FOUND" />{`
       RELAY→FAVOUR: 438 live dead-name claim(s) still current
   R5  Duplicate / echo memory      `}<OK c="CLEAN" />{`
   `}<NUM c="7/12" />{` classes show rot right now · 12/12 fully tested

$ `}<CMD c="helicon doctor" />{`
  `}<OK c="[OK]" />{` Qwen key configured   `}<OK c="[OK]" />{` DB, `}<NUM c="4,214" />{` cubes`}</Term>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-2.5 mt-4">
            {[['helicon ci', 'rot exam as a GitHub Action'], ['helicon battery "<task>"', 'context-quality verdict'], ['helicon gold --inject', 'rulings → GOLDEN_RULES.md'], ['helicon watch', 'ambient cron, pings on new rot']].map(([c, d]) => (
              <div key={c} className="rounded-lg border border-zinc-800/40 px-3 py-2.5">
                <code className="text-[13px] font-semibold" style={{ color: 'var(--helicon-accent)' }}>{c}</code>
                <div className="text-[12px] mt-0.5" style={{ color: 'var(--helicon-muted)' }}>{d}</div>
              </div>
            ))}
          </div>
        </Exhibit>

        <Exhibit n="ii." title="Inside your IDE, over MCP" sub="the agent audits its own memory">
          <p className="text-[14px] m-0 mb-3" style={{ color: 'var(--helicon-muted)' }}>A 16-tool MCP server drops into Cursor or Claude Code. The agent pulls its own memory with provenance and flags stale context at the point of use.</p>
          <Term>{`$ `}<DIM c="# ~/.cursor/mcp.json" />{`
  `}<P c='"helicon"' />{`: { `}<CMD c='"command":"helicon","args":["mcp"]' />{` }

`}<DIM c="agent ▸" />{` load what you know about the auth refactor
`}<OK c="helicon_context ▸" />{` 6 memories, ranked (text-embedding-v4 + qwen3-rerank)
   #a1f2  "auth uses JWT rotation"   `}<DIM c="verified 3d · used 5x" />{`
   #c8e1  "sessions in Redis"        `}<DIM c="verified 41d" />{`  `}<ROT c="⚠ stale" />{`
`}<DIM c="agent ▸" />{` #c8e1 is wrong, we moved off Redis, flag it
`}<OK c="helicon_flag ▸" />{` filed as a finding; a human confirms, nothing deleted`}</Term>
        </Exhibit>

        <Exhibit n="iii." title="In the dashboard" sub="the weekly sit-down">
          <p className="text-[14px] m-0 mb-1" style={{ color: 'var(--helicon-muted)' }}><code style={{ color: 'var(--helicon-accent)' }}>helicon serve</code> → four surfaces you're looking at right now.</p>
          <div className="grid sm:grid-cols-2 gap-3 mt-3">
            {CARDS_DASH.map(([tag, h, p]) => (
              <div key={tag} className="rounded-xl border border-zinc-800/40 px-4 py-3.5" style={{ background: 'rgba(60,40,20,0.02)' }}>
                <div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-stale)' }}>{tag}</div>
                <div className="text-[16px] my-1" style={{ ...SERIF, color: 'var(--helicon-ink)' }}>{h}</div>
                <p className="text-[13px] m-0" style={{ color: 'var(--helicon-muted)' }}>{p}</p>
              </div>
            ))}
          </div>
        </Exhibit>
      </section>

      {/* QWEN STACK */}
      <section>
        <div className="text-[11px] uppercase tracking-[0.24em] mb-2" style={{ color: 'var(--helicon-muted)' }}>Built on Qwen Cloud · Alibaba Model Studio</div>
        <h2 className="text-[clamp(24px,3.2vw,32px)] m-0 mb-5" style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>The whole stack runs on Qwen, direct on Alibaba.</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          {STACK.map(([tag, h, p]) => (
            <div key={tag} className="rounded-xl border border-zinc-800/40 px-5 py-4 bg-white">
              <div className="text-[10px] uppercase tracking-[0.14em]" style={{ color: 'var(--helicon-stale)' }}>{tag}</div>
              <div className="text-[17px] my-1.5" style={{ ...SERIF, color: 'var(--helicon-ink)' }}>{h}</div>
              <p className="text-[13.5px] m-0" style={{ color: 'var(--helicon-muted)' }}>{p}</p>
            </div>
          ))}
        </div>
      </section>

      {/* QUICKSTART */}
      <section>
        <div className="text-[11px] uppercase tracking-[0.24em] mb-2" style={{ color: 'var(--helicon-muted)' }}>Quick start · 60 seconds · $0</div>
        <h2 className="text-[clamp(24px,3.2vw,32px)] m-0 mb-5" style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>Run the exam on your own stack.</h2>
        <Term>{`$ `}<CMD c="pip install -e ." />{`        `}<DIM c="# slim; add [embeddings] for local vectors" />{`
$ `}<CMD c="helicon init" />{`            `}<DIM c="# auto-detects Claude Code · Cursor · git · Obsidian" />{`
$ `}<CMD c="helicon scan" />{`            `}<DIM c="# read your memory, read-only, into cubes" />{`
$ `}<CMD c="helicon serve" />{`           `}<DIM c="# dashboard → localhost:8420" />{``}</Term>
        <p className="text-[15px] mt-6 pt-6" style={{ color: 'var(--helicon-muted)', borderTop: '1px solid var(--helicon-line)' }}>
          <strong style={{ ...SERIF, color: 'var(--helicon-ink)', fontWeight: 500 }}>Mem0 stores. Letta organizes. Zep timestamps.</strong>{' '}
          Mount Helicon is the exam, and every answer shows its receipts.
        </p>
      </section>
    </div>
  );
}
