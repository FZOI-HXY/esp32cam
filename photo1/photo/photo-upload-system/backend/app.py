from flask import Flask, render_template, request, jsonify, Response, send_from_directory
import os
from werkzeug.utils import secure_filename
import uuid
import base64
import time
import threading
import ipaddress
import re
import shutil
import requests
import state as state_module

app = Flask(__name__)

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

# 存储最新的画面数据
latest_frame = None
latest_frame_time = 0
# 帧版本号，每次更新预览帧时自增，用于 MJPEG 流去重
frame_id = 0
# 帧到达条件变量：新帧写入时 notify_all，所有 stream 订阅者各自 wait 后推送。
# 使用 Condition 而非 Event 避免多客户端 clear() 互相吃帧的问题。
frame_condition = threading.Condition()


class _FrameEventShim:
    """向后兼容层：测试代码调用 frame_event.set() 时通知所有流订阅者。"""

    def set(self):
        with frame_condition:
            frame_condition.notify_all()


# 保留 frame_event 名称供外部代码/测试兼容
frame_event = _FrameEventShim()

# 存储ESP32-CAM的IP地址
esp32_cam_ip = None
esp32_cam_ip_time = 0
ESP32_IP_TIMEOUT = 60  # IP地址有效期60秒

# 拍照状态管理
is_capturing = False
last_capture_time = 0
CAPTURE_TIMEOUT = 30  # 拍照超时时间（秒），高分辨率需要更长时间
last_captured_photo = None  # 存储最近拍摄的照片

# 闪光灯控制
flash_enabled = False  # 闪光灯状态

# 已保存照片列表
saved_photos = []
# 相册文件存在性缓存：避免 /api/photos 每次请求 N 次 os.path.exists
# 在 save_photo / delete_photo / migrate_legacy_photos_to_album 后失效
_album_files_cache = None
_album_files_cache_mtime = 0

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def validate_esp32_ip(ip_str):
    """校验 ESP32-CAM IP 地址：仅允许私有/回环/链路本地地址，防止 SSRF。

    返回校验通过的 IP 字符串；不通过返回 None。
    """
    if not ip_str:
        return None
    ip_pattern = r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$'
    if not re.match(ip_pattern, ip_str):
        return None
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return None
    if not (addr.is_private or addr.is_loopback or addr.is_link_local):
        return None
    return ip_str


def is_safe_filename(filename):
    """检查文件名是否安全：不含路径分隔符或 .. 遍历，防止路径遍历攻击。"""
    if not filename:
        return False
    # 拒绝包含路径分隔符或 .. 的文件名
    if '/' in filename or '\\' in filename or '..' in filename:
        return False
    # 文件名应与 basename 一致（即不含目录部分）
    return filename == os.path.basename(filename)

def reload_state_from_disk():
    """从 state.json 加载持久化字段到全局变量。"""
    global saved_photos, flash_enabled, esp32_cam_ip, esp32_cam_ip_time
    s = state_module.load_state(app.config['STATE_FILE'])
    saved_photos = s.get('saved_photos', [])
    flash_enabled = s.get('flash_enabled', False)
    esp32_cam_ip = s.get('esp32_cam_ip', None)
    esp32_cam_ip_time = s.get('esp32_cam_ip_time', 0)


def persist_state():
    """将持久化字段写入 state.json。"""
    state_module.save_state(app.config['STATE_FILE'], {
        'saved_photos': saved_photos,
        'flash_enabled': flash_enabled,
        'esp32_cam_ip': esp32_cam_ip,
        'esp32_cam_ip_time': esp32_cam_ip_time,
    })

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
        files = {f for f in os.listdir(album_dir) if os.path.exists(os.path.join(album_dir, f))}
    except OSError:
        files = set()
    _album_files_cache = files
    _album_files_cache_mtime = current_mtime
    return files

# 启动时加载持久化状态（必须在上述全局变量与函数定义之后）
reload_state_from_disk()
print(f"状态已加载: 相册 {len(saved_photos)} 张, 闪光灯 {'开' if flash_enabled else '关'}")


