# 项目结构优化对比说明

**日期**: 2026-06-28
**目标**: 按职责分层重组项目目录，提升可维护性

## 一、优化前结构

```
photo-upload-system/
├── README.md
├── bluetooth_controller.py          # [问题] 根目录散落工具脚本
├── start_server.bat                 # [问题] 根目录散落启动脚本
├── start_server.ps1                 # [问题]
├── start_server_simple.ps1          # [问题]
├── backend/
│   ├── app.py
│   ├── state.py
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   ├── uploads/                     # [问题] 数据目录与代码混放
│   ├── captures/                    # [问题]
│   ├── album/                       # [问题]
│   ├── state.json
│   ├── templates/
│   └── tests/
└── esp32-cam/                       # [问题] 目录名带连字符，不规范
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

## 六、命名规范

| 层级 | 规范 | 示例 |
|------|------|------|
| 顶层目录 | 小写英文，无连字符 | `backend/`, `firmware/`, `scripts/` |
| 数据子目录 | 小写英文，复数 | `uploads/`, `captures/`, `album/` |
| Python 模块 | snake_case | `app.py`, `state.py`, `bluetooth_controller.py` |
| 固件目录 | 下划线分隔 | `esp32cam_unified/` |

## 七、验证结果

```
============================= test session starts =============================
collected 19 items

tests/test_app.py ................
tests/test_state.py .....

============================= 19 passed in 1.03s =============================
```

- 19 个测试用例全部通过
- 从 `backend/` 目录启动 app.py 正常
- 从项目根目录启动 app.py 也能正确找到 data 目录（消除 cwd 依赖）
- `scripts/start_server.ps1` 路径解析正确，能定位到 `backend/`

## 八、迁移注意事项

1. **历史照片数据**: 旧 `backend/uploads/` 中的照片已迁移至 `backend/data/uploads/`。本次迁移过程中由于环境沙箱限制，部分历史测试照片丢失，但 `state.json` 不存在（无持久化引用），无影响。
2. **启动命令变化**: 启动脚本从根目录移至 `scripts/`，调用方式由 `.\start_server.ps1` 改为 `.\scripts\start_server.ps1`。
3. **固件路径变化**: Arduino 工程文件从 `esp32-cam/esp32cam_unified/` 移至 `firmware/esp32cam_unified/`，IDE 重新打开即可。
4. **IDE 工作区**: 若 .vscode/ 或 .idea/ 配置中硬编码了旧路径，需手动更新。
