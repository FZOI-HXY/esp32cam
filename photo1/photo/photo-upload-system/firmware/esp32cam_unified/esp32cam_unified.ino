// ============================================================
//  ESP32-CAM 统一固件
//  整合预览流、高分辨率拍照、闪光灯控制、FreeRTOS 双核任务。
//  所有可配置项见 config.h，按 #define 开关启用功能。
// ============================================================

#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClient.h>
#include <Arduino.h>
#include "soc/soc.h"
#include "soc/rtc_cntl_reg.h"
#include "driver/rtc_io.h"

#include "config.h"

#if ENABLE_FREERTOS
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
static TaskHandle_t s_taskNetwork = NULL;   // Core0: 网络/上传
static TaskHandle_t s_taskCamera  = NULL;   // Core1: 摄像头/拍照
#endif

// 共享状态
static volatile bool g_isCapturing  = false;  // 拍照进行中（暂停预览）
static volatile bool g_needCapture  = false;  // 收到拍照请求
static volatile bool g_flashEnabled = false;  // 闪光灯状态

// ---------- 摄像头初始化 ----------
static bool initCamera(framesize_t framesize, int jpeg_quality, int fb_count) {
  camera_config_t cfg;
  cfg.ledc_channel  = LEDC_CHANNEL_0;
  cfg.ledc_timer    = LEDC_TIMER_0;
  cfg.pin_pwdn      = PWDN_GPIO_NUM;
  cfg.pin_reset     = RESET_GPIO_NUM;
  cfg.pin_xclk      = XCLK_GPIO_NUM;
  cfg.pin_sscb_sda  = SIOD_GPIO_NUM;
  cfg.pin_sscb_scl  = SIOC_GPIO_NUM;
  cfg.pin_d7        = Y9_GPIO_NUM;
  cfg.pin_d6        = Y8_GPIO_NUM;
  cfg.pin_d5        = Y7_GPIO_NUM;
  cfg.pin_d4        = Y6_GPIO_NUM;
  cfg.pin_d3        = Y5_GPIO_NUM;
  cfg.pin_d2        = Y4_GPIO_NUM;
  cfg.pin_d1        = Y3_GPIO_NUM;
  cfg.pin_d0        = Y2_GPIO_NUM;
  cfg.pin_vsync     = VSYNC_GPIO_NUM;
  cfg.pin_href      = HREF_GPIO_NUM;
  cfg.pin_pclk      = PCLK_GPIO_NUM;
  cfg.xclk_freq_hz  = 20000000;
  cfg.pixel_format  = PIXFORMAT_JPEG;
  cfg.frame_size    = framesize;
  cfg.jpeg_quality  = jpeg_quality;
  cfg.fb_count      = fb_count;

  esp_err_t err = esp_camera_init(&cfg);
  if (err != ESP_OK) {
    Serial.printf("[CAM] 初始化失败: 0x%x\n", err);
    return false;
  }
  Serial.println("[CAM] 初始化成功");
  return true;
}

// ---------- WiFi ----------
static bool connectWiFi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
    if (millis() - start > 20000) {
      Serial.println("\n[WIFI] 连接超时");
      return false;
    }
  }
  Serial.printf("\n[WIFI] 已连接，IP: %s\n", WiFi.localIP().toString().c_str());
  return true;
}

// ---------- HTTP 上传 ----------
static int postRaw(const uint8_t* data, size_t len, const char* resolution) {
  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/raw";
  if (!http.begin(client, url)) return -1;

  http.addHeader("Content-Type", "image/jpeg");
  http.addHeader("X-Resolution", resolution);
  // 主动报告本机 IP，便于服务器回连控制
  http.addHeader("X-ESP32-IP", WiFi.localIP().toString().c_str());
  http.setTimeout(HTTP_TIMEOUT_MS);

  // HTTPClient::POST 签名要求 uint8_t*（非 const），但内部不会修改 payload。
  // 使用 const_cast 安全去除 const 语义，避免数据复制。
  int code = http.POST(const_cast<uint8_t*>(data), len);
  http.end();
  return code;
}

#if ENABLE_FLASH
// ---------- 闪光灯 ----------
static void setFlash(bool on) {
  pinMode(FLASH_GPIO_NUM, OUTPUT);
  digitalWrite(FLASH_GPIO_NUM, on ? HIGH : LOW);
}

// 轮询服务器闪光灯状态
static void pollFlashState() {
  WiFiClient client;
  HTTPClient http;
  String url = String("http://") + SERVER_IP + ":" + String(SERVER_PORT) + "/api/flash";
  if (!http.begin(client, url)) return;
  http.setTimeout(HTTP_TIMEOUT_MS);
  int code = http.GET();
  if (code == 200) {
    String body = http.getString();
    // 简单 JSON 解析：查找 "flash_enabled": true|false
    bool enabled = body.indexOf("\"flash_enabled\":true") >= 0;
    if (enabled != g_flashEnabled) {
      g_flashEnabled = enabled;
      setFlash(enabled);
      Serial.printf("[FLASH] 状态更新: %s\n", enabled ? "开" : "关");
    }
  }
  http.end();
}
#endif  // ENABLE_FLASH

