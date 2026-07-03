# 项目性能优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变功能与外部 API 的前提下，消除后端 Flask 服务与 ESP32-CAM 固件中的性能反模式，降低预览流延迟、提升并发能力、减少请求路径上的阻塞。

**Architecture:** 后端优化分四类：(1) MJPEG 流用 `threading.Event` 唤醒替代 `time.sleep` 轮询；(2) 启用 `threaded=True` 允许多请求并发；(3) 移除 `gc.collect()` 反模式与函数内 import 反复查找；(4) `/api/photos` 加文件存在性缓存，避免每次请求 N 次 `os.path.exists`；`(5)` `/api/capture` 的 `requests.post` timeout 从 10s 降至 5s 避免长时间阻塞 worker。固件侧清理死代码 `g_latestFrame`（FreeRTOS 模式下从未使用，白占内存）。

**Tech Stack:** Python 3 / Flask 3.0、threading.Event、pytest、Arduino C++ / esp32-camera

---

## 性能瓶颈清单（优化前）

| 位置 | 问题 | 影响 |
|------|------|------|
| `app.py` `/api/stream` | `time.sleep(1.0/15)` 轮询 frame_id | 新帧到达后最长 67ms 才推送，CPU 空转 |
| `app.py` `app.run()` | 默认单线程 | 一个请求阻塞时其他请求排队 |
| `app.py` `cleanup_memory` | 每 30s `gc.collect()` 在请求路径执行 | CPython 显式 GC 慢，请求延迟尖峰 |
| `app.py` 三个路由函数内 `import` | `from flask import send_from_directory`、`import shutil` 每次请求执行 | 模块查找开销（虽小但累加） |
| `app.py` `/api/photos` | 每次请求遍历 saved_photos 调 `os.path.exists` | O(N) 系统调用，相册大时慢 |
| `app.py` `/api/capture` | `requests.post(timeout=10)` | ESP32-CAM 无响应时阻塞 worker 10s |
| `esp32cam_unified.ino` | `g_latestFrame` 在 FreeRTOS 模式下从未赋值/读取 | 死代码占内存、混淆 |

## 文件结构

| 文件 | 改动类型 | 职责 |
|------|---------|------|
| `backend/app.py` | 修改 | 流唤醒、并发、清理反模式、缓存、timeout |
| `backend/tests/test_app.py` | 修改 | 新增 Event 唤醒与缓存测试 |
| `firmware/esp32cam_unified/esp32cam_unified.ino` | 修改 | 删除 g_latestFrame 死代码 |

---

### Task 1: MJPEG 流用 threading.Event 唤醒替代 sleep 轮询

**Files:**
- Modify: `backend/app.py:29-31` (新增 Event)、`backend/app.py` `/api/raw` 预览分支、`/api/stream` 生成器

- [ ] **Step 1: 写失败测试 - 验证新帧到达时 stream 立即推送（≤100ms）**

在 `backend/tests/test_app.py` 末尾追加：

```python
import time as _time


def test_stream_pushes_frame_immediately_after_update(app, client):
    """新帧到达后，stream 应在 100ms 内推送，无需等待 67ms sleep 周期。"""
    # 先清空帧
    app.latest_frame = None
    app.frame_id = 0

    # 在另一个线程发起流请求，读取首块
    import threading
    result = {'chunk': None}

    def reader():
        resp = client.get('/api/stream')
        # 读取第一块（应为边界+帧）
        try:
            result['chunk'] = next(resp.response)
        except StopIteration:
            result['chunk'] = b''
        resp.close()

    t = threading.Thread(target=reader, daemon=True)
    t.start()

    # 等待连接建立
    _time.sleep(0.2)

    # 更新帧
    app.latest_frame = b'\xff\xd8\xff\xe0test'
    app.frame_id = 1
    # 唤醒流
    if hasattr(app, 'frame_event'):
        app.frame_event.set()

    t.join(timeout=2.0)
    assert result['chunk'] is not None
    assert b'test' in result['chunk']
```