def migrate_legacy_photos_to_album():
    """一次性迁移：把 saved_photos 引用的旧 uploads/ 文件移到 album/，并更新 url/location 字段。

    幂等设计：若文件已在 album/ 则不再移动；若 uploads/ 与 album/ 不存在则跳过。
    迁移完成后回写 state.json，避免下次启动重复迁移。
    """
    changed = False
    uploads_dir = app.config['UPLOAD_FOLDER']
    album_dir = app.config['ALBUM_FOLDER']
    os.makedirs(album_dir, exist_ok=True)
    for photo in saved_photos:
        filename = photo.get('filename')
        if not filename:
            continue
        album_path = os.path.join(album_dir, filename)
        # 已在 album/：仅更新元数据
        if os.path.exists(album_path):
            if photo.get('url') != f'/album/{filename}' or photo.get('location') != 'album':
                photo['url'] = f'/album/{filename}'
                photo['location'] = 'album'
                changed = True
            continue
        # 不在 album/，尝试从 uploads/ 迁移
        legacy_path = os.path.join(uploads_dir, filename)
        if os.path.exists(legacy_path):
            shutil.move(legacy_path, album_path)
            photo['url'] = f'/album/{filename}'
            photo['location'] = 'album'
            changed = True
            print(f"迁移旧相册照片: {filename} (uploads -> album)")
    if changed:
        persist_state()


# 执行一次性迁移
migrate_legacy_photos_to_album()

@app.route('/')
def index():
    print("访问根路径")
    return render_template('streaming_simple.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': '没有选择文件'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': '没有选择文件'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'error': '不支持的文件格式'}), 400
    
    original_filename = secure_filename(file.filename)
    file_extension = original_filename.rsplit('.', 1)[1].lower()
    new_filename = f"{uuid.uuid4().hex}.{file_extension}"
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    file.save(filepath)
    
    return jsonify({
        'success': True,
        'filename': new_filename,
        'original_filename': original_filename,
        'size': os.path.getsize(filepath)
    })

@app.route('/api/upload', methods=['POST'])
def api_upload():
    if 'image' not in request.files:
        return jsonify({'error': '没有图片数据'}), 400
    
    file = request.files['image']
    
    if file.filename == '':
        new_filename = f"esp32cam_{uuid.uuid4().hex}.jpg"
    else:
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else 'jpg'
        new_filename = f"{uuid.uuid4().hex}.{file_extension}"
    
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], new_filename)
    file.save(filepath)
    
    return jsonify({
        'success': True,
        'filename': new_filename,
        'size': os.path.getsize(filepath),
        'url': f'/uploads/{new_filename}'
    })

@app.route('/api/raw', methods=['POST'])
def api_raw_upload():
    global latest_frame, latest_frame_time, esp32_cam_ip, esp32_cam_ip_time, is_capturing, last_captured_photo, frame_id
    
    if not request.data:
        return jsonify({'error': '没有接收到数据'}), 400
    
    # 自动记录ESP32-CAM的IP地址
    # 优先从HTTP头中获取ESP32-CAM主动报告的IP地址
    esp32_ip_from_header = request.headers.get('X-ESP32-IP')
    new_ip = None
    if esp32_ip_from_header:
        new_ip = esp32_ip_from_header
    else:
        # 备选：从请求连接信息获取
        client_ip = request.remote_addr
        # 只有当没有其他IP来源时才使用远程地址，避免使用服务器自己的IP
        if client_ip and client_ip != '127.0.0.1':
            new_ip = client_ip

    # 仅在 IP 实际变化时才更新并持久化，避免预览帧高频上传导致每秒多次磁盘写入
    if new_ip and new_ip != esp32_cam_ip:
        esp32_cam_ip = new_ip
        esp32_cam_ip_time = time.time()
        print(f"ESP32-CAM IP地址已更新: {esp32_cam_ip}")
        persist_state()
    
    # 检查是否为高分辨率拍照帧
    resolution = request.headers.get('X-Resolution', 'preview')
    
    if resolution == 'high':
        # 只保存高分辨率拍照帧到 captures/ 目录（暂存，待用户保存到相册）
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        new_filename = f"esp32cam_{timestamp}_{uuid.uuid4().hex[:8]}.jpg"
        captures_dir = app.config['CAPTURES_FOLDER']
        filepath = os.path.join(captures_dir, new_filename)

        try:
            # 直接保存原始照片（不进行AI增强）
            with open(filepath, 'wb') as f:
                f.write(request.data)

            # 更新最近拍摄的照片
            last_captured_photo = {
                'filename': new_filename,
                'url': f'/captures/{new_filename}',
                'location': 'captures',
                'size': len(request.data),
                'timestamp': time.time(),
                'enhanced': False
            }

            # 拍照完成，重置状态
            is_capturing = False
            print(f"高分辨率照片保存成功: {new_filename}")

            return jsonify({
                'success': True,
                'filename': new_filename,
                'size': len(request.data),
                'url': f'/captures/{new_filename}',
                'location': 'captures',
                'captured': True,
                'enhanced': False
            })
        except Exception as e:
            print(f"保存文件失败: {str(e)}")
            return jsonify({'error': f'保存文件失败: {str(e)}'}), 500
    else:
        # 预览帧只更新内存，不保存到磁盘
        # 只有在非拍照状态下才更新预览帧
        if not is_capturing:
            # 验证数据完整性
            if len(request.data) > 0:
                # 在 Condition 锁内更新共享帧状态，保证并发安全与内存可见性
                with frame_condition:
                    latest_frame = request.data
                    latest_frame_time = time.time()
                    frame_id += 1
                    # 唤醒所有 MJPEG 流订阅者立即推送新帧（广播，不会互相吃帧）
                    frame_condition.notify_all()
            else:
                print('接收到空数据')
        
        return jsonify({
            'success': True,
            'message': '预览帧已更新',
            'size': len(request.data),
            'is_capturing': is_capturing
        })

