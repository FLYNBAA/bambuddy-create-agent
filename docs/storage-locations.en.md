# BCA Storage Locations and Data Layout

[中文](storage-locations.md) | **English**

BCA uses Bambuddy `DATA_DIR` and the native database. Deployment or migration must not move only one part.

```text
DATA_DIR/
├─ bca-agent/       creator session SQLite, uploads, concept images, GLB, and 3MF
├─ bca-tasks/       model 3MF awaiting root slicing
├─ archive/         Bambuddy archive and Library-related data
├─ sessions.sqlite3 / native database (per SQLite deployment layout)
└─ virtual_printer/ Virtual Printer data
```

The database also stores:

```text
bca_tasks
bca_creator_*
```

`bca_creator_*` includes plaintext Provider configuration. Back up SQLite with consistent WAL sidecars; dump the `DATABASE_URL` database for PostgreSQL. Restore matching database and `DATA_DIR` snapshots together.

Filesystem paths must not be returned through APIs. Creator artifacts download through controlled routes; Meshy public URL uses only the controlled GLB capability route.

See the [English deployment guide](../DEPLOYMENT_BCA.md).
