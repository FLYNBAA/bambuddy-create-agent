# BCA Virtual Printer FTP Port Migration

[中文](migration-vp-ftp-port.md) | **English**

Virtual Printer is native Bambuddy functionality, but a BCA task eventually enters the native queue, so port migration affects the complete BCA print path.

## Network models

- Linux host networking: Virtual Printer can bind required ports directly.
- Windows Docker Desktop bridge: explicitly map control, MQTT, passive FTP, and optional camera ports. The default BCA smoke override publishes only web `8012:8000`; it is not full Virtual Printer support.

## Migration steps

1. Back up the database, `DATA_DIR`, and `bca_creator_*` configuration before changing ports.
2. Stop native/container services.
3. Update Compose or Virtual Printer configuration and avoid host port conflicts.
4. In bridge mode map required FTP passive range. Non-proxy VPs receive per-instance slices; proxy VPs may need the printer's full passive range.
5. Start and check `/health`.
6. Use a non-billed sliced `.gcode.3mf` to verify native queue upload, acknowledgement, and cancellation.

## BCA relationship

BCA does not FTP-upload model 3MF directly. The Creator → task → root slicing → native Queue tail is owned by Virtual Printer/native FTPS. Do not create a second FTP service for BCA.

See the [English deployment guide](../DEPLOYMENT_BCA.md).
