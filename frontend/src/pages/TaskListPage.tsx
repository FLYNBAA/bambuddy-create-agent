import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, Expand, FileUp, ImageOff, ListPlus, Loader2, Send, Trash2, X } from 'lucide-react';
import { getAuthToken } from '../api/client';

type Task = {
  id: number;
  filename: string;
  title?: string | null;
  username?: string | null;
  created_by: string;
  created_at: string;
  status: string;
  sliced_library_file_id: number | null;
  print_queue_item_id: number | null;
  customer_name?: string | null;
  phone?: string | null;
  address?: string | null;
  notes?: string | null;
  price?: string | null;
  style_image_preview_url?: string | null;
  model_preview_url?: string | null;
  source_3mf_url?: string | null;
  source_3mf_snapshot_url?: string | null;
};
type PrinterOption = { id: number; name: string; model?: string | null };
type Preview = { url: string; title: string };

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

function PreviewDialog({ preview, onClose }: { preview: Preview; onClose: () => void }) {
  const dialogRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab' || !dialogRef.current) return;
      const focusable = [...dialogRef.current.querySelectorAll<HTMLElement>('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')]
        .filter((element) => !element.hasAttribute('disabled'));
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      previouslyFocused?.focus();
    };
  }, [onClose]);

  return <div className="creator-preview-backdrop" role="presentation" onMouseDown={onClose}>
    <section ref={dialogRef} className="creator-preview-dialog" role="dialog" aria-modal="true" aria-labelledby="task-preview-title" onMouseDown={(event) => event.stopPropagation()}>
      <header><h2 id="task-preview-title">{preview.title}</h2><button className="icon-button" onClick={onClose} aria-label="关闭预览" autoFocus><X size={18} /></button></header>
      <img className="bca-preview-image-large" src={preview.url} alt="" />
    </section>
  </div>;
}

