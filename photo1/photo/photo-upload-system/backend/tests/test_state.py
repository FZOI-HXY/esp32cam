"""state 模块：JSON 状态持久化。"""
import os


def test_load_state_returns_defaults_when_file_missing(tmp_path):
    import state
    s = state.load_state(str(tmp_path / "nonexistent.json"))
    assert s == {
        'saved_photos': [],
        'flash_enabled': False,
        'esp32_cam_ip': None,
        'esp32_cam_ip_time': 0,
    }


def test_save_then_load_roundtrip(tmp_path):
    import state
    path = str(tmp_path / "state.json")
    payload = {
        'saved_photos': [{'filename': 'a.jpg', 'url': '/album/a.jpg', 'saved_at': 1.0, 'selected': False, 'location': 'album'}],
        'flash_enabled': True,
        'esp32_cam_ip': '192.168.1.50',
        'esp32_cam_ip_time': 12345.0,
    }
    state.save_state(path, payload)
    loaded = state.load_state(path)
    assert loaded == payload


def test_save_state_is_atomic(tmp_path):
    """保存应通过临时文件 + os.replace，避免半写入。"""
    import state
    path = str(tmp_path / "state.json")
    state.save_state(path, {'saved_photos': [], 'flash_enabled': False, 'esp32_cam_ip': None, 'esp32_cam_ip_time': 0})
    assert not os.path.exists(path + '.tmp')
    assert os.path.exists(path)


def test_load_state_recovers_from_corrupt_json(tmp_path):
    """损坏的 JSON 应回退到默认值，不抛异常。"""
    import state
    path = str(tmp_path / "state.json")
    with open(path, 'w', encoding='utf-8') as f:
        f.write("{not valid json")
    s = state.load_state(path)
    assert s['saved_photos'] == []
    assert s['flash_enabled'] is False
