import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../components/ModelViewer', () => ({ ModelViewer: () => <div data-testid="model-viewer" /> }));

import { CreatorPage } from '../../pages/CreatorPage';

type Session = Record<string, unknown>;

function session(overrides: Partial<Session> = {}): Session {
  return {
    session_id: 'creator-session',
    status: 'ready',
    brief: { subject: 'Cat', style: 'Cute', product_type: 'Figure' },
    image_prompt: 'A cute printable cat figure',
    generated_images: [],
    selected_image_index: null,
    model_download_url: null,
    print_file_download_url: null,
    calibrated_print_file_download_url: null,
    image_generation: { status: 'not_started' },
    model_generation: { status: 'not_started' },
    print_analysis: { status: 'not_started', report: null },
    print_file: { status: 'not_started' },
    color_calibration: { status: 'not_started' },
    events: [],
    error: null,
    ...overrides,
  };
}
function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('CreatorPage card workflow', () => {
  it('submits creative input only to the multipart prepare endpoint', async () => {
    const current = session({ image_prompt: null, brief: {} });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/sessions')) return json([current]);
      if (url.endsWith('/prepare')) return json(session());
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<CreatorPage />);
    await user.type(await screen.findByLabelText('创意描述'), '桌面猫摆件');
    await user.click(screen.getByRole('button', { name: '准备创意' }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/creator/sessions/creator-session/prepare'),
      expect.objectContaining({ method: 'POST', body: expect.any(FormData) }),
    ));
    expect(screen.queryByText(/Agent|对话|确认生成/)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('uses direct image, model and calibration actions without confirmation gates', async () => {
    const current = session({ generated_images: ['/style-1'], selected_image_index: 0, model_download_url: '/model.glb' });
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/sessions')) return json([current]);
      if (url === '/style-1') return new Response(new Blob(['image']));
      if (url.endsWith('/images/generate') || url.endsWith('/model/generate') || url.endsWith('/print/calibrate')) return json(current);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<CreatorPage />);
    await user.click(await screen.findByRole('button', { name: '重新生成风格图' }));
    await user.click(screen.getByRole('button', { name: '重做 3D 概念图' }));
    await user.click(screen.getByRole('button', { name: '开始校准' }));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/images/generate'), expect.objectContaining({ method: 'POST' }));
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/model/generate'), expect.objectContaining({ body: JSON.stringify({ image_index: 0 }) }));
      expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining('/print/calibrate'), expect.objectContaining({ body: JSON.stringify({ mode: 'white', max_colors: 1 }) }));
    });
    expect(screen.queryByText(/付款|支付|确认继续|我已了解/)).not.toBeInTheDocument();
    vi.unstubAllGlobals();
  });

  it('limits multicolor calibration to the accessible 1–8 range', async () => {
    const current = session({ generated_images: ['/style-1'], selected_image_index: 0, model_download_url: '/model.glb' });
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => String(input).endsWith('/sessions') ? json([current]) : new Response(new Blob(['image'])));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<CreatorPage />);
    await user.click(await screen.findByRole('button', { name: '多色' }));
    const slider = screen.getByRole('slider');
    expect(slider).toHaveAttribute('min', '1');
    expect(slider).toHaveAttribute('max', '8');
    fireEvent.change(slider, { target: { value: '8' } });
    expect(slider).toHaveValue('8');
    vi.unstubAllGlobals();
  });
});