@app.route('/api/frame', methods=['GET'])
def get_frame():
    global latest_frame, latest_frame_time
    
    try:
        if latest_frame:
            # 直接返回原始帧（不进行AI增强）
            return Response(latest_frame, mimetype='image/jpeg')
        else:
            # 返回默认图像
            default_image = os.path.join(app.static_folder, 'default.jpg') if hasattr(app, 'static_folder') else None
            if default_image and os.path.exists(default_image):
                with open(default_image, 'rb') as f:
                    return Response(f.read(), mimetype='image/jpeg')
            else:
                return jsonify({'error': '无画面数据'}), 404
    except Exception as e:
        print(f'获取帧失败: {str(e)}')
        # 返回默认图像作为备用
        default_image = os.path.join(app.static_folder, 'default.jpg') if hasattr(app, 'static_folder') else None
        if default_image and os.path.exists(default_image):
            with open(default_image, 'rb') as f:
                return Response(f.read(), mimetype='image/jpeg')
        else:
            return jsonify({'error': '获取帧失败'}), 500
    finally:
        pass

@app.route('/api/stream')
def video_stream():
    """MJPEG 实时流：单连接持续推送，新帧到达时由 frame_condition 唤醒立即发送。

    使用 Condition.notify_all() 广播：每个订阅者各自 wait，不会被其他客户端
    的 clear() 干扰，保证多客户端各自收到完整帧序列。
    """
    boundary = 'frame'

    def generate():
        last_id = -1
        while True:
            # 在 Condition 锁内等待并读取帧，保证与生产者的写入互斥一致
            with frame_condition:
                frame_condition.wait(timeout=1.0)
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

@app.route('/api/capture', methods=['POST'])
def capture():
    global esp32_cam_ip, esp32_cam_ip_time, is_capturing, last_capture_time
    
    try:
        data = request.get_json() or {}
        esp32_ip = data.get('esp32_ip')
        
        # 验证IP地址
        if not esp32_ip:
            # 检查是否有缓存的IP地址
            if esp32_cam_ip and (time.time() - esp32_cam_ip_time) < ESP32_IP_TIMEOUT:
                esp32_ip = esp32_cam_ip
                print(f"使用缓存的ESP32-CAM IP地址: {esp32_ip}")
            else:
                return jsonify({'error': '未指定ESP32-CAM IP地址'}), 400

        # 验证IP地址格式与网段（防止 SSRF，仅允许私有/回环/链路本地地址）
        validated_ip = validate_esp32_ip(esp32_ip)
        if not validated_ip:
            return jsonify({'error': '无效的IP地址或非局域网地址'}), 400
        esp32_ip = validated_ip

        # 发送拍照指令
        is_capturing = True
        last_capture_time = time.time()
        
        print(f"发送拍照指令到: {esp32_ip}")
        
        # 发送POST请求到ESP32-CAM的/capture端点
        response = requests.post(
            f"http://{esp32_ip}/capture",
            timeout=5
        )
        
        if response.status_code == 200:
            print("拍照指令发送成功")
            return jsonify({
                'success': True,
                'message': '拍照指令已发送，正在处理中...',
                'esp32_ip': esp32_ip
            })
        else:
            print(f"ESP32-CAM响应异常: {response.status_code}")
            is_capturing = False
            return jsonify({
                'success': False,
                'error': f'ESP32-CAM响应异常: {response.status_code}'
            }), 500
            
    except requests.exceptions.RequestException as e:
        print(f"发送拍照指令失败: {str(e)}")
        is_capturing = False
        return jsonify({
            'success': False,
            'error': f'无法连接ESP32-CAM: {str(e)}'
        }), 500
    except Exception as e:
        print(f"拍照失败: {str(e)}")
        is_capturing = False
        return jsonify({
            'success': False,
            'error': f'拍照失败: {str(e)}'
        }), 500

