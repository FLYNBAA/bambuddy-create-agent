# BCA Windows Installer Build

[中文](README.md) | **English**

This directory builds the BCA Windows `.exe` installer. Build it from the current `bambuddy-create-agent` working tree; an upstream Bambuddy prebuilt installer does not contain BCA functionality.

## Installer architecture

```text
Install directory: C:\Program Files\Bambuddy\
Data directory:    C:\ProgramData\Bambuddy\data\
Log directory:     C:\ProgramData\Bambuddy\logs\
Service:           NSSM-managed FastAPI/Uvicorn
Browser entry:     http://localhost:8000
```

BCA artifacts are stored under `DATA_DIR`:

```text
bca-agent/   creator sessions and artifacts
bca-tasks/   task source files awaiting slicing
```

Plaintext Provider configuration is stored in native Bambuddy `bca_creator_*` settings. Updates, uninstall, migration, and backup must keep the database and data together.

## Prerequisites

- Windows 10/11 x64 or a GitHub Windows runner;
- Python 3.11+;
- Node.js 22 LTS and npm;
- Inno Setup 6;
- Current BCA fork checkout;
- Installed BCA Python and frontend dependencies.

## Build

From the repository root:

```cmd
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
npm --prefix frontend ci
npm --prefix frontend run build
cd installers\windows
python build.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" bambuddy.iss
```

Output:

```text
installers\windows\build\output\bambuddy-windows-setup.exe
```

## Post-install checks

1. Open `http://localhost:8000` and complete administrator Setup.
2. Enter or confirm plaintext Provider configuration at `/creator/settings`.
3. Check `/health`.
4. Add printers by LAN IP where required by Windows networking.
5. Never trigger billed Providers automatically from the installer. Use approved smoke only through the deployment guide.

## Windows constraints

- Virtual Printer ports such as 322/990/8883 can trigger Firewall rules.
- Virtual Printer, SSDP, and Docker bridge are different network models. For Docker Desktop, see the [English deployment guide](../../DEPLOYMENT_BCA.md).
- Data recovery requires the native database, `DATA_DIR`, and `bca_creator_*` configuration together.

## References

- [English deployment guide](../../DEPLOYMENT_BCA.md)
- [Updating BCA](../../UPDATING.en.md)
- [English engineering contract](../../AGENTS.md)