- [ ] **Step 2: 运行测试验证失败**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/test_app.py::test_stream_pushes_frame_immediately_after_update -v
```
Expected: FAIL（`app.frame_event` 不存在）

- [ ] **Step 3: 添加 frame_event 全局变量**

在 `backend/app.py` 找到：

```python
# 帧版本号，每次更新预览帧时自增，用于 MJPEG 流去重
frame_id = 0
```

在其后新增一行：

```python
# 帧到达事件：新帧写入时 set，stream 生成器 wait 后立即推送
frame_event = threading.Event()
```

并在文件顶部 import 区添加（若尚无 threading）：

```python
import threading
```

- [ ] **Step 4: 在 /api/raw 预览分支中 set 事件**

找到 `/api/raw` 的预览分支：

```python
        # 预览帧只更新内存，不保存到磁盘
        # 只有在非拍照状态下才更新预览帧
        if not is_capturing:
            # 验证数据完整性
            if len(request.data) > 0:
                # 更新最新画面
                latest_frame = request.data
                latest_frame_time = time.time()
                frame_id += 1
            else:
                print('接收到空数据')
```

替换为：

```python
        # 预览帧只更新内存，不保存到磁盘
        # 只有在非拍照状态下才更新预览帧
        if not is_capturing:
            # 验证数据完整性
            if len(request.data) > 0:
                # 更新最新画面
                latest_frame = request.data
                latest_frame_time = time.time()
                frame_id += 1
                # 唤醒所有 MJPEG 流订阅者立即推送新帧
                frame_event.set()
            else:
                print('接收到空数据')
```

- [ ] **Step 5: 改造 /api/stream 生成器用 Event.wait 替代 sleep**

找到：

```python
@app.route('/api/stream')
def video_stream():
    """MJPEG 实时流：单连接持续推送，仅在 frame_id 变化时发送新帧。"""
    boundary = 'frame'

    def generate():
        last_id = -1
        while True:
            frame = latest_frame
            fid = frame_id
            if frame is not None and fid != last_id:
                last_id = fid
                yield (
                    b'--' + boundary.encode() + b'\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )
            # 上限 ~15 FPS，避免空转占满 CPU
            time.sleep(1.0 / 15)

    return Response(
        generate(),
        mimetype=f'multipart/x-mixed-replace; boundary={boundary}',
        headers={'Cache-Control': 'no-cache, private'},
    )
```

替换为：

```python
@app.route('/api/stream')
def video_stream():
    """MJPEG 实时流：单连接持续推送，新帧到达时由 frame_event 唤醒立即发送。"""
    boundary = 'frame'

    def generate():
        last_id = -1
        while True:
            # 等待新帧事件，最长等 1 秒（保活，避免连接被代理超时关闭）
            frame_event.wait(timeout=1.0)
            frame_event.clear()
            frame = latest_frame
            fid = frame_id
            if frame is not None and fid != last_id:
                last_id = fid
                yield (
                    b'--' + boundary.encode() + b'\r\n'
                    b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n'
                )

    return Response(
        generate(),
        mimetype=f'multipart/x-mixed-replace; boundary={boundary}',
        headers={'Cache-Control': 'no-cache, private'},
    )
```

- [ ] **Step 6: 运行测试验证通过**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/test_app.py::test_stream_pushes_frame_immediately_after_update tests/test_app.py::test_stream_returns_multipart_content_type tests/test_app.py::test_stream_yields_frame_only_on_change -v
```
Expected: 3 passed

---

### Task 2: 启用 threaded 模式 + 移除 gc.collect 反模式

**Files:**
- Modify: `backend/app.py` `cleanup_memory` 函数、`/api/frame` finally 块、`app.run()`

- [ ] **Step 1: 删除 cleanup_memory 函数定义**

找到并删除整个函数：

```python
def cleanup_memory():
    """定期清理内存"""
    global LAST_CLEANUP_TIME
    
    current_time = time.time()
    if current_time - LAST_CLEANUP_TIME > CLEANUP_INTERVAL:
        print("执行内存清理...")
        
        # 强制垃圾回收
        gc.collect()
        
        # 记录清理时间
        LAST_CLEANUP_TIME = current_time
        print("内存清理完成")
```

- [ ] **Step 2: 删除 /api/frame 中的 cleanup_memory 调用**

找到 `/api/frame` 的 finally 块：

```python
    finally:
        # 定期清理内存
        cleanup_memory()
```

替换为：

```python
    finally:
        pass
```

或者直接删除整个 `try/except/finally` 结构，改为线性代码（更清晰）。保守起见仅删除 finally 内容。

- [ ] **Step 3: 删除 LAST_CLEANUP_TIME 与 CLEANUP_INTERVAL 全局变量**

找到并删除：

```python
# 内存管理
LAST_CLEANUP_TIME = time.time()
CLEANUP_INTERVAL = 30  # 每30秒清理一次内存
```

- [ ] **Step 4: 删除 gc import**

找到文件顶部的 `import gc` 并删除该行。

- [ ] **Step 5: 启用 threaded 模式**

找到文件末尾：

```python
if __name__ == '__main__':
    print("启动Flask服务器...")
    print(f"服务器将运行在 http://0.0.0.0:5000")
    print(f"访问地址: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
```

替换为：

```python
if __name__ == '__main__':
    print("启动Flask服务器...")
    print(f"服务器将运行在 http://0.0.0.0:5000")
    print(f"访问地址: http://localhost:5000")
    # threaded=True 允许多请求并发，避免单请求阻塞其他客户端
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
```

- [ ] **Step 6: 运行全部测试验证**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v 2>&1 | Select-Object -Last 5
```
Expected: 20 passed（含 Task 1 新增测试）

---

### Task 3: 提升模块级 import，消除函数内重复 import

**Files:**
- Modify: `backend/app.py` 顶部 import 区、`uploaded_file`、`captured_file`、`album_file`、`save_photo`、`migrate_legacy_photos_to_album`

- [ ] **Step 1: 顶部添加 send_from_directory 与 shutil**

找到顶部 import 区：

```python
from flask import Flask, render_template, request, jsonify, Response
import os
from werkzeug.utils import secure_filename
import uuid
import base64
import time
import gc
import ipaddress
import re
import requests
import state as state_module
```

替换为：

```python
from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import os
from werkzeug.utils import secure_filename
import uuid
import base64
import time
import ipaddress
import re
import shutil
import requests
import state as state_module
```

（同时删除 `import gc`，与 Task 2 Step 4 一致）

- [ ] **Step 2: 删除三个静态文件路由内的 import**

找到：

```python
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/captures/<filename>')
def captured_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['CAPTURES_FOLDER'], filename)

