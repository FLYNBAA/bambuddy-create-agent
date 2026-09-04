import { useEffect, useState } from 'react';
import JSZip, { type JSZipObject } from 'jszip';
import { ImageOff, Loader2 } from 'lucide-react';

type SnapshotState =
  | { status: 'loading' }
  | { status: 'ready'; url: string; source: string }
  | { status: 'unavailable' };

interface ThreeMfSnapshotProps {
  archive: Blob;
  filename: string;
}

const IMAGE_EXTENSION = /\.(?:png|jpe?g|webp)$/i;
const SNAPSHOT_PATHS = [
  /^Metadata\/plate_1\.png$/i,
  /^Metadata\/plate_\d+\.png$/i,
  /(?:^|\/)(?:thumbnail|preview|cover)[^/]*\.(?:png|jpe?g|webp)$/i,
  /(?:^|\/)[^/]*(?:thumbnail|preview|cover)[^/]*\.(?:png|jpe?g|webp)$/i,
];
const MAX_SNAPSHOT_BYTES = 24 * 1024 * 1024;

function findSnapshot(files: Record<string, JSZipObject>): JSZipObject | undefined {
  const entries = Object.values(files).filter((entry) => !entry.dir && IMAGE_EXTENSION.test(entry.name));
  for (const pattern of SNAPSHOT_PATHS) {
    const match = entries.find((entry) => pattern.test(entry.name));
    if (match) return match;
  }
  return undefined;
}

function mediaTypeFor(path: string): string {
  if (/\.jpe?g$/i.test(path)) return 'image/jpeg';
  if (/\.webp$/i.test(path)) return 'image/webp';
  return 'image/png';
}

async function extractSnapshot(archive: Blob): Promise<{ blob: Blob; source: string } | null> {
  const zip = await JSZip.loadAsync(archive);
  const entry = findSnapshot(zip.files);
  if (!entry) return null;

  const image = await entry.async('blob');
  if (image.size > MAX_SNAPSHOT_BYTES) return null;
  return {
    blob: image.slice(0, image.size, mediaTypeFor(entry.name)),
    source: entry.name,
  };
}

/**
 * Shows the slicer's own colored plate image. This deliberately never parses
 * or renders 3MF geometry, avoiding WebGL work and server-side rendering.
 */
export function ThreeMfSnapshot({ archive, filename }: ThreeMfSnapshotProps) {
  const [state, setState] = useState<SnapshotState>({ status: 'loading' });

  useEffect(() => {
    let cancelled = false;
    let snapshotUrl: string | undefined;
    setState({ status: 'loading' });

    void extractSnapshot(archive)
      .then((snapshot) => {
        if (cancelled) return;
        if (!snapshot) {
          setState({ status: 'unavailable' });
          return;
        }
        snapshotUrl = URL.createObjectURL(snapshot.blob);
        setState({ status: 'ready', url: snapshotUrl, source: snapshot.source });
      })
      .catch(() => {
        if (!cancelled) setState({ status: 'unavailable' });
      });

    return () => {
      cancelled = true;
      if (snapshotUrl) URL.revokeObjectURL(snapshotUrl);
    };
  }, [archive]);

  if (state.status === 'loading') {
    return <div className="creator-3mf-snapshot creator-3mf-snapshot-loading" aria-live="polite"><Loader2 className="spin" size={20} /><span>Reading embedded color snapshot…</span></div>;
  }

  if (state.status === 'unavailable') {
    return <div className="creator-3mf-snapshot creator-3mf-snapshot-empty"><ImageOff size={22} /><div><strong>Embedded color snapshot unavailable</strong><p>{filename} has no supported slicer snapshot. Download the 3MF to inspect it in your slicer.</p></div></div>;
  }

  return <figure className="creator-3mf-snapshot">
    <img src={state.url} alt={`Embedded color snapshot for ${filename}`} />
    <figcaption>Embedded color snapshot · {state.source}</figcaption>
  </figure>;
}
