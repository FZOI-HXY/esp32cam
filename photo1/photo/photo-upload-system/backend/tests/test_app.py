"""app 模块可导入且核心路由存在的冒烟测试。"""


def test_app_importable(app):
    """验证 app 模块可被导入。"""
    assert app is not None
    assert hasattr(app, 'app')


def test_root_route_exists(app, client):
    """验证根路由可访问（返回 200）。"""
    resp = client.get('/')
    assert resp.status_code == 200


import os


def test_get_photos_filters_missing_files(app, client, tmp_path):
    """相册列表应排除磁盘上已不存在的照片。"""
    # 准备：两张照片，一张存在一张不存在
    import os
    album_dir = app.app.config['ALBUM_FOLDER']
    existing_file = os.path.join(album_dir, "esp32cam_existing.jpg")
    with open(existing_file, 'wb') as f:
        f.write(b"\xff\xd8\xff\xe0fake-jpeg")
    ghost_file = "esp32cam_deleted.jpg"  # 不在磁盘上

    app.saved_photos = [
        {
            'filename': 'esp32cam_existing.jpg',
            'url': '/album/esp32cam_existing.jpg',
            'saved_at': 1000.0,
            'selected': False,
        },
        {
            'filename': ghost_file,
            'url': f'/album/{ghost_file}',
            'saved_at': 2000.0,
            'selected': False,
        },
    ]

    resp = client.get('/api/photos')
    assert resp.status_code == 200
    data = resp.get_json()
    filenames = [p['filename'] for p in data['photos']]
    assert 'esp32cam_existing.jpg' in filenames
    assert ghost_file not in filenames


def test_get_photos_syncs_memory_list(app, client, tmp_path):
    """读取后内存列表也应剔除幽灵条目，避免反复出现。"""
    import os
    album_dir = app.app.config['ALBUM_FOLDER']
    existing_file = os.path.join(album_dir, "keep.jpg")
    with open(existing_file, 'wb') as f:
        f.write(b"\xff\xd8fake")

    app.saved_photos = [
        {'filename': 'keep.jpg', 'url': '/album/keep.jpg', 'saved_at': 1.0, 'selected': False},
        {'filename': 'gone.jpg', 'url': '/album/gone.jpg', 'saved_at': 2.0, 'selected': False},
    ]

    client.get('/api/photos')
    # 第二次调用，验证内存已被清理
    resp = client.get('/api/photos')
    filenames = [p['filename'] for p in resp.get_json()['photos']]
    assert filenames == ['keep.jpg']


from unittest.mock import patch, MagicMock


def test_capture_rejects_public_ip(app, client):
    """拍照接口应拒绝公网 IP，防止 SSRF。"""
    with patch('app.requests') as mock_req:
        mock_req.exceptions.RequestException = Exception
        resp = client.post('/api/capture', json={'esp32_ip': '8.8.8.8'})
        assert resp.status_code == 400
        data = resp.get_json()
        assert 'error' in data
        # 确保未实际发起 HTTP 请求
        mock_req.post.assert_not_called()
        assert not app.is_capturing