@app.route('/album/<filename>')
def album_file(filename):
    from flask import send_from_directory
    return send_from_directory(app.config['ALBUM_FOLDER'], filename)
```

替换为：

```python
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/captures/<filename>')
def captured_file(filename):
    return send_from_directory(app.config['CAPTURES_FOLDER'], filename)

@app.route('/album/<filename>')
def album_file(filename):
    return send_from_directory(app.config['ALBUM_FOLDER'], filename)
```

- [ ] **Step 3: 删除 save_photo 与 migrate_legacy_photos_to_album 内的 import shutil**

找到 `save_photo` 函数内的：

```python
    global saved_photos, last_captured_photo
    import shutil
```

替换为：

```python
    global saved_photos, last_captured_photo
```

找到 `migrate_legacy_photos_to_album` 函数内的：

```python
    import shutil
    changed = False
```

替换为：

```python
    changed = False
```

- [ ] **Step 4: 运行全部测试验证**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v 2>&1 | Select-Object -Last 5
```
Expected: 20 passed

---

### Task 4: /api/photos 加文件存在性缓存

**Files:**
- Modify: `backend/app.py` `/api/photos` 端点、新增 `_album_files_cache` 与失效逻辑

- [ ] **Step 1: 写失败测试 - 验证缓存命中时不调用 os.path.exists**

在 `backend/tests/test_app.py` 末尾追加：

