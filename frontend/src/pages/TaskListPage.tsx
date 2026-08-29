import { useCallback, useEffect, useState } from 'react';
import { Download, FileUp, ListPlus, Loader2, Send, Trash2 } from 'lucide-react';
import { getAuthToken } from '../api/client';

type Task = {
  id: number;
  filename: string;
  status: string;
  sliced_library_file_id: number | null;
  print_queue_item_id: number | null;
  created_by: string;
  created_at: string;
};
type PrinterOption = { id: number; name: string; model?: string | null };

const BASE = '/api/v1/bca-tasks';

function authHeaders(init?: HeadersInit) {
  const headers = new Headers(init);
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE}${path}`, { ...init, headers: authHeaders(init?.headers) });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Task request failed (${response.status})`);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

async function listPrinters(): Promise<PrinterOption[]> {
  const response = await fetch('/api/v1/printers/', { headers: authHeaders() });
  if (!response.ok) throw new Error('Unable to load printers');
  return response.json() as Promise<PrinterOption[]>;
}

async function downloadTaskSource(task: Task) {
  const response = await fetch(`${BASE}/${task.id}/source`, { headers: authHeaders() });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Task download failed (${response.status})`);
  }
  const objectUrl = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = objectUrl;
  link.download = task.filename;
  link.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 0);
}

export function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [printers, setPrinters] = useState<PrinterOption[]>([]);
  const [model, setModel] = useState<File | null>(null);
  const [sliced, setSliced] = useState<Record<number, File | null>>({});
  const [printer, setPrinter] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [taskItems, printerItems] = await Promise.all([request<Task[]>(''), listPrinters()]);
      setTasks(taskItems); setPrinters(printerItems);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load task list'); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);

  async function upload() {
    if (!model) return;
    setBusy(true); setError(null);
    try { const form = new FormData(); form.append('file', model); await request<Task>('', { method: 'POST', body: form }); setModel(null); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Upload failed'); }
    finally { setBusy(false); }
  }

  async function attachSliced(taskId: number) {
    const file = sliced[taskId]; if (!file) return;
    setBusy(true); setError(null);
    try { const form = new FormData(); form.append('file', file); await request<Task>(`/${taskId}/sliced`, { method: 'POST', body: form }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Sliced file validation failed'); }
    finally { setBusy(false); }
  }

  async function queue(taskId: number) {
    const printerId = Number(printer[taskId]);
    if (!Number.isInteger(printerId) || printerId <= 0) { setError('请选择打印机'); return; }
    setBusy(true); setError(null);
    try { await request<Task>(`/${taskId}/queue`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ printer_id: printerId }) }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Queue submission failed'); }
    finally { setBusy(false); }
  }

  async function download(task: Task) {
    setBusy(true); setError(null);
    try { await downloadTaskSource(task); }
    catch (err) { setError(err instanceof Error ? err.message : 'Task download failed'); }
    finally { setBusy(false); }
  }

  async function remove(taskId: number) {
    if (!window.confirm('永久删除此任务及其待处理源文件？')) return;
    setBusy(true); setError(null);
    try { await request<void>(`/${taskId}`, { method: 'DELETE' }); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Delete failed'); }
    finally { setBusy(false); }
  }

  return <main className="bca-task-page">
    <header><div><span className="eyebrow">BCA TASK LIST</span><h1>任务清单</h1><p>仅将校准后的模型放入任务；root 上传切片后的 `.gcode.3mf` 后才能进入原生打印队列。</p></div></header>
    <section className="bca-task-upload"><label><FileUp size={18} />添加已校准模型 3MF<input type="file" accept=".3mf" onChange={(event) => setModel(event.target.files?.[0] || null)} /></label><button className="primary-button" disabled={!model || busy} onClick={() => void upload()}>{busy ? <Loader2 className="spin" size={16} /> : <ListPlus size={16} />}添加任务</button></section>
    {error && <p className="creator-error" role="alert">{error}</p>}
    <section className="bca-task-list">{tasks.map((task) => <article key={task.id} className="bca-task-card"><div className="bca-task-meta"><div><h2>{task.filename}</h2><p>{task.created_by || 'root'} · {new Date(task.created_at).toLocaleString()} · {task.status.replaceAll('_', ' ')}</p></div><div className="bca-task-actions"><button onClick={() => void download(task)}><Download size={16} />下载</button><button onClick={() => void remove(task.id)} aria-label="删除任务"><Trash2 size={16} /></button></div></div>{task.status !== 'queued' && <div className="bca-task-process"><label><FileUp size={16} />{sliced[task.id]?.name || '上传切片 .gcode.3mf'}<input type="file" accept=".3mf" onChange={(event) => setSliced((current) => ({ ...current, [task.id]: event.target.files?.[0] || null }))} /></label><button disabled={!sliced[task.id] || busy || task.status === 'ready_for_queue'} onClick={() => void attachSliced(task.id)}>处理并验证切片</button>{task.status === 'ready_for_queue' && <div className="bca-task-queue"><select value={printer[task.id] || ''} onChange={(event) => setPrinter((current) => ({ ...current, [task.id]: event.target.value }))}><option value="">选择打印机</option>{printers.map((item) => <option key={item.id} value={item.id}>{item.name}{item.model ? `（${item.model}）` : ''}</option>)}</select><button disabled={busy} onClick={() => void queue(task.id)}><Send size={16} />提交原生队列</button></div>}</div>}{task.status === 'queued' && <p className="bca-task-queued">已交给 Bambuddy 原生队列处理。</p>}</article>)}</section>
  </main>;
}
