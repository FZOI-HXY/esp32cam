import os
import sys
import shutil
import tempfile
from pathlib import Path

import pytest

# 将 backend 目录加入 sys.path，使 `import app` 可用
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture
def app(tmp_path, monkeypatch):
    """提供隔离的 Flask app 实例，使用临时上传与状态目录。"""
    import app as app_module
    upload_dir = str(tmp_path / "uploads")
    captures_dir = str(tmp_path / "captures")
    album_dir = str(tmp_path / "album")
    state_file = str(tmp_path / "state.json")
    for d in (upload_dir, captures_dir, album_dir):
        os.makedirs(d, exist_ok=True)
    monkeypatch.setitem(app_module.app.config, 'UPLOAD_FOLDER', upload_dir)
    monkeypatch.setitem(app_module.app.config, 'CAPTURES_FOLDER', captures_dir)
    monkeypatch.setitem(app_module.app.config, 'ALBUM_FOLDER', album_dir)
    monkeypatch.setitem(app_module.app.config, 'STATE_FILE', state_file)
    app_module.UPLOAD_FOLDER = upload_dir
    app_module.CAPTURES_FOLDER = captures_dir
    app_module.ALBUM_FOLDER = album_dir
    # 重置全局状态
    app_module.latest_frame = None
    app_module.latest_frame_time = 0
    app_module.frame_id = 0
    app_module.esp32_cam_ip = None
    app_module.esp32_cam_ip_time = 0
    app_module.is_capturing = False
    app_module.last_capture_time = 0
    app_module.last_captured_photo = None
    app_module.flash_enabled = False
    app_module.saved_photos = []
    # 从空状态文件重新加载（确保干净起点）
    app_module.reload_state_from_disk()
    yield app_module


@pytest.fixture
def client(app):
    """Flask 测试客户端。"""
    yield app.app.test_client()