@app.route('/api/capture/status', methods=['GET'])
def capture_status():
    global is_capturing, last_capture_time, last_captured_photo
    
    # 检查是否超时
    if is_capturing and (time.time() - last_capture_time) > CAPTURE_TIMEOUT:
        is_capturing = False
        print("拍照超时")
    
    return jsonify({
        'is_capturing': is_capturing,
        'last_captured_photo': last_captured_photo
    })

@app.route('/api/capture/clear', methods=['POST'])
def clear_capture():
    """清除最近拍摄的照片记录"""
    global last_captured_photo
    last_captured_photo = None
    return jsonify({'success': True, 'message': '已清除拍摄记录'})

# 闪光灯控制
@app.route('/api/flash', methods=['GET', 'POST'])
def flash_control():
    """闪光灯控制"""
    global flash_enabled, esp32_cam_ip, esp32_cam_ip_time

    if request.method == 'GET':
        # 获取当前闪光灯状态
        return jsonify({
            'success': True,
            'flash_enabled': flash_enabled
        })
    
    elif request.method == 'POST':
        # 设置闪光灯状态
        data = request.get_json() or {}
        enable = data.get('enable', False)

        # 发送指令到ESP32-CAM
        try:
            # 解析 IP：优先用户传入 → 缓存 → 硬编码 fallback
            esp32_ip = data.get('esp32_ip') or esp32_cam_ip or '192.168.137.74'
            # SSRF 校验：fallback IP 也必须经过验证（仅允许私有/回环/链路本地）
            validated_ip = validate_esp32_ip(esp32_ip)
            if not validated_ip:
                return jsonify({'success': False, 'error': '无效的ESP32-CAM IP地址或非局域网地址'}), 400
            esp32_ip = validated_ip

            # 发送闪光灯控制指令
            response = requests.post(
                f"http://{esp32_ip}/flash",
                json={'enable': enable},
                timeout=5
            )

            if response.status_code == 200:
                flash_enabled = enable
                # 记录用户指定的相机 IP，便于后续控制与状态持久化
                if data.get('esp32_ip'):
                    esp32_cam_ip = data.get('esp32_ip')
                    esp32_cam_ip_time = time.time()
                print(f"闪光灯状态已更新: {'开启' if enable else '关闭'}")
                persist_state()
                return jsonify({
                    'success': True,
                    'flash_enabled': flash_enabled,
                    'message': f"闪光灯已{'开启' if enable else '关闭'}"
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'ESP32-CAM响应异常'
                }), 500

        except Exception as e:
            print(f"闪光灯控制失败: {str(e)}")
            # 即使通信失败，也更新本地状态
            flash_enabled = enable
            if data.get('esp32_ip'):
                esp32_cam_ip = data.get('esp32_ip')
                esp32_cam_ip_time = time.time()
            persist_state()
            return jsonify({
                'success': True,
                'flash_enabled': flash_enabled,
                'message': f"闪光灯状态已更新（本地）: {'开启' if enable else '关闭'}"
            })

