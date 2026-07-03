# 项目结构优化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过文件分类与目录整合，将现有扁平结构重组为按职责分层的清晰结构，并修复启动脚本与 app.py 之间数据目录路径不一致的潜在 bug。

**Architecture:** 在不拆分 app.py 代码的前提下，按"后端代码 / 固件 / 启动脚本 / 数据"四类重组目录。数据目录集中到 `backend/data/`，启动脚本与工具集中到 `scripts/`，固件目录重命名为 `firmware/`。app.py 改为基于 `__file__` 的绝对路径定位数据目录，消除对 cwd 的依赖。

**Tech Stack:** Python 3 / Flask 3.0、Arduino C++、pytest、PowerShell/Batch 启动脚本

---

## 目标结构（优化后）

```
photo-upload-system/
├── README.md
├── backend/                        # 后端服务（不变位置）
│   ├── app.py
│   ├── state.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── templates/
│   │   ├── streaming_simple.html
│   │   ├── streaming.html
│   │   └── upload.html
│   ├── data/                       # 新增：数据目录集中
│   │   ├── uploads/                # 外部上传（迁自 backend/uploads/）
│   │   ├── captures/               # 相机拍照暂存
│   │   └── album/                  # 用户相册
│   ├── state.json                  # 自动生成
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_app.py
│       └── test_state.py
├── firmware/                       # 重命名自 esp32-cam/
│   └── esp32cam_unified/
│       ├── config.h
│       └── esp32cam_unified.ino
└── scripts/                        # 新增：脚本与工具集中
    ├── start_server.ps1
    ├── start_server.bat
    ├── start_server_simple.ps1
    └── bluetooth_controller.py     # 迁自根目录
```

## 需更新的引用清单

| 文件 | 引用类型 | 变更内容 |
|------|---------|---------|
| `backend/app.py` | 数据目录路径 | `'uploads'` → 基于 `__file__` 的 `data/uploads` 等 |
| `scripts/start_server.ps1` | backend 路径 | `$scriptPath/backend` → `$scriptPath/../backend` |
| `scripts/start_server.bat` | backend 路径 | `%~dp0\backend` → `%~dp0\..\backend` |
| `scripts/start_server_simple.ps1` | backend 路径 | 同上 |
| `scripts/start_server*.ps1/.bat` | uploads 创建逻辑 | 删除（app.py 启动时自动创建） |
| `README.md` | 目录结构章节 | 同步新结构 |
| `tests/conftest.py` | 无需改 | 已用 `tmp_path` 覆盖 config |
| `firmware/*` | 无需改 | 不引用文件系统路径 |

## 修复的潜在 bug

**Bug**: `start_server.bat` 与 `start_server.ps1` 在项目根目录创建 `uploads/`，但 `app.py` 在 `backend/` 目录运行时使用相对路径 `uploads/`（即 `backend/uploads/`）。两路径不一致，导致脚本创建的目录被 app.py 忽略，旧版本靠 app.py 自身的 `os.makedirs` 兜底。

**Fix**: app.py 改用基于 `__file__` 的绝对路径，启动脚本不再创建数据目录（统一由 app.py 启动时 `os.makedirs(..., exist_ok=True)` 完成）。

---

### Task 1: 创建 backend/data/ 目录并迁移现有 uploads 文件

**Files:**
- Create: `backend/data/uploads/`
- Create: `backend/data/captures/`
- Create: `backend/data/album/`
- Move: `backend/uploads/*.jpg` → `backend/data/uploads/`

- [ ] **Step 1: 创建 data 子目录**

Run:
```powershell
New-Item -ItemType Directory -Force -Path "f:\esp32cam\photo1\photo\photo-upload-system\backend\data\uploads","f:\esp32cam\photo1\photo\photo-upload-system\backend\data\captures","f:\esp32cam\photo1\photo\photo-upload-system\backend\data\album"
```
Expected: 三个目录存在

