# BCA Slicer-API Sidecar

[中文](README.md) | **English**

The optional Slicer-API sidecar wraps OrcaSlicer or Bambu Studio CLI in HTTP. BCA does not require it: root must upload the final validated `.gcode.3mf`, which may come from this sidecar, a desktop slicer, or another compatible process.

## Flow

```text
Model 3MF / STL
  → optional slicer sidecar or desktop slicer
  → .gcode.3mf
  → root uploads to /tasks
  → BCA validates Metadata/plate_N.gcode + Metadata/slice_info.config
  → native Bambuddy queue
```

## Start

From this directory:

```bash
docker compose up -d
curl http://localhost:3003/health
```

Start the Bambu Studio profile as well:

```bash
docker compose --profile bambu up -d
curl http://localhost:3001/health
curl http://localhost:3003/health
```

Default ports:

| Service | Port |
|---|---|
| OrcaSlicer API | `3003` |
| Bambu Studio API | `3001` |

Enable Slicer API in Bambuddy Settings → Slicer and set the Sidecar URL. BCA never forwards an unvalidated model 3MF directly to a printer.

## Network and architecture

- Images are typically `linux/amd64`; ARM64 hosts can use an x86_64 sidecar host or emulation.
- The sidecar may live on a different reachable host than Bambuddy.
- Production reverse proxy, authentication, and plaintext Provider configuration remain BCA/Bambuddy concerns, not sidecar concerns.
- Sidecar output still passes BCA task sliced-file validation.

## References

- [English deployment guide](../DEPLOYMENT_BCA.md)
- [English README](../README.en.md)
- [Chinese Slicer-API guide](README.md)
