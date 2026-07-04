"""状态持久化：将非瞬态状态序列化为 JSON 文件。

仅持久化字段：saved_photos、flash_enabled、esp32_cam_ip、esp32_cam_ip_time。
不持久化 latest_frame、is_capturing 等瞬态字段。
"""
import copy
import json
import os
import threading

_lock = threading.Lock()

DEFAULT_STATE = {
    'saved_photos': [],
    'flash_enabled': False,
    'esp32_cam_ip': None,
    'esp32_cam_ip_time': 0,
}


def _default_state():
    """返回深拷贝的默认状态，避免调用方 mutate 污染 DEFAULT_STATE。"""
    return copy.deepcopy(DEFAULT_STATE)


def load_state(path):
    """加载状态文件。文件不存在或损坏时返回默认状态。"""
    if not os.path.exists(path):
        return _default_state()
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return _default_state()
    # 合并默认键，防止旧文件缺字段
    merged = _default_state()
    merged.update(data)
    return merged


def save_state(path, state):
    """原子写入状态文件（临时文件 + os.replace）。"""
    with _lock:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