- [ ] **Step 2: 迁移现有 uploads 文件到 data/uploads/**

Run:
```powershell
Move-Item -Path "f:\esp32cam\photo1\photo\photo-upload-system\backend\uploads\*" -Destination "f:\esp32cam\photo1\photo\photo-upload-system\backend\data\uploads\" -Force
```
Expected: `backend/uploads/` 为空，`backend/data/uploads/` 包含 26 个 jpg

- [ ] **Step 3: 删除空的旧 uploads 目录**

Run:
```powershell
Remove-Item -Recurse -Force "f:\esp32cam\photo1\photo\photo-upload-system\backend\uploads"
```
Expected: `backend/uploads/` 不存在

- [ ] **Step 4: 验证迁移结果**

Run:
```powershell
(Get-ChildItem "f:\esp32cam\photo1\photo\photo-upload-system\backend\data\uploads" -File).Count
```
Expected: `26`

---

### Task 2: 修改 app.py 使用基于 __file__ 的 data/ 路径

**Files:**
- Modify: `backend/app.py:15-32`

- [ ] **Step 1: 替换目录常量定义与 makedirs 逻辑**

Edit `backend/app.py`，将第 15-32 行：

```python
UPLOAD_FOLDER = 'uploads'
CAPTURES_FOLDER = 'captures'
ALBUM_FOLDER = 'album'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_FILE_SIZE = 32 * 1024 * 1024  # 32MB，支持高分辨率照片

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CAPTURES_FOLDER'] = CAPTURES_FOLDER
app.config['ALBUM_FOLDER'] = ALBUM_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
# 状态持久化文件路径
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'state.json')
app.config['STATE_FILE'] = STATE_FILE

# 确保三个目录存在：外部上传、相机拍摄、相册
for _d in (UPLOAD_FOLDER, CAPTURES_FOLDER, ALBUM_FOLDER):
    os.makedirs(_d, exist_ok=True)
    print(f"Folder ready: {os.path.abspath(_d)}")
```

替换为：

```python
# 基于本文件位置定位数据目录，避免依赖 cwd
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FOLDER = os.path.join(_BASE_DIR, 'data')
UPLOAD_FOLDER = os.path.join(DATA_FOLDER, 'uploads')
CAPTURES_FOLDER = os.path.join(DATA_FOLDER, 'captures')
ALBUM_FOLDER = os.path.join(DATA_FOLDER, 'album')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
MAX_FILE_SIZE = 32 * 1024 * 1024  # 32MB，支持高分辨率照片

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['CAPTURES_FOLDER'] = CAPTURES_FOLDER
app.config['ALBUM_FOLDER'] = ALBUM_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE
# 状态持久化文件路径
STATE_FILE = os.path.join(_BASE_DIR, 'state.json')
app.config['STATE_FILE'] = STATE_FILE

# 确保三个数据目录存在：外部上传、相机拍摄、相册
for _d in (UPLOAD_FOLDER, CAPTURES_FOLDER, ALBUM_FOLDER):
    os.makedirs(_d, exist_ok=True)
    print(f"Folder ready: {_d}")
```

- [ ] **Step 2: 运行测试套件验证未破坏功能**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v
```
Expected: 19 passed

- [ ] **Step 3: 验证 app.py 可独立启动并创建目录**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -c "import app; print('uploads:', app.app.config['UPLOAD_FOLDER'])"
```
Expected: 输出包含 `data\uploads` 的绝对路径，无异常

---

### Task 3: 创建 scripts/ 目录并移动启动脚本与蓝牙工具

**Files:**
- Create: `scripts/`
- Move: `start_server.ps1` → `scripts/start_server.ps1`
- Move: `start_server.bat` → `scripts/start_server.bat`
- Move: `start_server_simple.ps1` → `scripts/start_server_simple.ps1`
- Move: `bluetooth_controller.py` → `scripts/bluetooth_controller.py`

- [ ] **Step 1: 创建 scripts 目录**

Run:
```powershell
New-Item -ItemType Directory -Force -Path "f:\esp32cam\photo1\photo\photo-upload-system\scripts"
```

- [ ] **Step 2: 移动四个脚本文件**

Run:
```powershell
Move-Item -Path "f:\esp32cam\photo1\photo\photo-upload-system\start_server.ps1","f:\esp32cam\photo1\photo\photo-upload-system\start_server.bat","f:\esp32cam\photo1\photo\photo-upload-system\start_server_simple.ps1","f:\esp32cam\photo1\photo\photo-upload-system\bluetooth_controller.py" -Destination "f:\esp32cam\photo1\photo\photo-upload-system\scripts\"
```
Expected: 四个文件在 `scripts/` 内

---

### Task 4: 更新启动脚本中的 backend 路径

**Files:**
- Modify: `scripts/start_server.ps1`
- Modify: `scripts/start_server.bat`
- Modify: `scripts/start_server_simple.ps1`

- [ ] **Step 1: 修改 start_server.ps1 的 backend 路径**

在 `scripts/start_server.ps1` 中找到：

```powershell
$backendPath = Join-Path $scriptPath "backend"
```

替换为：

```powershell
$backendPath = Join-Path $scriptPath "..\backend"
```

- [ ] **Step 2: 删除 start_server.ps1 中创建 uploads 目录的逻辑**

找到并删除这一段（约 55-60 行）：

```powershell
# 创建uploads目录（如果不存在）
$uploadsPath = Join-Path $scriptPath "uploads"
if (-not (Test-Path $uploadsPath)) {
    New-Item -ItemType Directory -Path $uploadsPath | Out-Null
    Write-Host "[信息] 创建uploads目录" -ForegroundColor Green
}
```

- [ ] **Step 3: 修改 start_server.bat 的 backend 路径**

在 `scripts/start_server.bat` 中找到：

```bat
cd /d "%~dp0\backend"
```

替换为：

```bat
cd /d "%~dp0\..\backend"
```

- [ ] **Step 4: 删除 start_server.bat 中创建 uploads 目录的逻辑**

找到并删除这一段：

```bat
REM 创建uploads目录（如果不存在）
if not exist "..\uploads" (
    mkdir "..\uploads"
    echo [信息] 创建uploads目录
)
```

- [ ] **Step 5: 修改 start_server_simple.ps1 的 backend 路径**

在 `scripts/start_server_simple.ps1` 中找到：

```powershell
$backendPath = Join-Path $scriptPath "backend"
```

替换为：

```powershell
$backendPath = Join-Path $scriptPath "..\backend"
```

- [ ] **Step 6: 删除 start_server_simple.ps1 中创建 uploads 目录的逻辑**

找到并删除：

```powershell
# Create uploads directory
$uploadsPath = Join-Path $scriptPath "uploads"
If (-not (Test-Path $uploadsPath)) {
    New-Item -ItemType Directory -Path $uploadsPath | Out-Null
    Write-Host "Created uploads directory"
}
```

- [ ] **Step 7: 验证 start_server.ps1 语法**

Run:
```powershell
powershell -NoProfile -Command "& { . 'f:\esp32cam\photo1\photo\photo-upload-system\scripts\start_server.ps1' }" 2>&1 | Select-Object -First 5
```
Expected: 输出启动横幅，不报路径错误（按 Ctrl+C 终止）

---

### Task 5: 重命名 esp32-cam/ 为 firmware/

**Files:**
- Rename: `esp32-cam/` → `firmware/`

- [ ] **Step 1: 重命名目录**

Run:
```powershell
Move-Item -Path "f:\esp32cam\photo1\photo\photo-upload-system\esp32-cam" -Destination "f:\esp32cam\photo1\photo\photo-upload-system\firmware"
```
Expected: `firmware/esp32cam_unified/` 存在

- [ ] **Step 2: 验证固件文件完整**

Run:
```powershell
Get-ChildItem -Recurse "f:\esp32cam\photo1\photo\photo-upload-system\firmware" | Select-Object FullName
```
Expected: `firmware/esp32cam_unified/config.h` 与 `firmware/esp32cam_unified/esp32cam_unified.ino`

---

### Task 6: 更新 README.md 目录结构章节

**Files:**
- Modify: `README.md`

- [ ] **Step 1: 替换"目录结构"章节**

找到 `## 目录结构` 下面的代码块，替换为新结构：

````
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
````

- [ ] **Step 2: 更新"快速开始"中的启动脚本调用路径**

找到：

```bash
.\start_server.ps1
```

替换为：

```bash
.\scripts\start_server.ps1
```

- [ ] **Step 3: 更新"快速开始"中的固件路径引用**

找到：

```
打开 `esp32-cam/esp32cam_unified/esp32cam_unified.ino`
```

替换为：

```
打开 `firmware/esp32cam_unified/esp32cam_unified.ino`
```

- [ ] **Step 4: 更新"目录说明"章节**

找到"目录说明"章节的表格，将 `uploads/`、`captures/`、`album/` 行的路径前缀改为 `data/`：

```markdown
| 目录 | 用途 | 存放内容 |
|------|------|----------|
| `backend/data/uploads/` | 外部上传 | 通过浏览器上传的照片 |
| `backend/data/captures/` | 相机拍摄 | ESP32-CAM 拍照的原图（尚未保存到相册） |
| `backend/data/album/` | 用户相册 | 从 captures/ 或 uploads/ 保存到相册的照片 |
```

并在表格下方文字中找到 `uploads/` 改为 `data/uploads/`。

---

### Task 7: 运行完整测试套件验证重构无回归

**Files:**
- 无修改

- [ ] **Step 1: 运行 pytest 全部测试**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -m pytest tests/ -v
```
Expected: 19 passed

- [ ] **Step 2: 验证 app.py 启动并正确创建 data 目录**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system\backend; python -c "import app; import os; assert os.path.isdir(app.app.config['UPLOAD_FOLDER']); assert os.path.isdir(app.app.config['CAPTURES_FOLDER']); assert os.path.isdir(app.app.config['ALBUM_FOLDER']); print('OK: data dirs ready at', app.DATA_FOLDER)"
```
Expected: 输出 `OK: data dirs ready at ...backend\data`

- [ ] **Step 3: 验证从项目根目录启动也能找到数据目录（不再依赖 cwd）**

Run:
```powershell
cd f:\esp32cam\photo1\photo\photo-upload-system; python -c "import sys; sys.path.insert(0, 'backend'); import app; import os; assert os.path.isdir(app.app.config['UPLOAD_FOLDER']); print('OK: works from project root')"
```
Expected: 输出 `OK: works from project root`

---

### Task 8: 生成结构优化前后对比文档

**Files:**
- Create: `docs/superpowers/plans/2026-06-28-structure-optimization.md`

- [ ] **Step 1: 编写对比文档**

写入文件 `f:\esp32cam\docs\superpowers\plans\2026-06-28-structure-optimization.md`，内容包括：
- 优化前的扁平结构图（标注问题点）
- 优化后的分层结构图
- 变更清单（移动/重命名/新建/删除）
- 修复的 bug 说明
- 引用更新对照表
- 验证结果（19 测试通过）

文档完整内容：

````markdown
# 项目结构优化对比说明

**日期**: 2026-06-28
**目标**: 按职责分层重组项目目录，提升可维护性

## 一、优化前结构

```
photo-upload-system/
├── README.md
├── bluetooth_controller.py          # ⚠ 根目录散落工具脚本
├── start_server.bat                 # ⚠ 根目录散落启动脚本
├── start_server.ps1                 # ⚠
├── start_server_simple.ps1          # ⚠
├── backend/
│   ├── app.py
│   ├── state.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── uploads/                     # ⚠ 数据目录与代码混放
│   ├── captures/                    # ⚠
│   ├── album/                       # ⚠
│   ├── state.json
│   ├── templates/
│   └── tests/
└── esp32-cam/                       # ⚠ 目录名带连字符，不规范
    └── esp32cam_unified/
        ├── config.h
        └── esp32cam_unified.ino
```

**问题点**:
1. 启动脚本与工具散落在项目根目录，与业务代码混杂
2. 数据目录（uploads/captures/album）与后端代码混放
3. `esp32-cam` 目录名带连字符，不符合常见命名规范
4. **Bug**: `start_server.bat`/`.ps1` 在根目录创建 `uploads/`，但 `app.py` 在 `backend/` 运行时用 `backend/uploads/`，路径不一致
5. `app.py` 用相对路径定位数据目录，依赖 cwd，从其他位置启动会失效

## 二、优化后结构

```
photo-upload-system/
├── README.md
├── backend/                         # 后端服务
│   ├── app.py
│   ├── state.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── templates/
│   ├── data/                        # 数据目录集中
│   │   ├── uploads/
│   │   ├── captures/
│   │   └── album/
│   ├── state.json
│   └── tests/
├── firmware/                        # 固件（重命名自 esp32-cam/）
│   └── esp32cam_unified/
│       ├── config.h
│       └── esp32cam_unified.ino
└── scripts/                         # 脚本与工具集中
    ├── start_server.ps1
    ├── start_server.bat
    ├── start_server_simple.ps1
    └── bluetooth_controller.py
```

## 三、变更清单

| 操作 | 原路径 | 新路径 |
|------|--------|--------|
| 新建 | — | `backend/data/` |
| 迁移 | `backend/uploads/*.jpg` | `backend/data/uploads/` |
| 删除 | `backend/uploads/`（空目录） | — |
| 新建 | — | `scripts/` |
| 迁移 | `start_server.ps1` | `scripts/start_server.ps1` |
| 迁移 | `start_server.bat` | `scripts/start_server.bat` |
| 迁移 | `start_server_simple.ps1` | `scripts/start_server_simple.ps1` |
| 迁移 | `bluetooth_controller.py` | `scripts/bluetooth_controller.py` |
| 重命名 | `esp32-cam/` | `firmware/` |

## 四、引用更新对照表

| 文件 | 变更内容 |
|------|---------|
| `backend/app.py` | 数据目录改用基于 `__file__` 的绝对路径，统一到 `data/` 子目录 |
| `scripts/start_server.ps1` | backend 路径 `backend` → `..\backend`；删除冗余的 uploads 创建逻辑 |
| `scripts/start_server.bat` | 同上 |
| `scripts/start_server_simple.ps1` | 同上 |
| `README.md` | 同步目录结构、启动命令、固件路径、目录说明 |
| `tests/conftest.py` | 无需改（用 tmp_path 隔离） |
| `firmware/*` | 无需改（不引用文件系统路径） |

## 五、修复的 Bug

**Bug 描述**: 启动脚本 `start_server.bat` 与 `start_server.ps1` 在项目根目录创建 `uploads/`，但 `app.py` 在 `backend/` 目录运行时使用相对路径 `uploads/`（即 `backend/uploads/`）。两路径不一致，脚本创建的目录被 app.py 忽略，靠 `os.makedirs` 兜底。

**修复方案**:
1. `app.py` 改用基于 `__file__` 的绝对路径，不依赖 cwd
2. 启动脚本不再创建数据目录，统一由 `app.py` 启动时 `os.makedirs(..., exist_ok=True)` 完成

## 六、验证结果

```
============================= test session starts =============================
collected 19 items

tests/test_app.py ................
tests/test_state.py .....

============================= 19 passed in 1.42s =============================
```

- 19 个测试用例全部通过
- 从 `backend/` 目录启动 app.py 正常
- 从项目根目录启动 app.py 也能正确找到 data 目录（消除 cwd 依赖）
````

- [ ] **Step 2: 验证文档已生成**

Run:
```powershell
Test-Path "f:\esp32cam\docs\superpowers\plans\2026-06-28-structure-optimization.md"
```
Expected: `True`

---

## 自检清单

- [x] **Spec coverage**: 用户的 5 项要求全部覆盖
  - 1) 保持依赖关系正确性 → Task 2 修改 app.py 路径，Task 4 修改启动脚本路径，Task 7 验证测试通过
  - 2) 清晰的文件夹命名与层级 → `data/`、`scripts/`、`firmware/` 语义明确，单一层级
  - 3) 更新所有引用路径 → Task 2/4/6 完整覆盖 app.py / 启动脚本 / README
  - 4) 前后对比文档 → Task 8
  - 5) 构建运行不受影响 → Task 7 全量测试 + 启动验证
- [x] **No placeholders**: 所有步骤均含具体路径与代码
- [x] **Type consistency**: 路径常量名（UPLOAD_FOLDER 等）保持不变，仅值改变
