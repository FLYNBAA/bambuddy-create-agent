import { useEffect, useState } from 'react';
import { KeyRound, Loader2, Save, ShieldCheck } from 'lucide-react';
import { getAuthToken } from '../api/client';

type Config = {
  deepseek_api_key: string;
  deepseek_base_url: string;
  deepseek_model: string;
  image_api_key: string;
  image_base_url: string;
  image_model: string;
  image_quality: string;
  tencent_secret_id: string;
  tencent_secret_key: string;
  tencent_region: string;
  meshy_api_key: string;
  meshy_base_url: string;
  meshy_model_input_mode: string;
  app_public_base_url: string;
  configured: Record<string, boolean>;
};

const secretFields = [
  ['deepseek_api_key', 'DeepSeek API Key'],
  ['image_api_key', 'Image API Key'],
  ['tencent_secret_id', 'Tencent Secret ID'],
  ['tencent_secret_key', 'Tencent Secret Key'],
  ['meshy_api_key', 'Meshy API Key'],
] as const;

const providerFields = [
  ['deepseek_base_url', 'DeepSeek Base URL'],
  ['deepseek_model', 'DeepSeek Model'],
  ['image_base_url', 'Image Base URL'],
  ['image_model', 'Image Model'],
  ['image_quality', 'Image Quality'],
  ['tencent_region', 'Tencent Region'],
  ['meshy_base_url', 'Meshy Base URL'],
  ['meshy_model_input_mode', 'Meshy Input Mode'],
  ['app_public_base_url', 'BCA Public Base URL'],
] as const;

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = getAuthToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  if (init?.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`/api/v1/creator${path}`, { ...init, headers });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Configuration request failed');
  }
  return response.json() as Promise<T>;
}

export function CreatorSettingsPage() {
  const [config, setConfig] = useState<Config | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void api<Config>('/config').then(setConfig).catch((err) => setError(err.message)); }, []);

  async function save() {
    if (!config) return;
    setBusy(true);
    setError(null);
    try {
      setConfig(await api<Config>('/config', { method: 'PUT', body: JSON.stringify(config) }));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  }

  if (!config) return <main className="bca-task-page"><p>{error || '加载 Agent 服务配置…'}</p></main>;

  const set = (field: keyof Config, value: string) => setConfig((current) => current ? { ...current, [field]: value } : current);

  return <main className="bca-task-page">
    <header><div><span className="eyebrow">BCA SERVICE CONFIG</span><h1>Agent 服务配置</h1><p>所有 Provider 参数和密钥均以明文从网页读取、持久化并热加载。拥有 Agent 服务配置读取或修改权限的用户、数据库备份和浏览器都可见这些值。</p></div></header>
    <section className="bca-config-grid">{Object.entries(config.configured).map(([name, ready]) => <div className="bca-config-status" key={name}><ShieldCheck size={17} /><span>{name}</span><strong className={ready ? 'ready' : 'missing'}>{ready ? '已配置' : '未配置'}</strong></div>)}</section>
    <section className="bca-config-form">
      <div className="bca-config-section"><h2>明文 Provider 密钥</h2><p>保存后立即写入 Bambuddy 数据库并重建 Agent Provider。请仅在受控管理环境使用。</p>{secretFields.map(([field, label]) => <label key={field}>{label}<input type="text" autoComplete="off" value={config[field]} onChange={(event) => set(field, event.target.value)} /></label>)}</div>
      <div className="bca-config-section"><h2>Provider 运行参数</h2>{providerFields.map(([field, label]) => <label key={field}>{label}<input value={config[field]} onChange={(event) => set(field, event.target.value)} /></label>)}</div>
    </section>
    {error && <p className="creator-error" role="alert">{error}</p>}
    <button className="primary-button" disabled={busy} onClick={() => void save()}>{busy ? <Loader2 className="spin" size={16} /> : <Save size={16} />}保存并热加载明文配置</button>
    <p className="bca-secret-note"><KeyRound size={16} />密钥明文会通过配置 API 返回，并持久化在 Bambuddy settings 表中；更改后当前 Agent 实例立即重建。</p>
  </main>;
}
