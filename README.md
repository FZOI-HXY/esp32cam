# MobileEye - ESP32-CAM 移动图像采集系统

**MobileEye**（移动之眼）—— 将 ESP32-CAM 绑在小车上，实现 WiFi 实时图像采集与远程控制。支持 MJPEG 实时流预览、高分辨率拍照、闪光灯控制、智能相册管理。

```
┌─────────────────┐      HTTP       ┌──────────────┐       ┌──────────┐
│  ESP32-CAM 设备端 │ ───────────►  │  Flask 服务端  │ ◄──── │  浏览器  │
│  (Arduino C++)   │  POST /api/raw  │  (Python 3)   │       │ (HTML5)  │
│  预览流 ~10fps   │  GET/POST/flash │  MJPEG 流     │       │ 实时预览 │
│  高分辨率拍照     │                 │  相册管理      │       │ 相册浏览 │
│  闪光灯控制      │                 │  状态持久化    │       │ 照片上传 │
└─────────────────┘                 └──────────────┘       └──────────┘
```

## 项目结构

```
esp32cam/
├── README.md                          # 本文件
├── docs/                              # 文档归档
│   └── superpowers/plans/             # 计划与总结文档
│       ├── 2026-06-27-project-architecture-overview.md
│       ├── 2026-06-28-refactor-summary.md
│       ├── 2026-06-28-structure-optimization-summary.md
│       └── 2026-06-28-performance-optimization.md
└── photo1/photo/                      # 项目主目录
    ├── photo-upload-system/           # 主系统
    │   ├── README.md                  # 详细使用说明（API 文档、快速开始等）
    │   ├── backend/                   # Flask 后端
    │   │   ├── app.py                 # 应用入口
    │   │   ├── state.py               # 状态持久化
    │   │   ├── data/                  # 数据目录（uploads/captures/album）
    │   │   ├── templates/             # 前端页面
    │   │   └── tests/                 # pytest 测试（21 项）
    │   ├── firmware/                  # ESP32-CAM 固件
    │   │   └── esp32cam_unified/      # 统一固件（config.h + .ino）
    │   └── scripts/                   # 启动脚本与工具
    ├── server.js                      # Node.js 备选服务（仅上传）
    └── .gitignore
```

## 快速开始

### 1. 启动后端

```bash
cd photo1/photo/photo-upload-system/backend
pip install -r requirements.txt
python app.py
```

或用启动脚本：

```powershell
cd photo1/photo/photo-upload-system
.\scripts\start_server.ps1
```

访问 `http://localhost:5000`。

### 2. 烧录固件到 ESP32-CAM

1. 安装 [Arduino IDE](https://www.arduino.cc/en/software)，添加 ESP32 开发板支持
2. 打开 `firmware/esp32cam_unified/esp32cam_unified.ino`
3. 编辑 `config.h`，配置 WiFi 与服务器地址：

```c
#define WIFI_SSID     "你的WiFi名称"
#define WIFI_PASSWORD "你的WiFi密码"
#define SERVER_IP     "192.168.1.x"
#define SERVER_PORT   5000
```

4. 选择开发板：**AI Thinker ESP32-CAM**，烧录
5. 串口输出 `[BOOT] ESP32-CAM 统一固件启动` 即成功

### 3. 运行测试

```bash
cd photo1/photo/photo-upload-system/backend
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

## 功能特性

| 功能 | 说明 |
|------|------|
| **MJPEG 实时预览** | threading.Event 唤醒，新帧延迟 < 1ms |
| **高分辨率拍照** | 1600x1200，拍照按钮触发 |
| **闪光灯控制** | 板载 LED 补光，状态持久化 |
| **相册管理** | 浏览、选择、删除，文件存在性缓存 |
| **外部上传** | 浏览器本地上传照片 |
| **状态持久化** | JSON 原子写入，重启不丢失 |
| **SSRF 防护** | 拍照指令仅允许私有 IP 段 |

## 技术栈

| 层 | 技术 |
|----|------|
| 设备端 | C++ / Arduino / esp32-camera / FreeRTOS |
| 服务端 | Python 3 / Flask 3.0 / threading.Event |
| 前端 | 原生 HTML5 / CSS3 / JavaScript |
| 测试 | pytest（21 项，TDD 驱动） |
| 通信 | HTTP（POST raw JPEG / multipart / JSON） |

## 文档索引

| 文档 | 内容 |
|------|------|
| [photo-upload-system/README.md](photo1/photo/photo-upload-system/README.md) | 详细使用说明、API 文档、目录说明 |
| [docs/superpowers/plans/2026-06-27-project-architecture-overview.md](docs/superpowers/plans/2026-06-27-project-architecture-overview.md) | 架构总览、数据流、模块职责 |
| [docs/superpowers/plans/2026-06-28-refactor-summary.md](docs/superpowers/plans/2026-06-28-refactor-summary.md) | 重构说明：MJPEG 流、状态持久化、目录分离、固件整合 |
| [docs/superpowers/plans/2026-06-28-structure-optimization-summary.md](docs/superpowers/plans/2026-06-28-structure-optimization-summary.md) | 目录结构优化对比 |
| [docs/superpowers/plans/2026-06-28-performance-optimization.md](docs/superpowers/plans/2026-06-28-performance-optimization.md) | 性能优化计划（Event 唤醒、缓存、并发等） |
| [docs/superpowers/plans/2026-06-27-bug-fixes.md](docs/superpowers/plans/2026-06-27-bug-fixes.md) | 早期 Bug 修复记录 |
| [docs/superpowers/plans/2026-06-27-fix-report.md](docs/superpowers/plans/2026-06-27-fix-report.md) | 修复报告 |
| [docs/superpowers/plans/2026-06-27-refactor.md](docs/superpowers/plans/2026-06-27-refactor.md) | 早期重构计划 |

## 安全

- **SSRF 防护**：拍照指令仅允许私有 IP 段（127.x.x.x、192.168.x.x、10.x.x.x、172.16-31.x.x）
- **文件类型校验**：上传文件后缀白名单
- **文件大小限制**：最大 32MB

## 许可

MIT