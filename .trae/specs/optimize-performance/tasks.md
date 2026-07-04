# Tasks

- [x] Task 1: MJPEG 流用 threading.Event 唤醒替代 sleep 轮询
  - [x] SubTask 1.1: 写失败测试 `test_stream_pushes_frame_immediately_after_update`（新帧到达后 100ms 内推送）
  - [x] SubTask 1.2: 添加 `import threading` 与 `frame_event = threading.Event()` 全局变量
  - [x] SubTask 1.3: `/api/raw` 预览分支写入帧后调用 `frame_event.set()`
  - [x] SubTask 1.4: `/api/stream` 生成器用 `frame_event.wait(timeout=1.0)` + `clear()` 替代 `time.sleep(1.0/15)`
  - [x] SubTask 1.5: 运行流相关 3 个测试通过

- [x] Task 2: 启用 threaded 模式 + 移除 GC 反模式
  - [x] SubTask 2.1: 删除 `cleanup_memory` 函数定义
  - [x] SubTask 2.2: `/api/frame` 的 finally 块改为 `pass`
  - [x] SubTask 2.3: 删除 `LAST_CLEANUP_TIME`、`CLEANUP_INTERVAL` 全局变量
  - [x] SubTask 2.4: 删除 `import gc`
  - [x] SubTask 2.5: `app.run` 添加 `threaded=True` 参数
  - [x] SubTask 2.6: 运行全部测试无回归

- [x] Task 3: 提升模块级 import，消除函数内重复 import
  - [x] SubTask 3.1: 顶部 import 区添加 `send_from_directory` 与 `import shutil`（同时移除 `import gc`）
  - [x] SubTask 3.2: 删除 3 个静态路由内的 `from flask import send_from_directory`
  - [x] SubTask 3.3: 删除 `save_photo` 内的 `import shutil`
  - [x] SubTask 3.4: 删除 `migrate_legacy_photos_to_album` 内的 `import shutil`
  - [x] SubTask 3.5: 运行全部测试无回归

- [x] Task 4: /api/photos 加文件存在性缓存
  - [x] SubTask 4.1: 写失败测试 `test_photos_cache_avoids_repeated_path_exists`（第二次请求不调用 os.path.exists）
  - [x] SubTask 4.2: 添加 `_album_files_cache` 与 `_album_files_cache_mtime` 全局变量
  - [x] SubTask 4.3: 实现 `get_album_files()` 函数（基于目录 mtime 缓存）
  - [x] SubTask 4.4: 改造 `/api/photos` 用 `get_album_files()` 集合查找替代 `os.path.exists`
  - [x] SubTask 4.5: 缓存测试通过 + 全部测试无回归

- [x] Task 5: /api/capture timeout 优化
  - [x] SubTask 5.1: `requests.post(timeout=10)` → `timeout=5`
  - [x] SubTask 5.2: 运行全部测试无回归

- [x] Task 6: 固件清理 g_latestFrame / s_fbLock 死代码
  - [x] SubTask 6.1: 删除 `static camera_fb_t* g_latestFrame = nullptr;` 声明
  - [x] SubTask 6.2: 删除 `static SemaphoreHandle_t s_fbLock = NULL;` 声明
  - [x] SubTask 6.3: 删除 setup() 中的 `s_fbLock = xSemaphoreCreateMutex();`
  - [x] SubTask 6.4: grep 验证无残留引用

- [x] Task 7: 最终全量验证
  - [x] SubTask 7.1: 运行后端全部测试（预期 21 passed）
  - [x] SubTask 7.2: `python -c "import app"` 验证启动正常、`frame_event` 与缓存变量就绪
  - [x] SubTask 7.3: grep 固件确认无 `g_latestFrame|s_fbLock|gc.collect|cleanup_memory|LAST_CLEANUP_TIME` 残留

# Task Dependencies
- Task 2 与 Task 3 都涉及顶部 import 区，Task 3 在 Task 2 之后执行以避免冲突
- Task 4 独立，可与 Task 5、Task 6 并行
- Task 5、Task 6 互相独立
- Task 7 依赖 Task 1-6 全部完成
