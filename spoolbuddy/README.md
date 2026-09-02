# SpoolBuddy 硬件开发说明

[English](README.en.md) | **中文**

SpoolBuddy 是 Bambuddy 的硬件扩展；BCA 使用 Bambuddy 活动手动耗材库做多色校准，但不依赖 SpoolBuddy 硬件。以下说明用于构建或维护 NFC/称重设备。

## PN5180 NFC Reader（SPI）

| PN5180 引脚 | Raspberry Pi 引脚 | GPIO | 线色示例 |
|---|---:|---:|---|
| 3V3 | 1 | — | 红 |
| 5V | 2 | — | 红 |
| GND | 20 | — | 黑 |
| SCK | 23 | GPIO11 | 黄 |
| MISO | 21 | GPIO9 | 蓝 |
| MOSI | 19 | GPIO10 | 绿 |
| NSS | 16 | GPIO23 | 橙 |
| BUSY | 22 | GPIO25 | 白 |
| RST | 18 | GPIO24 | 棕 |

3V3 为 IC 供电，5V 为天线 booster 供电；两者都应连接。绝不能将 5V 接到 3V3 引脚。

NSS 使用 GPIO23 的手动 chip-select，而不是默认 CE0。原因是 PN5180 对 setup/hold 时序有要求；GPIO8/CE0 不需要接到 reader。

## Raspberry Pi 设置

```bash
sudo raspi-config
# Interface Options → SPI → Enable
# Interface Options → I2C → Enable
sudo reboot
```

确认：

```bash
ls /dev/spidev0.*
ls /dev/i2c-*
```

在 `/boot/firmware/config.txt` 的 `[all]` 添加：

```text
dtparam=i2c_arm=on
dtoverlay=spi0-0cs
```

## BCA 关系

- SpoolBuddy 不是 BCA Provider 凭据或 creator session 的存储位置。
- BCA 多色校准读取 Bambuddy 活动、未归档、具有有效 RGBA 与非空 material 的 `spool` 行；不查询颜色目录。品牌/名称是匹配依据，不是候选资格门。
- SpoolBuddy 可帮助维护耗材库存，但 Creator 仍通过 Bambuddy inventory API 和数据库取得校准候选。完成的多色映射必须具有非空 `assignments` 和最终校准产物。

## 开发验证

在更改 SpoolBuddy daemon、硬件映射或系统统计后运行相关测试：

```powershell
$env:PYTHONPATH = "."
.\.venv\Scripts\python.exe -m pytest backend\tests\unit\test_spoolbuddy_system_stats.py backend\tests\unit\test_spoolbuddy_ssh.py -q
```

## 相关文档

- [English SpoolBuddy guide](README.en.md)
- [中文 BCA README](../README.md)
- [中文部署指南](../DEPLOYMENT_BCA.zh-CN.md)
