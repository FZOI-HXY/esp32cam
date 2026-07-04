#ifndef ESP32CAM_CONFIG_H
#define ESP32CAM_CONFIG_H

// ============================================================
//  ESP32-CAM 统一固件配置
//  通过下方 #define 开关选择启用功能，按需编译。
//  所有可调参数集中于此，主 .ino 文件无需修改。
// ============================================================

// ---------- 功能开关 ----------
// 预览流（连续上传低分辨率帧到 /api/raw，resolution=preview）
#ifndef ENABLE_PREVIEW
#define ENABLE_PREVIEW 1
#endif

// 高分辨率拍照（按需触发，上传到 /api/raw，resolution=high）
#ifndef ENABLE_CAPTURE
#define ENABLE_CAPTURE 1
#endif

// 闪光灯控制（GPIO4，监听 /flash 端点）
#ifndef ENABLE_FLASH
#define ENABLE_FLASH 1
#endif

// FreeRTOS 双核任务（Core0 网络、Core1 摄像头）
// 关闭时退化为单 loop 轮询
#ifndef ENABLE_FREERTOS
#define ENABLE_FREERTOS 1
#endif

// ---------- WiFi 配置 ----------
#ifndef WIFI_SSID
#define WIFI_SSID "your-wifi-ssid"
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "your-wifi-password"
#endif

// ---------- 服务器配置 ----------
#ifndef SERVER_IP
#define SERVER_IP "192.168.137.1"
#endif

#ifndef SERVER_PORT
#define SERVER_PORT 5000
#endif

// ---------- 摄像头引脚（AI-Thinker ESP32-CAM） ----------
#define PWDN_GPIO_NUM     32
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM      0
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       21
#define Y4_GPIO_NUM       19
#define Y3_GPIO_NUM       18
#define Y2_GPIO_NUM        5
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// 闪光灯引脚
#define FLASH_GPIO_NUM    4

// ---------- 摄像头参数 ----------
// 预览流分辨率（低分辨率、高帧率）
#ifndef PREVIEW_FRAMESIZE
#define PREVIEW_FRAMESIZE FRAMESIZE_QVGA   // 320x240
#endif

#ifndef PREVIEW_JPEG_QUALITY
#define PREVIEW_JPEG_QUALITY 12
#endif

// 拍照分辨率（高分辨率）
#ifndef CAPTURE_FRAMESIZE
#define CAPTURE_FRAMESIZE FRAMESIZE_UXGA   // 1600x1200
#endif

#ifndef CAPTURE_JPEG_QUALITY
#define CAPTURE_JPEG_QUALITY 10
#endif

#ifndef CAPTURE_FB_COUNT
#define CAPTURE_FB_COUNT 2
#endif

// ---------- 行为参数 ----------
// 预览上传间隔（毫秒）
#ifndef PREVIEW_INTERVAL_MS
#define PREVIEW_INTERVAL_MS 100
#endif

// 拍照触发检查间隔（毫秒）
#ifndef CAPTURE_POLL_INTERVAL_MS
#define CAPTURE_POLL_INTERVAL_MS 500
#endif

// 闪光灯轮询间隔（毫秒）
#ifndef FLASH_POLL_INTERVAL_MS
#define FLASH_POLL_INTERVAL_MS 1000
#endif

// HTTP 超时（毫秒）
#ifndef HTTP_TIMEOUT_MS
#define HTTP_TIMEOUT_MS 3000
#endif

// 串口波特率
#ifndef SERIAL_BAUD
#define SERIAL_BAUD 115200
#endif

#endif  // ESP32CAM_CONFIG_H
