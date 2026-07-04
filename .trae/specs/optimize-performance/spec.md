# 项目性能优化 Spec

## Why
当前后端 Flask 服务存在多个性能反模式：MJPEG 流靠 `time.sleep` 轮询导致新帧延迟最高 67ms；默认单线程使一个慢请求阻塞所有客户端；`/api/frame` 在请求路径执行 `gc.collect()` 造成延迟尖峰；`/api/photos` 每次请求 N 次 `os.path.exists`；多个函数内 `import` 反复查找模块；`/api/capture` timeout 过长。固件侧存在 `g_latestFrame`/`s_fbLock` 死代码占内存。本次在不改外部 API、不引入新功能的前提下消除这些反模式。

## What Changes
- **MJPEG 流唤醒**：新增 `threading.Event` (`frame_event`)，`/api/raw` 写入预览帧后 `set()`，`/api/stream` 生成器用 `wait(timeout=1.0)` 替代 `time.sleep(1.0/15)`，新帧延迟从 ~67ms 降至 ~1ms。
- **并发模式**：`app.run(threaded=True)` 允许多请求并发。
- **移除 GC 反模式**：删除 `cleanup_memory` 函数、`/api/frame` finally 中的调用、`LAST_CLEANUP_TIME`/`CLEANUP_INTERVAL` 全局变量、`import gc`。
- **import 提升**：`send_from_directory`、`shutil` 移到模块顶部；删除 5 处函数内 `import`（3 个静态路由 + `save_photo` + `migrate_legacy_photos_to_album`）。
- **相册文件存在性缓存**：新增 `get_album_files()` 基于 `album/` 目录 mtime 缓存文件名集合，`/api/photos` 用集合查找替代 N 次 `os.path.exists`；save/delete 操作时目录 mtime 自动变化，缓存自动失效。
- **capture timeout**：`/api/capture` 的 `requests.post(timeout=10)` → `timeout=5`。
- **固件死代码清理**：删除 `g_latestFrame` 声明、`s_fbLock` 声明与 setup 中的创建语句。

## Impact
- Affected specs: 无（项目首次建立 spec）
- Affected code:
  - `backend/app.py`（流、并发、GC、import、缓存、timeout）
  - `backend/tests/test_app.py`（新增 Event 唤醒测试、缓存命中测试）
  - `firmware/esp32cam_unified/esp32cam_unified.ino`（删除死代码）

## ADDED Requirements

### Requirement: MJPEG 流即时唤醒
系统 SHALL 在 `/api/raw` 接收到预览帧后立即唤醒所有 `/api/stream` 订阅者推送新帧，而非依赖固定 sleep 周期轮询。

#### Scenario: 新帧到达后流立即推送
- **WHEN** `/api/raw` 写入新预览帧并 `frame_event.set()`
- **THEN** `/api/stream` 订阅者在 100ms 内收到该帧

#### Scenario: 无新帧时流保活
- **WHEN** 1 秒内无新帧到达
- **THEN** `frame_event.wait(timeout=1.0)` 超时返回，连接保持不关闭

### Requirement: 相册文件存在性缓存
系统 SHALL 缓存 `album/` 目录文件名集合，`/api/photos` 请求时通过集合查找验证文件存在性，避免每次请求 N 次 `os.path.exists` 系统调用。

#### Scenario: 缓存命中时不调用 os.path.exists
- **WHEN** 第二次请求 `/api/photos` 且 `album/` 目录 mtime 未变化
- **THEN** 不再对相册文件调用 `os.path.exists`

#### Scenario: 目录变化时缓存自动失效
- **WHEN** save_photo 或 delete_photo 改变 `album/` 目录内容（mtime 变化）
- **THEN** 下次 `get_album_files()` 重建缓存

### Requirement: 多请求并发
系统 SHALL 以 `threaded=True` 启动 Flask，允许同一时刻处理多个请求。

#### Scenario: 慢请求不阻塞其他客户端
- **WHEN** 一个客户端发起 `/api/capture`（耗时数秒）
- **THEN** 另一客户端的 `/api/stream` 或 `/api/photos` 请求不被阻塞

## MODIFIED Requirements

### Requirement: `/api/stream` 生成器实现
`/api/stream` 端点的生成器 SHALL 使用 `frame_event.wait(timeout=1.0)` 等待新帧事件，事件触发后立即推送帧并 `clear()` 事件；不再使用 `time.sleep(1.0/15)` 轮询。

### Requirement: `/api/photos` 文件验证
`/api/photos` SHALL 通过 `get_album_files()` 返回的文件名集合验证 `saved_photos` 中每个条目的 `filename` 是否存在，替代原先的 `os.path.exists(os.path.join(album_dir, filename))`。当 `len(existing) != len(saved_photos)` 时回写 `state.json`。

### Requirement: `/api/capture` HTTP 超时
`/api/capture` 发往 ESP32-CAM 的 `requests.post` SHALL 使用 5 秒超时，避免设备无响应时长时间阻塞 worker。

### Requirement: 模块级 import
`send_from_directory` 与 `shutil` SHALL 在 `app.py` 顶部 import，函数内不再重复 import。

## REMOVED Requirements

### Requirement: 定期内存清理
**Reason**: CPython 的引用计数已自动管理内存，显式 `gc.collect()` 在请求路径执行会造成延迟尖峰，无实际收益。
**Migration**: 删除 `cleanup_memory` 函数、`/api/frame` finally 调用、`LAST_CLEANUP_TIME`/`CLEANUP_INTERVAL`/`import gc`。无外部行为变化。

### Requirement: 固件 g_latestFrame / s_fbLock
**Reason**: FreeRTOS 模式下 `g_latestFrame` 从未赋值或读取，`s_fbLock` 仅在 setup 创建但从未被 acquire/release，均为死代码。
**Migration**: 删除声明与 setup 中的创建语句。固件行为不变。
