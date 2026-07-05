# MobileEye (ESP32-CAM) 移动图像采集系统架构总览

> **文档目的:** 通览整个项目，梳理架构、模块职责与数据流，为后续开发、维护和重构提供清晰的认知基础。

**项目目标:** 基于 ESP32-CAM 硬件搭建一套"实时预览 + 高分辨率拍照 + 相册管理"的端到端移动图像采集系统（MobileEye）。

**架构概要:** 采用经典的「设备端 (ESP32-CAM) ↔ 服务端 (Flask) ↔ 浏览器前端」三层结构。ESP32-CAM 通过 HTTP POST 把 JPEG 帧推送到 Flask 服务端；服务端在内存中维护最新预览帧，并把高分辨率拍照帧落盘到 `uploads/`；浏览器通过轮询 `/api/frame` 拉取预览，通过 `/api/capture` 下发拍照指令。

**技术栈:**
- 设备端: C++ / Arduino 框架 / esp32-camera 驱动 / FreeRTOS（双核任务分配）
- 服务端: Python 3 + Flask 3.0
- 前端: 原生 HTML/CSS/JavaScript + Ant Design reset.css
- 备选服务端: Node.js + Express + Multer（仅简单上传，无流式预览）
- 通信: HTTP（POST 原始 JPEG / multipart 表单 / JSON 控制）

---

## 一、顶层目录结构

```
f:\esp32cam\
└── photo1\
    └── photo\                          # 项目实际根目录
        ├── server.js                   # Node.js 备选上传服务（简单版）
        ├── package.json (隐含)
        ├── public\
        │   └── upload.html             # Node 服务对应的上传页
        ├── uploads\                    # Node 服务的上传目录
        ├── start.bat                   # Node 服务启动脚本
        ├── test.py                     # Flask 环境自检脚本
        ├── test_env.bat                # 环境变量测试脚本
        └── photo-upload-system\        # ★ 主系统目录
            ├── backend\                # Flask 服务端
            ├── esp32-cam\              # ESP32-CAM 固件（多版本）
            ├── bluetooth_controller.py # PC 端蓝牙控制工具
            ├── start_server.bat        # Windows 启动脚本
            ├── start_server.ps1        # PowerShell 启动脚本（推荐）
            ├── start_server_simple.ps1 # 精简启动脚本
            └── 创建快捷方式.bat
```

> 注意：项目存在**两套并行的服务端实现**——`server.js`（Node，仅上传）和 `backend/app.py`（Flask，功能完整）。主系统是 Flask 版本。

---

## 二、核心子系统：Flask 服务端（`photo-upload-system/backend/`）

### 2.1 文件清单

| 文件 | 职责 |
|------|------|
| [app.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py) | Flask 应用入口，承载全部路由与业务逻辑（单文件架构） |
| [requirements.txt](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/requirements.txt) | Python 依赖声明（Flask 3.0 / Werkzeug / Flask-SocketIO） |
| `templates/streaming_simple.html` | ★ 默认首页，实时监控 + 拍照 + 相册（功能最全） |
| `templates/streaming.html` | 基于 Socket.IO 的流式版本（未默认启用） |
| `templates/upload.html` | 纯文件上传页面 |
| `uploads/` | 高分辨率拍照落盘目录 |

### 2.2 全局状态（模块级变量）