```python
def test_photos_cache_avoids_repeated_path_exists(app, client, monkeypatch):
    """/api/photos 第二次请求应命中缓存，不再调用 os.path.exists。"""
    # 准备一张真实相册照片
    album_dir = app.app.config['ALBUM_FOLDER']
    with open(os.path.join(album_dir, 'a.jpg'), 'wb') as f:
        f.write(b'fake')

    # 通过 save_photo 走正式流程写入 saved_photos
    client.post('/api/photos/save', json={'filename': 'a.jpg'})

    call_count = {'n': 0}
    real_exists = os.path.exists

    def counting_exists(path):
        if 'album' in path and path.endswith('a.jpg'):
            call_count['n'] += 1
        return real_exists(path)

    # 第一次请求：建立缓存
    monkeypatch.setattr(os.path, 'exists', counting_exists)
    r1 = client.get('/api/photos')
    monkeypatch.setattr(os.path, 'exists', real_exists)
    assert r1.get_json()['success'] is True
    first_count = call_count['n']
    assert first_count >= 1  # 第一次确实检查了磁盘

    # 第二次请求：应命中缓存，不再检查磁盘
    monkeypatch.setattr(os.path, 'exists', counting_exists)
    r2 = client.get('/api/photos')
    monkeypatch.setattr(os.path, 'exists', real_exists)
    second_count = call_count['n']
    assert second_count == 0, f'缓存未生效，第二次仍调用了 {second_count} 次 os.path.exists'
```

- [ ] **Step 2: 运行测试验证失败**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/test_app.py::test_photos_cache_avoids_repeated_path_exists -v
```
Expected: FAIL（无缓存逻辑，第二次仍调用 os.path.exists）

- [ ] **Step 3: 添加缓存全局变量与失效函数**

在 `backend/app.py` 找到：

```python
# 已保存照片列表
saved_photos = []
```

在其后新增：

```python
# 相册文件存在性缓存：避免 /api/photos 每次请求 N 次 os.path.exists
# 在 save_photo / delete_photo / migrate_legacy_photos_to_album 后失效
_album_files_cache = None
_album_files_cache_mtime = 0
```

- [ ] **Step 4: 添加缓存获取函数**

在 `persist_state` 函数定义之后添加：

```python
def get_album_files():
    """返回 album/ 目录下文件名集合，带缓存。

    缓存基于目录 mtime 失效：目录内容变化时 mtime 更新，缓存自动重建。
    """
    global _album_files_cache, _album_files_cache_mtime
    album_dir = app.config['ALBUM_FOLDER']
    try:
        current_mtime = os.path.getmtime(album_dir)
    except OSError:
        return set()
    if _album_files_cache is not None and _album_files_cache_mtime == current_mtime:
        return _album_files_cache
    try:
        files = {f for f in os.listdir(album_dir) if os.path.isfile(os.path.join(album_dir, f))}
    except OSError:
        files = set()
    _album_files_cache = files
    _album_files_cache_mtime = current_mtime
    return files
```

- [ ] **Step 5: 改造 /api/photos 用缓存**

找到：

```python
@app.route('/api/photos', methods=['GET'])
def get_photos():
    """获取相册中的所有照片（读时与磁盘同步，剔除已丢失的文件）"""
    global saved_photos
    album_dir = app.config['ALBUM_FOLDER']
    existing = [
        p for p in saved_photos
        if os.path.exists(os.path.join(album_dir, p.get('filename', '')))
    ]
    # 同步内存列表，避免幽灵条目反复出现
    if len(existing) != len(saved_photos):
        saved_photos = existing
        persist_state()
    return jsonify({
        'success': True,
        'photos': saved_photos
    })
```

替换为：

```python
@app.route('/api/photos', methods=['GET'])
def get_photos():
    """获取相册中的所有照片（读时与磁盘同步，剔除已丢失的文件）"""
    global saved_photos
    album_files = get_album_files()
    existing = [
        p for p in saved_photos
        if p.get('filename', '') in album_files
    ]
    # 同步内存列表，避免幽灵条目反复出现
    if len(existing) != len(saved_photos):
        saved_photos = existing
        persist_state()
    return jsonify({
        'success': True,
        'photos': saved_photos
    })
```

- [ ] **Step 6: 运行测试验证通过**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/test_app.py::test_photos_cache_avoids_repeated_path_exists -v
```
Expected: PASS

- [ ] **Step 7: 运行全部测试验证无回归**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v 2>&1 | Select-Object -Last 5
```
Expected: 21 passed

---

### Task 5: /api/capture timeout 优化

**Files:**
- Modify: `backend/app.py` `/api/capture` 端点

- [ ] **Step 1: 缩短 requests.post timeout**

找到 `/api/capture` 中的：

```python
        response = requests.post(
            f"http://{esp32_ip}/capture",
            timeout=10
        )
