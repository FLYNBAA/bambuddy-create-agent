import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import JSZip from 'jszip';
import { ThreeMfSnapshot } from '../../components/ThreeMfSnapshot';

const COLOR_SNAPSHOT = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a,
  0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44, 0x52,
]);

async function threeMf(entries: Record<string, Uint8Array>): Promise<Blob> {
  const zip = new JSZip();
  for (const [path, content] of Object.entries(entries)) zip.file(path, content);
  return zip.generateAsync({ type: 'blob' });
}

describe('ThreeMfSnapshot', () => {
  beforeEach(() => {
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:embedded-snapshot'),
      revokeObjectURL: vi.fn(),
    });
  });

  it('shows the embedded colored plate snapshot without constructing a 3D renderer', async () => {
    const archive = await threeMf({ 'Metadata/plate_1.png': COLOR_SNAPSHOT });
    render(<ThreeMfSnapshot archive={archive} filename="calibrated.3mf" />);

    const image = await screen.findByAltText('Embedded color snapshot for calibrated.3mf');
    expect(image).toHaveAttribute('src', 'blob:embedded-snapshot');
    expect(screen.getByText('Embedded color snapshot · Metadata/plate_1.png')).toBeInTheDocument();
  });

  it('explains when a 3MF has no embedded slicer snapshot', async () => {
    const archive = await threeMf({ '3D/3dmodel.model': new Uint8Array([1, 2, 3]) });
    render(<ThreeMfSnapshot archive={archive} filename="model.3mf" />);

    expect(await screen.findByText('Embedded color snapshot unavailable')).toBeInTheDocument();
    expect(screen.getByText(/Download the 3MF to inspect it in your slicer/)).toBeInTheDocument();
  });
});