export function TaskListPage() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [printers, setPrinters] = useState<PrinterOption[]>([]);
  const [model, setModel] = useState<File | null>(null);
  const [sliced, setSliced] = useState<Record<number, File | null>>({});
  const [printer, setPrinter] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stylePreviews, setStylePreviews] = useState<Record<string, string>>({});
  const [snapshotPreviews, setSnapshotPreviews] = useState<Record<number, string>>({});
  const [expandedPreview, setExpandedPreview] = useState<Preview | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [taskItems, printerItems] = await Promise.all([request<Task[]>(''), listPrinters()]);
      setTasks(taskItems); setPrinters(printerItems);
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to load task list'); }
  }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  useEffect(() => {
    const urls = [...new Set(tasks.flatMap((task) => task.style_image_preview_url ? [task.style_image_preview_url] : []))];
    if (!urls.length) { setStylePreviews({}); return; }
    const controller = new AbortController();
    const objectUrls: string[] = [];
    let disposed = false;
    void Promise.allSettled(urls.map(async (url) => {
      const response = await fetch(url, { headers: authHeaders(), signal: controller.signal });
      if (!response.ok) throw new Error(`Style preview failed (${response.status})`);
      const objectUrl = URL.createObjectURL(await response.blob());
      if (disposed) { URL.revokeObjectURL(objectUrl); return null; }
      objectUrls.push(objectUrl);
      return [url, objectUrl] as const;
    })).then((results) => {
      if (!disposed) setStylePreviews(Object.fromEntries(results.flatMap((result) => result.status === 'fulfilled' && result.value ? [result.value] : [])));
    });
    return () => { disposed = true; controller.abort(); objectUrls.forEach(URL.revokeObjectURL); };
  }, [tasks]);
  useEffect(() => {
    const controller = new AbortController();
    const objectUrls: string[] = [];
    let disposed = false;
    void Promise.allSettled(tasks.map(async (task) => {
      const response = await fetch(task.source_3mf_snapshot_url || `${BASE}/${task.id}/snapshot`, { headers: authHeaders(), signal: controller.signal });
      if (!response.ok) throw new Error(`3MF snapshot failed (${response.status})`);
      const objectUrl = URL.createObjectURL(await response.blob());
      if (disposed) { URL.revokeObjectURL(objectUrl); return null; }
      objectUrls.push(objectUrl);
      return [task.id, objectUrl] as const;
    })).then((results) => {
      if (!disposed) setSnapshotPreviews(Object.fromEntries(results.flatMap((result) => result.status === 'fulfilled' && result.value ? [result.value] : [])));
    });
    return () => { disposed = true; controller.abort(); objectUrls.forEach(URL.revokeObjectURL); };
  }, [tasks]);
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
    <header><div><h1>任务清单</h1><p>校准后的 3MF、风格图和模型预览会随任务保存。上传切片文件后，任务才可进入打印队列。</p></div></header>
    <section className="bca-task-upload"><label><FileUp size={18} />添加已有校准 3MF<input type="file" accept=".3mf" onChange={(event) => setModel(event.target.files?.[0] || null)} /></label><button className="primary-button" disabled={!model || busy} onClick={() => void upload()}>{busy ? <Loader2 className="spin" size={16} /> : <ListPlus size={16} />}添加任务</button></section>
    {error && <p className="creator-error" role="alert">{error}</p>}
    <section className="bca-task-list">{tasks.map((task) => {
      const styleUrl = task.style_image_preview_url ? stylePreviews[task.style_image_preview_url] : null;
      const snapshotUrl = snapshotPreviews[task.id];
      const hasSliced = Boolean(task.sliced_library_file_id);
      const queued = Boolean(task.print_queue_item_id);
      return <article key={task.id} className="bca-task-card">
        <div className="bca-task-meta"><div><p className="bca-task-owner">{task.username || task.created_by || 'root'}</p><h2>{task.title || task.filename}</h2><p>{task.status.replaceAll('_', ' ')} · {new Date(task.created_at).toLocaleString()}</p></div><div className="bca-task-actions"><button onClick={() => void download(task)}><Download size={16} />下载源文件</button><button onClick={() => void remove(task.id)} disabled={busy} aria-label={`删除任务 ${task.title || task.filename}`}><Trash2 size={16} /></button></div></div>
        <div className="bca-task-previews">
          {styleUrl && <button className="bca-task-preview bca-style-preview" onClick={() => setExpandedPreview({ url: styleUrl, title: '已选风格图' })}><img src={styleUrl} alt="已选风格图" /><span><Expand size={15} />风格图</span></button>}
          {snapshotUrl ? <button className="bca-task-preview" onClick={() => setExpandedPreview({ url: snapshotUrl, title: '彩色 3MF 快照' })}><img src={snapshotUrl} alt={`${task.title || task.filename} 的彩色 3MF 快照`} /><span><Expand size={15} />彩色 3MF 快照</span></button> : <div className="bca-task-preview bca-task-snapshot-unavailable"><ImageOff size={19} /><span>3MF 快照不可用</span></div>}
        </div>
        <details className="bca-task-details"><summary>配置 · 订单详情</summary><dl><div><dt>客户</dt><dd>{task.customer_name || '未填写'}</dd></div><div><dt>电话</dt><dd>{task.phone || '未填写'}</dd></div><div><dt>地址</dt><dd>{task.address || '未填写'}</dd></div><div><dt>价格</dt><dd>{task.price || '待定'}</dd></div>{task.notes && <div><dt>备注</dt><dd>{task.notes}</dd></div>}</dl></details>
        <div className="bca-task-process">{hasSliced ? <p className="bca-task-queued">切片文件已关联{queued ? '，已进入打印队列。' : '，请选择打印机后加入队列。'}</p> : <label><FileUp size={16} />上传切片后的 .gcode.3mf<input type="file" accept=".gcode.3mf,.3mf" onChange={(event) => setSliced((current) => ({ ...current, [task.id]: event.target.files?.[0] || null }))} /></label>}{!hasSliced && <button disabled={!sliced[task.id] || busy} onClick={() => void attachSliced(task.id)}>验证并关联切片文件</button>}{hasSliced && !queued && <><select value={printer[task.id] || ''} onChange={(event) => setPrinter((current) => ({ ...current, [task.id]: event.target.value }))} aria-label={`选择 ${task.title || task.filename} 的打印机`}><option value="">选择打印机</option>{printers.map((item) => <option key={item.id} value={item.id}>{item.name}{item.model ? ` · ${item.model}` : ''}</option>)}</select><button disabled={busy} onClick={() => void queue(task.id)}><Send size={16} />加入队列</button></>}</div>
      </article>;
    })}{!tasks.length && <div className="creator-empty">还没有任务。完成创作流程后可在此查看任务。</div>}</section>
    {expandedPreview && <PreviewDialog preview={expandedPreview} onClose={() => setExpandedPreview(null)} />}
  </main>;
}
