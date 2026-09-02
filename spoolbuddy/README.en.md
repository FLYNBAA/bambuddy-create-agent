# SpoolBuddy Hardware Development Guide

[中文](README.md) | **English**

SpoolBuddy is a Bambuddy hardware extension. BCA uses Bambuddy active manual inventory for multi-color calibration but does not depend on SpoolBuddy hardware. This guide covers NFC and scale device development.

## PN5180 NFC Reader (SPI)

| PN5180 pin | Raspberry Pi pin | GPIO | Example wire color |
|---|---:|---:|---|
| 3V3 | 1 | — | Red |
| 5V | 2 | — | Red |
| GND | 20 | — | Black |
| SCK | 23 | GPIO11 | Yellow |
| MISO | 21 | GPIO9 | Blue |
| MOSI | 19 | GPIO10 | Green |
| NSS | 16 | GPIO23 | Orange |
| BUSY | 22 | GPIO25 | White |
| RST | 18 | GPIO24 | Brown |

3V3 powers the IC and 5V powers the antenna booster; both should be connected. Never connect 5V to the 3V3 pin.

NSS uses manual GPIO23 chip-select rather than default CE0 because the PN5180 requires specific setup/hold timing. GPIO8/CE0 does not need to connect to the reader.

## Raspberry Pi setup

```bash
sudo raspi-config
# Interface Options → SPI → Enable
# Interface Options → I2C → Enable
sudo reboot
```

Verify:

```bash
ls /dev/spidev0.*
ls /dev/i2c-*
```

Add under `[all]` in `/boot/firmware/config.txt`:

```text
dtparam=i2c_arm=on
dtoverlay=spi0-0cs
```

## BCA relationship

- SpoolBuddy does not store BCA Provider credentials or creator sessions.
- BCA multi-color calibration reads active, unarchived Bambuddy `spool` rows with valid RGBA and non-empty material; it does not query the color catalog. Brand/name are matching evidence, not eligibility gates.
- SpoolBuddy can maintain inventory, but Creator receives calibration candidates through Bambuddy inventory APIs and database data. A completed multicolor mapping has non-empty `assignments` plus a final calibrated artifact.

## Developer verification

After changing the daemon, hardware mapping, or system stats:

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_spoolbuddy_system_stats.py backend\tests\unit\test_spoolbuddy_ssh.py -q
```

## References

- [Chinese SpoolBuddy guide](README.md)
- [English README](../README.en.md)
- [English deployment guide](../DEPLOYMENT_BCA.md)
