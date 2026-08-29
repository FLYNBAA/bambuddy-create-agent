import { useEffect, useState } from 'react';
import { KeyRound, Loader2, Save, ShieldCheck } from 'lucide-react';
import { getAuthToken } from '../api/client';

type Config = {
  deepseek_base_url: string; deepseek_model: string; image_base_url: string; image_model: string;
  image_quality: string; meshy_model_input_mode: string; app_public_base_url: string; configured: Record<string, boolean>;
};

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers); const token = getAuthToken(); if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api/v1/creator${path}`, { ...init, headers });
  if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || 'Configuration request failed'); }
  return response.json() as Promise<T>;
}

export function CreatorSettingsPage() {
  const [config, setConfig] = useState<Config | null>(null); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { void api<Config>('/config').then(setConfig).catch((err) => setError(err.message)); }, []);
  async function save() { if (!config) return; setBusy(true); setError(null); try { setConfig(await api<Config>('/config', { method: 'PUT', body: JSON.stringify(config) })); } catch (err) { setError(err instanceof Error ? err.message : 'Save failed'); } finally { setBusy(false); } }
  if (!config) return <main className="bca-task-page"><p>{error || '加载 Agent 服务配置…'}</p></main>;
  const set = (field: keyof Config, value: string) => setConfig((current) => current ? { ...current, [field]: value } : current);
  return <main className="bca-task-page"><header><div><span className="eyebrow">BCA SERVICE CONFIG</span><h1>Agent 服务配置</h1><p>模型端点和模型名可以热更新；API 密钥仅由环境变量或容器 Secret 注入，绝不通过网页回传或显示。</p></div></header><section className="bca-config-grid">{Object.entries(config.configured).map(([name, ready]) => <div className="bca-config-status" key={name}><ShieldCheck size={17} /><span>{name}</span><strong className={ready ? 'ready' : 'missing'}>{ready ? '已配置' : '未配置'}</strong></div>)}</section><section className="bca-config-form">{([['deepseek_base_url', 'DeepSeek Base URL'], ['deepseek_model', 'DeepSeek Model'], ['image_base_url', 'Image Base URL'], ['image_model', 'Image Model'], ['image_quality', 'Image Quality'], ['meshy_model_input_mode', 'Meshy Input Mode'], ['app_public_base_url', 'BCA Public Base URL']] as const).map(([field, label]) => <label key={field}>{label}<input value={config[field] as string} onChange={(event) => set(field, event.target.value)} /></label>)}</section>{error && <p className="creator-error">{error}</p>}<button className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? <Loader2 className="spin" size={16} /> : <Save size={16} />}热更新非敏感配置</button><p className="bca-secret-note"><KeyRound size={16} />密钥状态只显示是否存在；修改密钥后请通过部署环境更新并重启服务。</p></main>;
}
