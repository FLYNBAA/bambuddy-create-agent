import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';


import { TaskListPage } from '../../pages/TaskListPage';

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

describe('TaskListPage creator task cards', () => {
  it('shows immutable creator previews and expandable customer details', async () => {
    const task = {
      id: 17,
      filename: 'calibrated.3mf',
      title: 'Cat desk figure',
      username: 'maker',
      created_by: 'root',
      created_at: '2026-09-01T12:00:00Z',
      status: 'ready_for_slicing',
      sliced_library_file_id: null,
      print_queue_item_id: null,
      customer_name: 'Ada',
      phone: '12345678',
      address: '1 Main Street',
      notes: 'Blue filament',
      style_image_preview_url: '/style.png',
      model_preview_url: '/model.glb',
      source_3mf_url: '/source.3mf',
      source_3mf_snapshot_url: '/snapshot.png',
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/api/v1/bca-tasks')) return json([task]);
      if (url.endsWith('/api/v1/printers/')) return json([]);
      if (url === '/style.png' || url === '/snapshot.png') return new Response(new Blob(['image']));
      throw new Error(`Unexpected request: ${url}`);
    });
    vi.stubGlobal('fetch', fetchMock);
    const user = userEvent.setup();
    render(<TaskListPage />);

    expect(await screen.findByRole('heading', { name: 'Cat desk figure' })).toBeInTheDocument();
    expect(screen.getByText('maker')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /GLB 模型/ })).not.toBeInTheDocument();
    expect(await screen.findByRole('button', { name: /彩色 3MF 快照/ })).toBeInTheDocument();
    await user.click(screen.getByText('配置 · 订单详情'));
    expect(screen.getByText('Ada')).toBeInTheDocument();
    expect(screen.getByText('Blue filament')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /彩色 3MF 快照/ }));
    expect(screen.getByRole('dialog', { name: '彩色 3MF 快照' })).toBeInTheDocument();
    vi.unstubAllGlobals();
  });
});