# 相册功能
@app.route('/api/photos/save', methods=['POST'])
def save_photo():
    """保存照片到相册：将文件从 captures/ 或 uploads/ 移动到 album/。"""
    global saved_photos, last_captured_photo

    try:
        data = request.get_json() or {}
        filename = data.get('filename')

        if not filename and last_captured_photo:
            filename = last_captured_photo.get('filename')

        if not filename:
            return jsonify({'success': False, 'error': '没有指定照片'}), 400

        # 路径遍历防护：拒绝含分隔符或 .. 的文件名
        if not is_safe_filename(filename):
            return jsonify({'success': False, 'error': '无效的文件名'}), 400

        # 在 captures/ 与 uploads/ 中查找源文件（优先 captures，因为是相机拍照默认目录）
        captures_dir = app.config['CAPTURES_FOLDER']
        uploads_dir = app.config['UPLOAD_FOLDER']
        album_dir = app.config['ALBUM_FOLDER']
        src_path = None
        for d in (captures_dir, uploads_dir):
            candidate = os.path.join(d, filename)
            if os.path.exists(candidate):
                src_path = candidate
                break

        if src_path is None:
            return jsonify({'success': False, 'error': '照片文件不存在'}), 404

        # 移动到 album/；若已存在则覆盖（幂等保存）
        album_path = os.path.join(album_dir, filename)
        if os.path.abspath(src_path) != os.path.abspath(album_path):
            shutil.move(src_path, album_path)

        # 添加到已保存列表
        photo_info = {
            'filename': filename,
            'url': f'/album/{filename}',
            'location': 'album',
            'saved_at': time.time(),
            'selected': False
        }

        # 避免重复添加（使用 .get 避免 KeyError，兼容缺 filename 字段的旧数据）
        existing = [p for p in saved_photos if p.get('filename') == filename]
        if not existing:
            saved_photos.append(photo_info)
            print(f"照片已保存到相册: {filename}")
            persist_state()
        else:
            # 已存在则更新 url/location 字段（兼容旧数据），仅在字段实际变化时持久化
            idx = saved_photos.index(existing[0])
            old = saved_photos[idx]
            changed = False
            for k, v in photo_info.items():
                if old.get(k) != v:
                    old[k] = v
                    changed = True
            if changed:
                persist_state()

        return jsonify({
            'success': True,
            'message': '照片已保存到相册',
            'photo': photo_info
        })

    except Exception as e:
        print(f"保存照片失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

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

@app.route('/api/photos/select', methods=['POST'])
def select_photo():
    """选择/取消选择照片"""
    global saved_photos
    
    try:
        data = request.get_json() or {}
        filename = data.get('filename')
        selected = data.get('selected', True)
        
        if not filename:
            return jsonify({'success': False, 'error': '没有指定照片'}), 400
        
        # 更新照片选择状态（使用 .get 避免 KeyError，兼容缺 filename 字段的旧数据）
        for photo in saved_photos:
            if photo.get('filename') == filename:
                # 仅在选择状态实际变化时才写磁盘，避免重复点击产生无效 I/O
                if photo.get('selected') == selected:
                    return jsonify({
                        'success': True,
                        'message': f"照片已{'选择' if selected else '取消选择'}",
                        'photo': photo
                    })
                photo['selected'] = selected
                print(f"照片选择状态已更新: {filename} - {'已选择' if selected else '未选择'}")
                persist_state()
                return jsonify({
                    'success': True,
                    'message': f"照片已{'选择' if selected else '取消选择'}",
                    'photo': photo
                })

        return jsonify({'success': False, 'error': '照片未找到'}), 404
        
    except Exception as e:
        print(f"选择照片失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/photos/delete', methods=['POST'])
def delete_photo():
    """删除照片"""
    global saved_photos, _album_files_cache, _album_files_cache_mtime

    try:
        data = request.get_json() or {}
        filename = data.get('filename')

        if not filename:
            return jsonify({'success': False, 'error': '没有指定照片'}), 400

        # 路径遍历防护：拒绝含分隔符或 .. 的文件名
        if not is_safe_filename(filename):
            return jsonify({'success': False, 'error': '无效的文件名'}), 400

        # 从列表中移除（使用 .get 避免 KeyError，兼容缺 filename 字段的旧数据）
        saved_photos = [p for p in saved_photos if p.get('filename') != filename]

        # 删除文件（在 album/ 目录）
        filepath = os.path.join(app.config['ALBUM_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            print(f"照片已删除: {filename}")
        # 失效相册文件缓存，确保下次 /api/photos 反映最新状态
        _album_files_cache = None
        persist_state()

        return jsonify({
            'success': True,
            'message': '照片已删除'
        })

    except Exception as e:
        print(f"删除照片失败: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# 静态文件服务
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/captures/<filename>')
def captured_file(filename):
    return send_from_directory(app.config['CAPTURES_FOLDER'], filename)

@app.route('/album/<filename>')
def album_file(filename):
    return send_from_directory(app.config['ALBUM_FOLDER'], filename)

if __name__ == '__main__':
    print("启动Flask服务器...")
    print(f"服务器将运行在 http://0.0.0.0:5000")
    print(f"访问地址: http://localhost:5000")
    # threaded=True 允许多请求并发，避免单请求阻塞其他客户端
    app.run(host='0.0.0.0', port=5000, debug=False, threaded=True)