def test_capture_accepts_private_ip(app, client, tmp_path):
    """拍照接口应接受私有网段 IP 并转发请求。"""
    with patch('app.requests') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.post.return_value = mock_resp
        mock_req.exceptions.RequestException = Exception

        resp = client.post('/api/capture', json={'esp32_ip': '192.168.1.100'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        # 验证确实向 ESP32 发起了请求
        mock_req.post.assert_called_once()
        call_args = mock_req.post.call_args
        assert '192.168.1.100' in call_args[0][0]


def test_capture_accepts_loopback(app, client):
    """127.0.0.1 应被接受（本地回环属于私有范围）。"""
    with patch('app.requests') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.post.return_value = mock_resp
        mock_req.exceptions.RequestException = Exception

        resp = client.post('/api/capture', json={'esp32_ip': '127.0.0.1'})
        assert resp.status_code == 200


def test_stream_returns_multipart_content_type(app, client):
    """/api/stream 应返回 multipart/x-mixed-replace 内容类型。"""
    app.latest_frame = b"\xff\xd8\xff\xe0fake"
    app.frame_id = 42
    resp = client.get('/api/stream')
    assert resp.status_code == 200
    assert 'multipart/x-mixed-replace' in resp.content_type
    assert 'boundary=frame' in resp.content_type


def test_stream_yields_frame_only_on_change(app, client):
    """首帧应包含 boundary、Content-Type 与帧数据。"""
    app.latest_frame = b"\xff\xd8first"
    app.frame_id = 1
    resp = client.get('/api/stream', buffered=False)
    # 只取生成器产生的第一个数据块（首帧立即推送，因为 last_id=-1 != 1）
    first_chunk = next(resp.response)
    assert b'--frame\r\n' in first_chunk
    assert b'Content-Type: image/jpeg' in first_chunk
    assert b'\xff\xd8first' in first_chunk
    resp.close()


def test_state_persists_flash_enabled_across_reload(app, client):
    """闪光灯状态应在 reload 后保留。"""
    with patch('app.requests') as mock_req:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_req.post.return_value = mock_resp
        mock_req.exceptions.RequestException = Exception
        client.post('/api/flash', json={'enable': True, 'esp32_ip': '192.168.1.50'})
    # 模拟服务重启：从磁盘重新加载
    app.flash_enabled = False
    app.esp32_cam_ip = None
    app.reload_state_from_disk()
    assert app.flash_enabled is True
    assert app.esp32_cam_ip == '192.168.1.50'


def test_state_persists_saved_photos_across_reload(app, client, tmp_path):
    """相册列表应在 reload 后保留。"""
    # 准备一张照片在 captures 目录（save_photo 优先查找的位置）
    import os
    captures_dir = app.app.config['CAPTURES_FOLDER']
    with open(os.path.join(captures_dir, "pic.jpg"), 'wb') as f:
        f.write(b"\xff\xd8fake")

    client.post(
        '/api/photos/save',
        json={'filename': 'pic.jpg'}
    )
    # 模拟重启
    app.saved_photos = []
    app.reload_state_from_disk()
    assert len(app.saved_photos) == 1
    assert app.saved_photos[0]['filename'] == 'pic.jpg'


def test_save_photo_moves_file_from_captures_to_album(app, client):
    """save_photo 应将文件从 captures/ 移动到 album/，源文件不再存在。"""
    import os
    captures_dir = app.app.config['CAPTURES_FOLDER']
    album_dir = app.app.config['ALBUM_FOLDER']
    with open(os.path.join(captures_dir, "move_me.jpg"), 'wb') as f:
        f.write(b"\xff\xd8fake")

    resp = client.post(
        '/api/photos/save',
        json={'filename': 'move_me.jpg'}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['photo']['url'] == '/album/move_me.jpg'
    assert body['photo']['location'] == 'album'
    # 源文件已移走
    assert not os.path.exists(os.path.join(captures_dir, "move_me.jpg"))
    # 目标文件存在
    assert os.path.exists(os.path.join(album_dir, "move_me.jpg"))


def test_migrate_legacy_moves_old_uploads_to_album(app, tmp_path, monkeypatch):
    """migrate_legacy_photos_to_album 应将旧 uploads/ 照片移到 album/ 并更新元数据。"""
    import os
    # 构造 saved_photos 引用 uploads 中的文件
    uploads_dir = app.app.config['UPLOAD_FOLDER']
    album_dir = app.app.config['ALBUM_FOLDER']
    with open(os.path.join(uploads_dir, "legacy.jpg"), 'wb') as f:
        f.write(b"\xff\xd8legacy")
    app.saved_photos = [{
        'filename': 'legacy.jpg',
        'url': '/uploads/legacy.jpg',  # 旧 URL
        'saved_at': 1.0,
        'selected': False,
    }]
    app.persist_state()

    # 执行迁移
    app.migrate_legacy_photos_to_album()

    assert not os.path.exists(os.path.join(uploads_dir, "legacy.jpg"))
    assert os.path.exists(os.path.join(album_dir, "legacy.jpg"))
    assert app.saved_photos[0]['url'] == '/album/legacy.jpg'
    assert app.saved_photos[0]['location'] == 'album'

    # 再次迁移应幂等（不再尝试移动）
    app.migrate_legacy_photos_to_album()
    assert os.path.exists(os.path.join(album_dir, "legacy.jpg"))


def test_high_resolution_capture_saved_to_captures(app, client):
    """高分辨率拍照帧应保存到 captures/ 目录，URL 为 /captures/。"""
    fake_jpeg = b"\xff\xd8\xff\xe0fake-high-res"
    resp = client.post(
        '/api/raw',
        data=fake_jpeg,
        content_type='image/jpeg',
        headers={'X-Resolution': 'high', 'X-ESP32-IP': '192.168.1.50'}
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['success'] is True
    assert body['url'].startswith('/captures/')
    assert body['location'] == 'captures'
    # 文件实际在 captures 目录
    import os
    capture_path = os.path.join(app.app.config['CAPTURES_FOLDER'], body['filename'])
    assert os.path.exists(capture_path)
    with open(capture_path, 'rb') as f:
        assert f.read() == fake_jpeg
    # 不应出现在 uploads
    upload_path = os.path.join(app.app.config['UPLOAD_FOLDER'], body['filename'])
    assert not os.path.exists(upload_path)


def test_preview_upload_does_not_persist_state_repeatedly(app, client):
    """同一 ESP32-CAM 重复上传预览帧不应每次触发磁盘写入。"""
    save_calls = []
    original_persist = app.persist_state

    def counting_persist():
        save_calls.append(1)
        original_persist()

    app.persist_state = counting_persist

    headers = {'X-ESP32-IP': '192.168.1.77'}
    # 同一 IP 连续上传 5 帧预览
    for _ in range(5):
        client.post(
            '/api/raw',
            data=b"\xff\xd8preview",
            content_type='image/jpeg',
            headers=headers
        )
    # 仅首次 IP 变化触发一次持久化
    assert len(save_calls) == 1
    assert app.esp32_cam_ip == '192.168.1.77'


import time as _time


def test_stream_pushes_frame_immediately_after_update(app, client):
    """新帧到达后，stream 应在 100ms 内推送，无需等待 67ms sleep 周期。"""
    app.latest_frame = None
    app.frame_id = 0

    import threading
    result = {'chunk': None}

    def reader():
        resp = client.get('/api/stream')
        try:
            result['chunk'] = next(resp.response)
        except StopIteration:
            result['chunk'] = b''
        resp.close()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    _time.sleep(0.2)

    app.latest_frame = b'\xff\xd8\xff\xe0test'
    app.frame_id = 1
    if hasattr(app, 'frame_event'):
        app.frame_event.set()

    t.join(timeout=2.0)
    assert result['chunk'] is not None
    assert b'test' in result['chunk']


def test_photos_cache_avoids_repeated_path_exists(app, client, monkeypatch):
    """/api/photos 第二次请求应命中缓存，不再调用 os.path.exists。"""
    album_dir = app.app.config['ALBUM_FOLDER']
    with open(os.path.join(album_dir, 'a.jpg'), 'wb') as f:
        f.write(b'fake')

    client.post('/api/photos/save', json={'filename': 'a.jpg'})

    call_count = {'n': 0}
    real_exists = os.path.exists

    def counting_exists(path):
        if 'album' in path and path.endswith('a.jpg'):
            call_count['n'] += 1
        return real_exists(path)

    monkeypatch.setattr(os.path, 'exists', counting_exists)
    r1 = client.get('/api/photos')
    monkeypatch.setattr(os.path, 'exists', real_exists)
    assert r1.get_json()['success'] is True
    first_count = call_count['n']
    assert first_count >= 1

    call_count['n'] = 0  # 重置计数器，仅统计第二次请求
    monkeypatch.setattr(os.path, 'exists', counting_exists)
    r2 = client.get('/api/photos')
    monkeypatch.setattr(os.path, 'exists', real_exists)
    second_count = call_count['n']
    assert second_count == 0, f'缓存未生效，第二次仍调用了 {second_count} 次 os.path.exists'

