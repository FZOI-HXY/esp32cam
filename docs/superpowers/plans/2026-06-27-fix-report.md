# ESP32-CAM 项目问题修复说明文档

**修复日期:** 2026-06-27
**修复范围:** 架构梳理中识别的明确 Bug、死代码与安全隐患
**修复原则:** 最小化变更，不引入新功能，保持 API 兼容性

---

## 一、问题与修复总览

| # | 问题描述 | 根源 | 修复方法 | 涉及文件 |
|---|---------|------|----------|----------|
| 1 | 拍照/闪光灯控制在纯净环境报 ModuleNotFoundError | `app.py` 使用 `requests` 但 `requirements.txt` 未声明 | 补充 `requests==2.31.0` | `backend/requirements.txt` |
| 2 | 相册展示已删除照片，点击 404 | `get_photos()` 直接返回内存列表，不校验磁盘 | 读时过滤 + 同步内存 | `backend/app.py` |
| 3 | `/api/capture` 可被用于探测任意 IP (SSRF) | 仅校验 IP 格式，未限制网段 | 用 `ipaddress` 限制为私有网段 | `backend/app.py` |
| 4 | 启动脚本检查未使用的 cv2/numpy/PIL | 历史残留（曾计划 AI 增强） | 改为检查 flask/requests | 3 个启动脚本 |
| 5 | esp32cam_freertos 编译报重定义 | `g_bFlashEnabled` 重复声明 | 删除重复声明 | `esp32cam_freertos.ino` |
| 6 | esp32cam_freertos 信号量浪费内存 | 创建后从未使用 | 删除声明与创建代码 | `esp32cam_freertos.ino` |

---

## 二、详细修复记录

### 修复 1: 补充 requests 依赖

**问题描述:** `app.py` 的 `capture()` 和 `flash_control()` 内部 `import requests`，但 `requirements.txt` 未声明。在新环境按 `requirements.txt` 安装后，调用拍照或闪光灯接口会抛 `ModuleNotFoundError: No module named 'requests'`。

**修复方法:** 在 `requirements.txt` 追加 `requests==2.31.0`。

**测试验证:** `python -c "import requests"` 成功；现有测试通过。

---

### 修复 2: 相册与磁盘同步

**问题描述:** `get_photos()` 原样返回内存中的 `saved_photos`。当 `uploads/` 下文件被外部删除后，前端仍展示该照片，访问 `/uploads/<filename>` 返回 404。

**修复方法:** 在 `get_photos()` 中过滤掉磁盘上不存在的条目，并同步更新内存列表 `saved_photos`（避免幽灵条目反复出现）。不自动添加磁盘多出的文件，避免纳入 `/api/upload` 的非相册文件。

**代码变更:**

修改文件: [backend/app.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py) `get_photos` 函数

```python
# 修复前
@app.route('/api/photos', methods=['GET'])
def get_photos():
    return jsonify({'success': True, 'photos': saved_photos})

# 修复后
@app.route('/api/photos', methods=['GET'])
def get_photos():
    global saved_photos
    upload_dir = app.config['UPLOAD_FOLDER']
    existing = [
        p for p in saved_photos
        if os.path.exists(os.path.join(upload_dir, p.get('filename', '')))
    ]
    if len(existing) != len(saved_photos):
        saved_photos = existing
    return jsonify({'success': True, 'photos': saved_photos})
```

**测试用例:**
- `test_get_photos_filters_missing_files`: 验证磁盘不存在的照片被排除
- `test_get_photos_syncs_memory_list`: 验证内存列表同步剔除

**测试结果:** 2 个测试 PASS。

---

### 修复 3: SSRF 防护

**问题描述:** `/api/capture` 仅用正则校验 IP 格式，未限制网段。攻击者可传入 `8.8.8.8` 等公网 IP，利用服务端发起 `requests.post("http://8.8.8.8/capture")`，构成 SSRF。

**修复方法:**
1. 将 `import requests`、`import re`、`import ipaddress` 统一移到文件顶部（原为函数内局部导入，影响可测试性）
2. 使用标准库 `ipaddress` 校验目标 IP 必须为 `is_private`/`is_loopback`/`is_link_local`
3. ESP32-CAM 始终在局域网内，不影响正常使用

**代码变更:**

修改文件: [backend/app.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/app.py)

```python
# 修复后新增的校验
try:
    addr = ipaddress.ip_address(esp32_ip)
except ValueError:
    return jsonify({'error': '无效的IP地址格式'}), 400
if not (addr.is_private or addr.is_loopback or addr.is_link_local):
    return jsonify({'error': '仅允许访问局域网内的 ESP32-CAM 地址'}), 400
```

**测试用例:**
- `test_capture_rejects_public_ip`: 公网 IP 8.8.8.8 被拒（400），且未发起 HTTP 请求
- `test_capture_accepts_private_ip`: 私有 IP 192.168.1.100 被接受并转发
- `test_capture_accepts_loopback`: 127.0.0.1 被接受

**测试结果:** 3 个测试 PASS。
**兼容性:** ESP32-CAM 使用 192.168.x.x/10.x.x.x，均在允许范围。