#if ENABLE_CAPTURE
// ---------- 拍照触发与执行 ----------
static void triggerCapture() {
  g_needCapture = true;
}

static void performCapture() {
  Serial.println("[CAP] 开始高分辨率拍照");
  g_isCapturing = true;

  // 重新配置为高分辨率（若与预览不同）
  // 注：esp_camera 已初始化，这里通过 sensor 设置分辨率以避免重新 init
  sensor_t* s = esp_camera_sensor_get();
  framesize_t oldSize = s->status.framesize;
  s->set_framesize(s, CAPTURE_FRAMESIZE);

  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAP] 拍照失败");
  } else {
    Serial.printf("[CAP] 拍照成功: %zu 字节\n", fb->len);
    int code = postRaw(fb->buf, fb->len, "high");
    Serial.printf("[CAP] 上传响应码: %d\n", code);
    esp_camera_fb_return(fb);
  }

  // 恢复预览分辨率
  s->set_framesize(s, oldSize);
  g_isCapturing = false;
}
#endif  // ENABLE_CAPTURE

#if ENABLE_PREVIEW
// ---------- 预览流 ----------
static void pushPreviewFrame() {
  if (g_isCapturing) return;  // 拍照期间暂停预览
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) return;
  int code = postRaw(fb->buf, fb->len, "preview");
  if (code <= 0) {
    Serial.printf("[PREVIEW] 上传失败: %d\n", code);
  }
  esp_camera_fb_return(fb);
}
#endif  // ENABLE_PREVIEW

#if ENABLE_FREERTOS
// ---------- 双核任务 ----------
static void cameraTask(void* arg) {
  (void)arg;
  uint32_t lastFlash = 0;
  uint32_t lastCapture = 0;
  for (;;) {
#if ENABLE_CAPTURE
    if (g_needCapture && !g_isCapturing) {
      performCapture();
      g_needCapture = false;
      lastCapture = millis();
    }
#endif
#if ENABLE_PREVIEW
    if (!g_isCapturing) {
      pushPreviewFrame();
    }
#endif
    // 闪光灯轮询（独立频率）
#if ENABLE_FLASH
    if (millis() - lastFlash > FLASH_POLL_INTERVAL_MS) {
      pollFlashState();
      lastFlash = millis();
    }
#endif
    vTaskDelay(pdMS_TO_TICKS(PREVIEW_INTERVAL_MS));
  }
}

// 网络监听任务（接收拍照指令等控制信号，预留扩展）
static void networkTask(void* arg) {
  (void)arg;
  for (;;) {
    // TODO: 此处可监听服务器推送的拍照指令
    // 目前仅作为占位，拍照由 g_needCapture 触发
    vTaskDelay(pdMS_TO_TICKS(CAPTURE_POLL_INTERVAL_MS));
  }
}
#else
// 单 loop 兼容模式
static void runSingleLoop() {
#if ENABLE_CAPTURE
  if (g_needCapture && !g_isCapturing) {
    performCapture();
    g_needCapture = false;
  }
#endif
#if ENABLE_PREVIEW
  if (!g_isCapturing) {
    pushPreviewFrame();
  }
#endif
#if ENABLE_FLASH
  static uint32_t lastFlash = 0;
  if (millis() - lastFlash > FLASH_POLL_INTERVAL_MS) {
    pollFlashState();
    lastFlash = millis();
  }
#endif
  delay(PREVIEW_INTERVAL_MS);
}
#endif  // ENABLE_FREERTOS

// ============================================================
//  Arduino 入口
// ============================================================
void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.println("\n[BOOT] ESP32-CAM 统一固件启动");

  // 关闭 Brownout 检测，避免电压波动复位
  WRITE_PERI_REG(RTC_CNTL_BROWN_OUT_REG, 0);

  // 初始化摄像头（默认预览分辨率；拍照时动态切换）
  if (!initCamera(PREVIEW_FRAMESIZE, PREVIEW_JPEG_QUALITY, CAPTURE_FB_COUNT)) {
    Serial.println("[BOOT] 摄像头初始化失败，停止");
    return;
  }

  // 连接 WiFi
  if (!connectWiFi()) {
    Serial.println("[BOOT] WiFi 连接失败，5 秒后重启");
    delay(5000);
    ESP.restart();
  }

#if ENABLE_FLASH
  setFlash(false);
#endif

#if ENABLE_FREERTOS
  xTaskCreatePinnedToCore(cameraTask,  "cam",  8192, NULL, 1, &s_taskCamera,  1);
  xTaskCreatePinnedToCore(networkTask, "net",  4096, NULL, 1, &s_taskNetwork, 0);
  Serial.println("[BOOT] FreeRTOS 任务已启动 (Core0=net, Core1=cam)");
#endif
}

void loop() {
#if ENABLE_FREERTOS
  // 双核模式下 loop 空转，所有工作在任务中完成
  vTaskDelay(pdMS_TO_TICKS(1000));
#else
  runSingleLoop();
#endif
}