[app.py:18-37](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py#L18-L37) 集中定义了服务端的内存状态：

| 变量 | 类型 | 作用 |
|------|------|------|
| `latest_frame` | bytes \| None | 最新预览帧（原始 JPEG） |
| `latest_frame_time` | float | 预览帧时间戳 |
| `esp32_cam_ip` | str \| None | 缓存的 ESP32-CAM IP 地址 |
| `esp32_cam_ip_time` | float | IP 缓存时间戳（60 秒有效期） |
| `is_capturing` | bool | 拍照进行中标志 |
| `last_capture_time` | float | 拍照开始时间（30 秒超时） |
| `last_captured_photo` | dict \| None | 最近一次拍照结果元数据 |
| `flash_enabled` | bool | 闪光灯开关状态 |
| `saved_photos` | list[dict] | 相册照片列表（仅元数据，不持久化） |

> ⚠️ **架构风险提示：** 所有状态均为进程内变量，**未持久化**，服务重启即丢失；`saved_photos` 与磁盘文件可能不一致。

### 2.3 路由总览

| 方法 | 路径 | 功能 | 调用方 |
|------|------|------|--------|
| GET | `/` | 渲染 `streaming_simple.html` | 浏览器 |
| POST | `/upload` | multipart 表单上传（通用） | 浏览器/Node |
| POST | `/api/upload` | multipart 表单上传（API） | ESP32-CAM |
| POST | `/api/raw` | ★ 原始 JPEG 上传（预览/高分辨率） | ESP32-CAM |
| GET | `/api/frame` | 返回最新预览帧 | 浏览器轮询 |
| POST | `/api/capture` | 下发拍照指令到 ESP32-CAM | 浏览器 |
| GET | `/api/capture/status` | 查询拍照状态 | 浏览器轮询 |
| POST | `/api/capture/clear` | 清除拍照记录 | 浏览器 |
| GET/POST | `/api/flash` | 读取/设置闪光灯 | 浏览器 |
| POST | `/api/photos/save` | 保存照片到相册 | 浏览器 |
| GET | `/api/photos` | 获取相册列表 | 浏览器 |
| POST | `/api/photos/select` | 选择/取消选择照片 | 浏览器 |
| POST | `/api/photos/delete` | 删除照片（列表+磁盘） | 浏览器 |
| GET | `/uploads/<filename>` | 静态文件服务 | 浏览器 |

### 2.4 关键设计点

**预览帧 vs 高分辨率帧的分流**（[app.py:130-180](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py#L130-L180)）：
- 通过 HTTP 头 `X-Resolution` 区分：`high` → 落盘保存；其他 → 仅更新内存
- 通过 HTTP 头 `X-ESP32-IP` 自动捕获设备 IP，供后续拍照指令使用
- 拍照进行中（`is_capturing=True`）时，预览帧不再更新，避免覆盖

**拍照指令的异步协作**（[app.py:202-260](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py#L202-L260)）：
1. 浏览器 POST `/api/capture` → Flask 转发到 `http://<esp32_ip>/capture`
2. Flask 设置 `is_capturing=True`，立即返回
3. ESP32-CAM 收到指令后切换高分辨率模式拍照，再 POST `/api/raw`（带 `X-Resolution: high`）
4. 浏览器轮询 `/api/capture/status` 直到 `is_capturing=False` 且拿到 `last_captured_photo`

**内存管理**（[app.py:43-55](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py#L43-L55)）：
- 每 30 秒触发一次 `gc.collect()`，在 `/api/frame` 的 `finally` 块中调用
- `MAX_CONTENT_LENGTH = 32MB`，支持高分辨率照片

---

## 三、ESP32-CAM 固件层（`photo-upload-system/esp32-cam/`）

项目包含**多个并行版本**的固件，从简单到复杂递进：

| 固件 | 文件 | 特点 | 推荐度 |
|------|------|------|--------|
| `esp32cam_upload` | [esp32cam_upload.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_upload.ino) | 最简版，VGA 每 5 秒 multipart 上传 | 入门示例 |
| `esp32cam_simple_upload` | [esp32cam_simple_upload.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_simple_upload.ino) | QVGA 每 10 秒 raw 上传 | 入门示例 |
| `esp32cam_raw_upload` | [esp32cam_raw_upload/esp32cam_raw_upload.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_raw_upload/esp32cam_raw_upload.ino) | QVGA raw 上传 + 蓝牙控制 | 中等 |
| `esp32cam_streaming` | [esp32cam_streaming/esp32cam_streaming.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_streaming/esp32cam_streaming.ino) | ★ WebServer + 预览/拍照切换 + 配置页 | 生产推荐 |
| `esp32cam_http_streaming` | [esp32cam_http_streaming/esp32cam_http_streaming.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_http_streaming/esp32cam_http_streaming.ino) | 蓝牙 + raw 上传混合版 | 中等 |
| `esp32cam_freertos` | [esp32cam_freertos/esp32cam_freertos.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_freertos/esp32cam_freertos.ino) | ★★ FreeRTOS 双核任务分配 | 最完整 |

### 3.1 硬件配置（所有固件统一）

AI-Thinker ESP32-CAM 引脚定义（OV2640/OV3660 兼容）：
- XCLK=0, SIOD=26, SIOC=27, VSYNC=25, HREF=23, PCLK=22
- D0~D7: 5, 18, 19, 21, 36, 39, 34, 35
- PWDN=32, RESET=-1, FLASH=4

### 3.2 最完整版本：`esp32cam_freertos` 双核架构

[esp32cam_freertos.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_freertos/esp32cam_freertos.ino) 的核心设计：

```
┌─────────────────────────────────────────────────┐
│  Core 0 (vTaskCore0): 图像采集与上传             │
│  - 预览模式: QVGA(320x240) @ ~30fps → /api/raw   │
│  - 拍照模式: QXGA(2048x1536) → /api/raw (high)   │
│  - 通过 g_bNeedCapture 标志接收拍照请求          │
│  - 拍照时停预览→重新初始化→丢3帧→拍照→恢复       │
└─────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────┐
│  Core 1 (vTaskCore1): HTTP 服务器 (端口 80)      │
│  - POST /capture → 设置 g_bNeedCapture 标志      │
│  - POST /flash   → 控制 GPIO4 闪光灯             │
│  - GET  /flash   → 返回闪光灯状态                │
└─────────────────────────────────────────────────┘
```

**双核通信机制：** 使用全局标志位 `g_bNeedCapture`、`g_bIsCapturing`、`g_bFlashEnabled`（虽然创建了信号量 `xCaptureSemaphore`/`xPreviewSemaphore` 但实际未使用，存在资源浪费）。

**分辨率切换流程（关键）：**
1. 收到 `/capture` → Core 1 设置 `g_bNeedCapture=true`
2. Core 0 检测到标志 → 停止预览 → `esp_camera_deinit()`
3. 重新初始化为 QXGA（PSRAM 存储，质量 6）
4. 重新配置白平衡/曝光参数，等待 500ms 稳定
5. 丢弃前 3 帧让传感器适应光照
6. 可选开启闪光灯（GPIO4）→ 拍照 → 上传 → 关闭闪光灯
7. 反向流程恢复 QVGA 预览

### 3.3 备选版本：`esp32cam_streaming`（单核 WebServer 版）

[esp32cam_streaming.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_streaming/esp32cam_streaming.ino) 使用 `WebServer` 库提供：
- `/capture` (POST) — 触发拍照
- `/status` (GET) — 返回内存/分辨率状态
- `/config` (GET) / `/saveconfig` (POST) — 网页配置服务器 IP
- 预览上传通过 `WiFiClient` 手动构造 HTTP 请求，分块发送（4KB/8KB）

特点：拍照分辨率 `FRAMESIZE_XGA` (1024x768)，比 freertos 版低；但提供了运行时配置 IP 的能力。

---

## 四、前端层（浏览器）

### 4.1 主页面 `streaming_simple.html`

[streaming_simple.html](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/templates/streaming_simple.html) 是默认首页，功能模块：

| 模块 | 实现方式 |
|------|----------|
| IP 配置 | `localStorage` 持久化 ESP32-CAM IP |
| 闪光灯开关 | checkbox → `/api/flash` |
| 实时预览 | 定时轮询 `/api/frame?t=<timestamp>` 刷新 `<img>` |
| 拍照 | `/api/capture` → 轮询 `/api/capture/status` |
| 拍照结果 | 显示 + 保存到相册 / 放弃 |
| 相册 | 网格视图，支持单选/全选/删除/下载 |

> ⚠️ **性能提示：** 预览采用 `<img src>` 轮询而非 MJPEG 流或 WebSocket，帧率受限且存在延迟；`streaming.html` 引入了 Socket.IO 但未启用。

### 4.2 样式

- 使用 Ant Design 5.x 的 reset.css 作为基础样式重置
- 自定义 CSS 实现 Ant Design 风格的按钮/卡片/网格布局
- 无构建步骤，纯静态 HTML

---

## 五、辅助工具

### 5.1 蓝牙控制器 `bluetooth_controller.py`

[bluetooth_controller.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/bluetooth_controller.py) 通过 `pybluez` 库在 PC 端建立 RFCOMM 蓝牙服务端，等待 ESP32-CAM 连接后发送 `capture`/`test` 命令。与 `esp32cam_http_streaming.ino`（含 `BluetoothSerial`）配套使用。

> 状态：依赖 `bluetooth` 库（pybluez），Windows 上安装较繁琐，实际使用频率低。

### 5.2 启动脚本

| 脚本 | 作用 |
|------|------|
| `start_server.ps1` | ★ 推荐入口：检查 Python/依赖 → 创建 uploads 目录 → 获取本机 IP → 启动 `app.py` |
| `start_server.bat` | bat 版本，逻辑同上 |
| `start_server_simple.ps1` | 精简版 |
| `创建快捷方式.bat` | 创建桌面快捷方式 |

> ⚠️ 启动脚本检查的依赖包含 `cv2`/`numpy`/`PIL`，但 `requirements.txt` 未声明这些，且 `app.py` 实际未使用 OpenCV（注释中提到"不进行AI增强"）。存在依赖声明与实际使用不一致的问题。

---

## 六、备选服务端：Node.js 版（`photo/server.js`）

[server.js](file:///f:/esp32cam/photo1/photo/server.js) 是一个独立的 Express + Multer 上传服务：
- 端口 5000（与 Flask 版冲突，不能同时运行）
- 仅支持 `/upload` (POST) 和 `/list` (GET)，无流式预览、无拍照控制
- 16MB 文件大小限制
- 配套 `public/upload.html` 提供拖拽上传 UI

> 定位：早期原型/简单场景的备选方案，功能远不如 Flask 版完整。

---

## 七、端到端数据流

### 7.1 预览流（持续）

```
ESP32-CAM (Core 0, QVGA@30fps)
    │ POST /api/raw
    │ Header: X-Resolution: preview, X-ESP32-IP: <ip>
    │ Body: <raw jpeg bytes>
    ▼
Flask app.py: api_raw_upload()
    │ 更新 latest_frame, latest_frame_time
    │ (不落盘)
    ▼
浏览器: updatePreview()
    │ GET /api/frame?t=<ts>
    ▼
Flask: get_frame() → Response(latest_frame, image/jpeg)
    │
    ▼
<img id="preview">.src 更新
```

### 7.2 拍照流（按需）

```
浏览器: startCapture()
    │ POST /api/capture { esp32_ip }
    ▼
Flask: capture()
    │ POST http://<esp32_ip>/capture  (转发)
    │ 设置 is_capturing=True
    ▼
ESP32-CAM (Core 1): handleCapture()
    │ 设置 g_bNeedCapture=true
    │ 立即返回 200
    ▼
ESP32-CAM (Core 0): 检测到 g_bNeedCapture
    │ deinit → init(QXGA) → 丢3帧 → 拍照
    │ POST /api/raw
    │ Header: X-Resolution: high
    │ Body: <high-res jpeg>
    ▼
Flask: api_raw_upload() (resolution==high)
    │ 落盘 uploads/esp32cam_<ts>_<uuid>.jpg
    │ 更新 last_captured_photo, is_capturing=False
    ▼
浏览器: checkCaptureStatus() 轮询
    │ GET /api/capture/status
    │ 检测到 is_capturing=false & last_captured_photo
    ▼
显示拍照结果 → 保存到相册 / 放弃
```

---

## 八、架构观察与潜在改进点

> 以下仅为客观观察，**不构成立即修改建议**，供后续决策参考。

### 8.1 一致性问题
1. **固件碎片化：** 6 个 .ino 文件大量重复摄像头引脚定义和初始化代码，且 WiFi 凭据/服务器 IP 硬编码且不一致（`test`/`12345678` vs `12354678`；服务器 IP 多个版本）
2. **依赖声明：** `requirements.txt` 缺少 `requests`（`app.py` 在 `capture()` 内 import），启动脚本检查的 `cv2`/`numpy`/`PIL` 未声明且未使用
3. **未使用代码：** `streaming.html` 引入 Socket.IO 但 `app.py` 未注册 SocketIO 实例；freertos 版创建了信号量但从未使用

### 8.2 可靠性风险
1. **状态不持久化：** `saved_photos`、`flash_enabled`、`esp32_cam_ip` 均为内存变量，重启丢失
2. **相册与磁盘不同步：** 直接删除 `uploads/` 下文件不会更新 `saved_photos`；反之 `delete_photo` 删除文件后若列表操作失败会产生不一致
3. **并发安全：** 全局变量在 Flask 多 worker 下不安全（当前 `debug=False` 单进程尚可）
4. **拍照超时：** ESP32 端无心跳，Flask 端 30 秒超时后 `is_capturing=False`，但 ESP32 可能仍在处理，后续 high 帧到达会重置状态

### 8.3 性能瓶颈
1. **预览轮询：** 浏览器 `<img>` 轮询而非 MJPEG 流，延迟高、带宽浪费
2. **预览帧覆盖：** `latest_frame` 单变量，高频率上传时浏览器拉取的帧可能被跳过（属设计取舍）
3. **分辨率切换耗时：** `esp_camera_deinit` + 重新 init 约 1-2 秒，拍照体验有延迟

### 8.4 安全性
1. `/api/capture` 对 `esp32_ip` 仅做格式校验，未限制内网范围，存在 SSRF 风险
2. `/uploads/<filename>` 未对文件名做路径穿越校验（`send_from_directory` 默认安全，但仍建议白名单）
3. 无任何认证机制，局域网内任意设备可操作

---

## 九、快速启动指引（推荐路径）

1. **服务端：** 双击 `photo-upload-system/start_server.ps1`（或右键"用 PowerShell 运行"）
2. **固件：** 用 Arduino IDE 打开 `esp32-cam/esp32cam_freertos/esp32cam_freertos.ino`
   - 修改 `ssid`/`password` 为实际 WiFi
   - 修改 `serverAddress` 为运行 Flask 的 PC 的 IP
   - 选择 ESP32-CAM 开发板，上传
3. **使用：** 浏览器访问 `http://<pc-ip>:5000`，输入 ESP32-CAM IP（串口监视器可查看），开始预览/拍照

---

## 十、文件索引（快速跳转）

**服务端：**
- [backend/app.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py) — Flask 主应用
- [backend/requirements.txt](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/requirements.txt) — 依赖
- [backend/templates/streaming_simple.html](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/templates/streaming_simple.html) — 默认前端

**ESP32-CAM 固件：**
- [esp32-cam/esp32cam_freertos/esp32cam_freertos.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_freertos/esp32cam_freertos.ino) — ★ 推荐版本
- [esp32-cam/esp32cam_streaming/esp32cam_streaming.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_streaming/esp32cam_streaming.ino) — 可配置版本
- [esp32-cam/esp32cam_raw_upload/esp32cam_raw_upload.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_raw_upload/esp32cam_raw_upload.ino) — 蓝牙版本

**工具与脚本：**
- [bluetooth_controller.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/bluetooth_controller.py) — PC 蓝牙控制
- [start_server.ps1](file:///f:/esp32cam/photo1/photo/photo-upload-system/start_server.ps1) — 启动脚本

**备选 Node 服务：**
- [server.js](file:///f:/esp32cam/photo1/photo/server.js) — Node 备选服务
- [public/upload.html](file:///f:/esp32cam/photo1/photo/public/upload.html) — Node 版上传页
