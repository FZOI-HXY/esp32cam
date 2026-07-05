# MobileEye (ESP32-CAM) 移动图像采集系统重构说明

**日期**: 2026-06-28
**目标**: 解决预览性能、状态持久化、目录分离、固件碎片化四大问题
**测试**: 18 个用例全部通过

---

## 一、问题与方案

### 1. 预览性能优化
**问题**: 前端每 50ms 轮询 `/api/frame`，浏览器与服务器负担重、画面卡顿。

**方案**: 改用 MJPEG 流（`multipart/x-mixed-replace`），单连接持续推送。

**变更**:
- 后端新增 `/api/stream` 端点，通过生成器推送 MJPEG 流；引入 `frame_id` 计数器，仅在新帧到达时发送，避免空转。
- 前端 `templates/streaming_simple.html` 移除 `setInterval(updatePreview, 50)`，改为 `img.src = '/api/stream'`，并添加 `onerror` 自动重连。

**测试**:
- `test_stream_returns_multipart_content_type`: 验证 Content-Type 含 `multipart/x-mixed-replace; boundary=frame`
- `test_stream_yields_frame_only_on_change`: 验证仅在 `frame_id` 变化时推送

### 2. 状态持久化
**问题**: 服务重启后相册列表、闪光灯状态、相机 IP 全部丢失。

**方案**: 引入 `state.py` 模块，JSON 原子写入 `state.json`。

**变更**:
- 新建 `backend/state.py`: `load_state()` / `save_state()`，临时文件 + `os.replace` 原子写入，损坏文件自动回退默认值。
- `app.py` 新增 `reload_state_from_disk()` / `persist_state()`，启动时加载，关键变更点（拍照 IP 更新、闪光灯、相册增删、照片选择、幽灵清理）调用 `persist_state()`。
- 持久化字段: `saved_photos`、`flash_enabled`、`esp32_cam_ip`、`esp32_cam_ip_time`
- 不持久化瞬态字段: `latest_frame`、`is_capturing`

**测试**:
- `test_state_persists_flash_enabled_across_reload`: 闪光灯与相机 IP 重启后保留
- `test_state_persists_saved_photos_across_reload`: 相册列表重启后保留
- `test_load_state_returns_defaults_when_file_missing` / `test_load_state_recovers_from_corrupt_json` / `test_save_state_is_atomic` / `test_save_then_load_roundtrip`

### 3. 相册与上传目录分离
**问题**: 所有照片（相机拍照、外部上传、相册）混存于 `uploads/`，无法区分用途。

**方案**: 拆分为三个目录:
| 目录 | 用途 | 静态路由 |
|------|------|----------|
| `captures/` | 相机拍摄暂存 | `/captures/<file>` |
| `album/` | 用户保存的相册 | `/album/<file>` |
| `uploads/` | 外部上传（兼容） | `/uploads/<file>` |

**变更**:
- `app.py` 新增 `CAPTURES_FOLDER` / `ALBUM_FOLDER` 常量，启动时 `os.makedirs` 三目录。
- `/api/raw` 高分辨率拍照帧改写到 `captures/`，URL 改为 `/captures/`。
- `/api/photos/save` 改为从 `captures/` 或 `uploads/` 查找源文件，`shutil.move` 到 `album/`，元数据 `url` / `location` 更新为 `/album/`。
- `/api/photos`（GET）与 `/api/photos/delete` 改查 `ALBUM_FOLDER`。
- 新增一次性迁移函数 `migrate_legacy_photos_to_album()`：启动时把旧 `uploads/` 中相册照片移到 `album/`，幂等设计。

**测试**:
- `test_high_resolution_capture_saved_to_captures`: 拍照帧入 captures
- `test_save_photo_moves_file_from_captures_to_album`: save 从 captures 移到 album
- `test_migrate_legacy_moves_old_uploads_to_album`: 旧 uploads 照片迁移且幂等

### 4. 固件碎片化整合
**问题**: 6 个重复 `.ino` 文件（freertos / http_streaming / raw_upload / streaming×2 / simple_upload / upload），功能重叠难维护。

**方案**: 整合为单一 `esp32cam_unified.ino` + `config.h`，通过 `#define` 开关选择特性。

**变更**:
- 删除 7 个旧 `.ino` 及其空目录
- 新建 `esp32-cam/esp32cam_unified/config.h`: 集中所有可配置项（WiFi、服务器、引脚、分辨率、间隔、功能开关）
- 新建 `esp32cam_unified.ino`: 整合预览流、高分辨率拍照、闪光灯控制、FreeRTOS 双核任务（Core0 网络、Core1 摄像头），关闭 `ENABLE_FREERTOS` 时退化为单 loop 轮询

---

## 二、文件变更清单

### 新增
- `backend/state.py` — 状态持久化模块
- `backend/tests/test_state.py` — state 模块测试（4 例）
- `esp32-cam/esp32cam_unified/config.h` — 固件配置头
- `esp32-cam/esp32cam_unified/esp32cam_unified.ino` — 整合固件
- `docs/superpowers/plans/2026-06-27-refactor.md` — 重构计划

### 修改
- `backend/app.py` — MJPEG 流、状态持久化、三目录分离、迁移函数
- `backend/templates/streaming_simple.html` — 前端切到 MJPEG 流
- `backend/tests/conftest.py` — 测试夹具适配新目录与状态文件
- `backend/tests/test_app.py` — 新增 8 个测试用例
- `backend/requirements.txt` — 补充 requests 依赖

### 删除
- `esp32-cam/esp32cam_freertos/esp32cam_freertos.ino`
- `esp32-cam/esp32cam_http_streaming/esp32cam_http_streaming.ino`
- `esp32-cam/esp32cam_raw_upload/esp32cam_raw_upload.ino`
- `esp32-cam/esp32cam_streaming/esp32cam_streaming.ino`
- `esp32-cam/esp32cam_simple_upload.ino`
- `esp32-cam/esp32cam_streaming.ino`
- `esp32-cam/esp32cam_upload.ino`
- 上述空目录

---

## 三、验证

```
============================= test session starts =============================
collected 18 items

tests/test_app.py .............
tests/test_state.py .....

============================= 18 passed in 1.42s =============================
```

| 类别 | 用例数 | 覆盖点 |
|------|--------|--------|
| 基础 | 2 | 导入、根路由 |
| 相册读取 | 2 | 幽灵过滤、内存同步 |
| 拍照 SSRF | 3 | 公网拒绝、私网/回环允许 |
| MJPEG 流 | 2 | Content-Type、增量推送 |
| 状态持久化 | 2 | 闪光灯、相册列表重启保留 |
| 目录分离 | 3 | captures 入库、save 移动、旧 uploads 迁移 |
| state 模块 | 4 | 默认值、往返、原子写、损坏恢复 |

---

## 四、兼容性

- **API 兼容**: `/api/raw`、`/api/photos/*`、`/api/flash` 端点签名不变，仅存储路径调整。
- **静态路由**: 保留 `/uploads/`，新增 `/captures/`、`/album/`。
- **旧数据**: 启动时自动迁移 `uploads/` 中的相册照片到 `album/`，无需人工干预。
- **固件**: 旧 `.ino` 已删除，需在 Arduino IDE 中打开 `esp32cam_unified/esp32cam_unified.ino`，按 `config.h` 顶部注释配置 WiFi 与服务器 IP。
