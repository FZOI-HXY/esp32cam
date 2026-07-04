# ESP32-CAM 照片上传系统

基于 ESP32-CAM 的实时照片采集与管理系统，支持 MJPEG 实时流预览、高分辨率拍照、闪光灯控制、相册管理与外部照片上传。

## 架构

```
┌─────────────────┐      HTTP      ┌──────────────┐       ┌──────────┐
│  ESP32-CAM 设备端 │ ──────────►  │  Flask 服务端  │ ◄──── │  浏览器  │
│  (Arduino C++)   │  POST /api/raw │  (Python 3)   │       │ (HTML5)  │
│                  │  GET/POST /flash│              │       │          │
│  预览流 ~10fps   │                │  MJPEG 流     │       │ 实时预览 │
│  高分辨率拍照     │                │  相册管理      │       │ 相册浏览 │
│  闪光灯控制      │                │  状态持久化    │       │ 照片上传 │
└─────────────────┘                └──────────────┘       └──────────┘
```

## 目录结构

```
photo-upload-system/
├── README.md
├── backend/                        # 后端服务
│   ├── app.py                      # Flask 应用主入口
│   ├── state.py                    # 状态持久化模块
│   ├── requirements.txt            # Python 依赖
│   ├── requirements-dev.txt        # 开发/测试依赖
│   ├── templates/                  # 前端模板
│   │   ├── streaming_simple.html   # 主预览页面（MJPEG 流）
│   │   ├── streaming.html          # 旧版预览页
│   │   └── upload.html             # 照片上传页
│   ├── data/                       # 数据目录（集中存储）
│   │   ├── uploads/                # 外部上传文件
│   │   ├── captures/               # 相机拍照暂存
│   │   └── album/                  # 用户相册
│   ├── state.json                  # 持久化状态文件（自动生成）
│   └── tests/                      # 测试套件
│       ├── conftest.py             # pytest 夹具
│       ├── test_app.py             # 应用测试
│       └── test_state.py           # 状态模块测试
├── firmware/                       # ESP32-CAM 固件
│   └── esp32cam_unified/           # 统一固件
│       ├── config.h                # 配置头文件
│       └── esp32cam_unified.ino    # 主程序
└── scripts/                        # 启动脚本与工具
    ├── start_server.ps1            # Windows 启动脚本
    ├── start_server.bat            # Windows 快捷启动
    ├── start_server_simple.ps1     # 精简启动脚本
    └── bluetooth_controller.py     # 蓝牙控制工具
```

## 快速开始

### 1. 启动后端服务

```bash
cd backend
pip install -r requirements.txt
python app.py
```

浏览器访问 `http://localhost:5000`。

或用 PowerShell 运行启动脚本：

```powershell
.\scripts\start_server.ps1
```

### 2. 烧录固件到 ESP32-CAM

1. 安装 [Arduino IDE](https://www.arduino.cc/en/software)
2. 添加 ESP32 开发板支持包（首选项 -> 附加开发板管理器 URL 添加 `https://espressif.github.io/arduino-esp32/package_esp32_index.json`）
3. 打开 `esp32-cam/esp32cam_unified/esp32cam_unified.ino`
4. 编辑 `config.h`，配置 WiFi 与服务器信息：

```c
#define WIFI_SSID     "你的WiFi名称"
#define WIFI_PASSWORD "你的WiFi密码"
#define SERVER_IP     "192.168.1.x"   // 后端服务所在电脑 IP
#define SERVER_PORT   5000
```

5. 选择开发板：**AI Thinker ESP32-CAM**
6. 烧录并复位，串口输出 `[BOOT] ESP32-CAM 统一固件启动` 即成功

### 3. 使用

| 功能 | 说明 |
|------|------|
| **实时预览** | 摄像头持续推送 MJPEG 流（约 10fps），浏览器直接播放 |
| **拍照** | 点击拍照按钮，高分辨率原图上传至服务端 |
| **闪光灯** | 控制 ESP32-CAM 板载 LED 补光 |
| **保存到相册** | 将拍照的照片存入相册目录 |
| **上传照片** | 从本地上传照片到服务器 |
| **相册管理** | 浏览、选择、删除相册中的照片 |

## API 文档

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 预览页面（streaming_simple.html） |
| `/api/stream` | GET | MJPEG 实时流（multipart/x-mixed-replace） |
| `/api/frame` | GET | 单帧快照 JPEG（兼容旧版） |
| `/api/raw` | POST | ESP32-CAM 上传帧数据（X-Resolution: preview/high） |
| `/api/capture` | POST | 触发拍照指令 |
| `/api/flash` | GET/POST | 查询/设置闪光灯状态 |
| `/api/photos` | GET | 获取相册列表 |
| `/api/photos/save` | POST | 保存照片到相册 |
| `/api/photos/select` | POST | 选择/取消选择照片 |
| `/api/photos/delete` | POST | 删除照片 |
| `/api/upload` | POST | 外部上传照片（multipart/form-data） |
| `/uploads/<file>` | GET | 获取上传目录文件 |
| `/captures/<file>` | GET | 获取拍照目录文件 |
| `/album/<file>` | GET | 获取相册目录文件 |

## 目录说明

| 目录 | 用途 | 存放内容 |
|------|------|----------|
| `backend/data/uploads/` | 外部上传 | 通过浏览器上传的照片 |
| `backend/data/captures/` | 相机拍摄 | ESP32-CAM 拍照的原图（尚未保存到相册） |
| `backend/data/album/` | 用户相册 | 从 captures/ 或 uploads/ 保存到相册的照片 |

启动时自动将旧 `data/uploads/` 中的相册照片迁移至 `data/album/`，无需手动操作。

## 测试

```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

测试覆盖：MJPEG 流、状态持久化、目录分离、相册管理、SSRF 防护、旧数据迁移、state 模块原子写入与损坏恢复。

## 固件配置

通过 `config.h` 的 `#define` 开关控制编译特性：

```c
#define ENABLE_PREVIEW   1   // 预览流（连续上传）
#define ENABLE_CAPTURE   1   // 高分辨率拍照
#define ENABLE_FLASH     1   // 闪光灯控制
#define ENABLE_FREERTOS  1   // 双核任务（Core0 网络、Core1 摄像头）
```

关闭 `ENABLE_FREERTOS` 时退化为单 `loop()` 轮询模式。其他参数（分辨率、帧率、超时等）同样在 `config.h` 集中可调。

## 状态持久化

`state.json` 持久化以下非瞬态数据：

- 相册列表（saved_photos）
- 闪光灯状态（flash_enabled）
- ESP32-CAM IP 地址与更新时间

写入采用临时文件 + `os.replace` 原子操作，避免崩溃导致文件损坏。文件损坏或不存在时自动回退默认值。

## 安全

- **SSRF 防护**：拍照指令只能发送到私有 IP 段（127.x.x.x、192.168.x.x、10.x.x.x、172.16-31.x.x）
- **文件类型校验**：上传文件后缀白名单
- **文件大小限制**：最大 32MB