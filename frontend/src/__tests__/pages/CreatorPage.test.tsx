import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { CreatorPage } from '../../pages/CreatorPage';

type Session = Record<string, unknown>;

function session(status: string): Session {
  return {
    session_id: 'creator-session',
    status,
    brief: { subject: 'Cat', style: 'Cute', product_type: 'Figure' },
    questions: [],
    image_prompt: 'Prompt',
    generated_images: [],
    selected_image_index: null,
    model_download_url: null,
    print_file_download_url: null,
    calibrated_print_file_download_url: null,
    geometry_print_file_download_url: null,
    print_analysis: { status: 'not_started', report: null },
    model_repair: { status: 'not_started' },
    print_file: { status: 'not_started' },
    geometry_status: 'not_started',
    color_calibration: { status: 'not_started' },
    conversation: [],
    events: [],
    error: null,
  };
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('CreatorPage action controls', () => {
  it.each([
    ['awaiting_image_confirmation', '确认生成四张图', '/confirm-image'],
    ['awaiting_3d_confirmation', '确认生成 GLB', '/confirm-3d'],
    ['completed', '开始打印分析', '/print/analyze'],
  ])('posts %s action to its API route', async (status, label, route) => {
    const current = session(status);
    const fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/sessions')) return json([current]);
      if (url.endsWith(route)) return json(current);
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();

    render(<CreatorPage />);
    await screen.findByRole('button', { name: label });
    await user.click(screen.getByRole('button', { name: label }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining(`/api/v1/creator/sessions/creator-session${route}`),
        expect.objectContaining({ method: 'POST' }),
      );
    });
    vi.unstubAllGlobals();
  });
});