---

### 修复 4: 启动脚本依赖检查

**问题描述:** `start_server.ps1`、`start_server_simple.ps1`、`start_server.bat` 均检查 `cv2`/`numpy`/`PIL`，但 `app.py` 已移除 AI 增强逻辑，`requirements.txt` 也未声明这些库。导致每次启动都误报缺依赖并尝试安装。

**修复方法:** 将检查项改为 `flask`/`requests`（与 `requirements.txt` 一致）。

**涉及文件:**
- [start_server.ps1](file:///f:/esp32cam/photo1/photo/photo-upload-system/start_server.ps1)
- [start_server_simple.ps1](file:///f:/esp32cam/photo1/photo/photo-upload-system/start_server_simple.ps1)
- [start_server.bat](file:///f:/esp32cam/photo1/photo/photo-upload-system/start_server.bat)

**测试验证:** Grep 确认三个脚本中无 `cv2`/`numpy`/`PIL` 残留。

---

### 修复 5: 删除重复声明

**问题描述:** [esp32cam_freertos.ino](file:///f:/esp32cam/photo1/photo/photo-upload-system/esp32-cam/esp32cam_freertos/esp32cam_freertos.ino) 第 32 行 `bool g_bFlashEnabled = false;`，第 264 行又出现 `bool g_bFlashEnabled = false;`。C++ 全局变量重定义违反 ODR，多数编译器报错。

**修复方法:** 删除第 264 行的重复声明及其上方注释，保留第 32 行的原始声明。

**测试验证:** Grep 确认仅第 28 行一处声明。

---

### 修复 6: 删除未使用信号量

**问题描述:** `xCaptureSemaphore`/`xPreviewSemaphore` 在 `setup()` 中创建并做 NULL 检查，但全文件无 `xSemaphoreTake`/`xSemaphoreGive` 调用。双核间实际靠 `g_bNeedCapture` 等标志位通信。死代码浪费 RAM 并误导维护者。

**修复方法:** 删除第 25-26 行声明、第 420-425 行创建与检查代码。

**测试验证:** Grep 确认无 `xSemaphore`/`SemaphoreHandle_t`/`xCaptureSemaphore`/`xPreviewSemaphore` 残留。

---

## 三、测试结果汇总

**测试文件:** [backend/tests/test_app.py](file:///f:/esp32cam/photo1/photo/photo-upload-system/backend/tests/test_app.py)

| 测试名 | 覆盖修复 | 结果 |
|--------|----------|------|
| `test_app_importable` | 基础设施 | PASS |
| `test_root_route_exists` | 基础设施 | PASS |
| `test_get_photos_filters_missing_files` | 修复 2 | PASS |
| `test_get_photos_syncs_memory_list` | 修复 2 | PASS |
| `test_capture_rejects_public_ip` | 修复 3 | PASS |
| `test_capture_accepts_private_ip` | 修复 3 | PASS |
| `test_capture_accepts_loopback` | 修复 3 | PASS |

**总计:** 7 个测试，全部 PASS，用时 0.43s。

**运行命令:**
```
cd f:\esp32cam\photo1\photo\photo-upload-system\backend
python -m pytest tests/test_app.py -v
```

---

## 四、代码变更记录

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `backend/requirements.txt` | 修改 | +`requests==2.31.0` |
| `backend/requirements-dev.txt` | 新增 | `pytest==7.4.4` |
| `backend/app.py` | 修改 | `get_photos` 同步逻辑、`capture` SSRF 防护、`import ipaddress/re/requests` 移至顶部 |
| `backend/tests/__init__.py` | 新增 | 测试包标识 |
| `backend/tests/conftest.py` | 新增 | pytest 夹具（temp 上传目录、状态重置） |
| `backend/tests/test_app.py` | 新增 | 7 个测试用例 |
| `start_server.ps1` | 修改 | 依赖检查改为 flask/requests |
| `start_server_simple.ps1` | 修改 | 同上 |
| `start_server.bat` | 修改 | 同上 |
| `esp32cam_freertos.ino` | 修改 | 删除重复声明、未用信号量 |

---

## 五、未引入新功能确认

- 未新增任何 API 路由
- 未改变任何现有路由的请求/响应格式（仅在错误分支返回 400 而非 500）
- 未改变前端行为
- 未改变 ESP32-CAM 固件功能逻辑
- 未改变硬件引脚配置
- SSRF 防护仅拒绝公网 IP，ESP32-CAM 局域网地址不受影响

---

## 六、范围外事项（需独立计划）

以下问题在架构梳理中识别但本计划未处理，属于功能增强或大型重构：

1. **预览性能优化:** 当前 `<img>` 轮询，可改为 MJPEG 流或 WebSocket
2. **状态持久化:** `saved_photos`、`flash_enabled` 等重启丢失，可落盘 JSON
3. **认证机制:** 当前无任何鉴权，局域网内任意设备可操作
4. **固件碎片化:** 6 个 .ino 文件大量重复，可合并为可配置单版本
5. **相册与上传目录分离:** `/api/upload` 与相册共用 `uploads/`，语义混淆