```

替换为：

```python
        response = requests.post(
            f"http://{esp32_ip}/capture",
            timeout=5
        )
```

- [ ] **Step 2: 运行测试验证**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v 2>&1 | Select-Object -Last 5
```
Expected: 21 passed

---

### Task 6: 固件清理 g_latestFrame 死代码

**Files:**
- Modify: `firmware/esp32cam_unified/esp32cam_unified.ino`

- [ ] **Step 1: 删除 g_latestFrame 声明**

找到：

```cpp
// 共享状态
static volatile bool g_isCapturing  = false;  // 拍照进行中（暂停预览）
static volatile bool g_needCapture  = false;  // 收到拍照请求
static volatile bool g_flashEnabled = false;  // 闪光灯状态
static camera_fb_t*  g_latestFrame  = nullptr; // 最新预览帧
```

替换为：

```cpp
// 共享状态
static volatile bool g_isCapturing  = false;  // 拍照进行中（暂停预览）
static volatile bool g_needCapture  = false;  // 收到拍照请求
static volatile bool g_flashEnabled = false;  // 闪光灯状态
```

- [ ] **Step 2: 验证 g_latestFrame 未在其他位置被引用**

Run:
```powershell
Select-String -Path "f:\esp32cam\photo1\photo\photo-upload-system\firmware\esp32cam_unified\esp32cam_unified.ino" -Pattern "g_latestFrame"
```
Expected: 无输出（已全部删除）

- [ ] **Step 3: 验证 s_fbLock 是否被使用**

Run:
```powershell
Select-String -Path "f:\esp32cam\photo1\photo\photo-upload-system\firmware\esp32cam_unified\esp32cam_unified.ino" -Pattern "s_fbLock"
```
Expected: 仅在声明与 setup 中创建，无实际使用。

若 s_fbLock 也未使用，同样删除：

找到：

```cpp
static SemaphoreHandle_t s_fbLock = NULL;   // 帧缓冲锁
```

删除该行。

找到 setup() 中的：

```cpp
  s_fbLock = xSemaphoreCreateMutex();
```

删除该行。

- [ ] **Step 4: 验证固件无语法错误（仅静态检查关键符号）**

Run:
```powershell
Select-String -Path "f:\esp32cam\photo1\photo\photo-upload-system\firmware\esp32cam_unified\esp32cam_unified.ino" -Pattern "g_latestFrame|s_fbLock"
```
Expected: 无输出

---

### Task 7: 最终全量测试与验证

**Files:**
- 无修改

- [ ] **Step 1: 运行后端全部测试**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v
```
Expected: 21 passed

- [ ] **Step 2: 验证 app.py 可正常启动**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -c "import app; print('启动 OK'); print('threaded:', app.app.run.__defaults__ if hasattr(app.app.run, '__defaults__') else 'N/A'); print('frame_event:', app.frame_event); print('album cache:', app._album_files_cache)"
```
Expected: 输出 `启动 OK`、`frame_event: <threading.Event ...>`、`album cache: None`

- [ ] **Step 3: 验证固件无残留死代码引用**

Run:
```powershell
Select-String -Path "f:\esp32cam\photo1\photo\photo-upload-system\firmware\esp32cam_unified\esp32cam_unified.ino" -Pattern "g_latestFrame|s_fbLock|gc\.collect|cleanup_memory|LAST_CLEANUP_TIME"
```
Expected: 无输出

---

## 自检清单

- [x] **Spec coverage**: 性能优化目标全部覆盖
  - MJPEG 流延迟 → Task 1（Event 唤醒）
  - 并发能力 → Task 2（threaded=True）
  - 请求路径阻塞 → Task 2（移除 gc.collect）+ Task 3（import 提升）+ Task 5（timeout 缩短）
  - 相册查询性能 → Task 4（文件存在性缓存）
  - 固件内存占用 → Task 6（删除死代码）
  - 验证无回归 → Task 7
- [x] **No placeholders**: 所有步骤均含具体代码与命令
- [x] **Type consistency**: `frame_event`、`get_album_files`、`_album_files_cache` 在各 Task 中命名一致
