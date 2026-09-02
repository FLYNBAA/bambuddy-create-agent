import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('../../components/ModelViewer', () => ({ ModelViewer: () => <div data-testid="model-viewer" /> }));

import { CreatorPage } from '../../pages/CreatorPage';

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('Creator API test bench', () => {
  it('invokes the brief capability without creating a Creator session', async () => {
    const fetchMock = vi.fn(async () => json({ language: 'en', brief: { subject: 'cat' }, image_prompt_ready: true, prompts: { positive_prompt: 'Positive prompt', negative_prompt: 'Negative prompt', image2_prompt: 'Image2 prompt', print_constraints: ['Complete subject'] } }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<CreatorPage />);

    await user.click(screen.getByRole('button', { name: 'Invoke module' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/creator/modules/brief/prepare',
      expect.objectContaining({ method: 'POST', headers: expect.any(Headers) }),
    ));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    expect(JSON.parse(request.body as string)).toMatchObject({ message: expect.any(String), current_brief: { subject: 'cat' } });
    expect(await screen.findByText(/Positive prompt/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Image2 style image' }));
    expect(screen.getByLabelText('Prompt')).toHaveValue('Image2 prompt');
    vi.unstubAllGlobals();
  });

  it('retries a Meshy result URL without requiring or uploading a GLB', async () => {
    const fetchMock = vi.fn(async () => json({ reused: true }));
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<CreatorPage />);

    await user.click(screen.getByRole('button', { name: 'GLB → multicolor 3MF' }));
    await user.type(screen.getByLabelText('Existing Meshy 3MF result URL'), 'https://api.meshy.ai/result.3mf');
    await user.click(screen.getByRole('button', { name: 'Invoke module' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/creator/modules/print/multicolor',
      expect.objectContaining({ method: 'POST' }),
    ));
    const request = fetchMock.mock.calls[0][1] as RequestInit;
    const body = request.body as FormData;
    expect(body.get('meshy_result_url')).toBe('https://api.meshy.ai/result.3mf');
    expect(body.get('model')).toBeNull();
    vi.unstubAllGlobals();
  });

  it('exposes every capability as an independent test target', () => {
    vi.stubGlobal('fetch', vi.fn());
    render(<CreatorPage />);
    expect(screen.getByRole('button', { name: 'Brief preparation' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Image2 style image' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Image → GLB' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GLB → multicolor 3MF' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '3MF color calibration' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'GLB print analysis' })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
