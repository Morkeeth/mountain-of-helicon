import { useEffect, useRef, useState } from 'react';
type Task = { id: string; project: string; text: string };
type Plan = { acceptance: string; record: unknown; snapshot: unknown; log: string; profile: string; task: Task; limit: string };
export function ComparisonHandoff({ item, against, receipt }: { item: string; against: string; receipt: string }) {
  const [profile, setProfile] = useState('');
  const [tasks, setTasks] = useState<Task[]>([]);
  const [task, setTask] = useState('');
  const [at, setAt] = useState('');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const sequence = useRef(0);
  useEffect(() => { sequence.current++; setTasks([]); setTask(''); setPlan(null); setMessage(''); }, [profile, item, against, receipt]);
  useEffect(() => { sequence.current++; setPlan(null); }, [task]);
  async function action(kind: 'tasks' | 'preview' | 'commit') {
    const seq = ++sequence.current; setBusy(true); setMessage('');
    const time = kind === 'preview' ? new Date().toISOString().replace(/\.\d{3}Z$/, 'Z') : at;
    if (kind === 'preview') setAt(time);
    try {
      const response = await fetch(kind === 'tasks' ? `/api/judge-compare/handoff/tasks?${new URLSearchParams({profile})}` : `/api/judge-compare/handoff/${kind}`, kind === 'tasks' ? { headers: {'X-Helicon-Local':'1'} } : {
        method:'POST', headers:{'X-Helicon-Local':'1','Content-Type':'application/json'}, body:JSON.stringify({item,against,receipt,profile,task_id:task,prepared_at:time,acceptance:kind==='commit'?plan?.acceptance:undefined}) });
      if (!response.ok) throw Error('Handoff refused. Reload the task list and inspect current sources and destination. No automatic retry.');
      const data = await response.json(); if (seq !== sequence.current) return;
      if (kind === 'tasks') { setTasks(data.tasks); setTask(''); }
      else if (kind === 'preview') setPlan(data);
      else { setPlan(null); setMessage(`Returned to ZUP → For review → ${data.task.text}. Profile: ${data.profile}. Record: ${data.id}. Open the native app using this profile; existing human decisions are unchanged.`); }
    } catch(e) { if(seq === sequence.current) { setPlan(null);setMessage(e instanceof Error?e.message:'Handoff unavailable.'); } }
    finally { if(seq === sequence.current)setBusy(false); }
  }
  return <section aria-label="Return comparison to ZUP" className="border-t mt-4 pt-3 space-y-3">
    <strong>Return this comparison to ZUP</strong>
    <p>Attach a local historical comparison to an existing task. No memory text is copied. The pair estimate never becomes task-completion support.</p>
    <label className="block">Existing ZUP profile directory<input aria-label="ZUP profile" className="block w-full border rounded p-2 bg-white text-black" value={profile} disabled={busy} onChange={e=>setProfile(e.target.value)} /></label>
    <button className="underline" disabled={busy || !profile} onClick={()=>void action('tasks')}>Load tasks from this profile</button>
    <label className="block">Destination task<select aria-label="Destination task" className="block w-full border rounded p-2 bg-white text-black" value={task} disabled={busy} onChange={e=>setTask(e.target.value)}><option value="">Choose explicitly</option>{tasks.map(t=><option key={t.id} value={t.id}>{t.project} · {t.text}</option>)}</select></label>
    <button className="underline" disabled={busy || !task} onClick={()=>void action('preview')}>Inspect exact local handoff</button>
    {plan && <div className="space-y-2"><p className="break-all">Profile: {plan.profile}<br/>Append to: {plan.log}<br/>Task: {plan.task.text}</p><pre aria-label="Exact local handoff" className="text-xs whitespace-pre-wrap break-words border p-2">{JSON.stringify({record:plan.record,snapshot:plan.snapshot},null,2)}</pre><p>{plan.limit}</p><button className="border p-2 rounded" disabled={busy} onClick={()=>void action('commit')}>Confirm local return to this task</button></div>}
    {message && <p role="status" className="break-words">{message}</p>}
  </section>;
}
