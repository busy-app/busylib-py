#!/usr/bin/env python3
"""
ping_display_bar_logo.py — отображает график пинга (в виде цветных столбиков)
и логотип CS:GO на LED-дисплее 72x16.

Цвета пинга:
  0–20 мс   — зелёный
  21–50 мс  — жёлтый
  >50 мс    — красный
Шкала — до 100 мс.
"""
import sys, time, argparse, collections, io, platform, re, subprocess, os
from PIL import Image, ImageDraw
import requests

# === Конфигурация ===
DEVICE_IP = "10.0.4.20"
APP_ID = "ping_app"
GRAPH_FILE = "graph.png"
LOGO_FILE = "csgo.png"         # логотип, который должен быть в папке рядом со скриптом
LOGO_REMOTE_PATH = "csgo.png"  # имя файла на устройстве
DISPLAY_WIDTH = 72
DISPLAY_HEIGHT = 16
TEXT_FONT = "small"
TEXT_COLOR = "#FFFFFFFF"

# Область графика (учитываем место для логотипа)
LOGO_WIDTH = 16
GRAPH_X = LOGO_WIDTH + 1       # график начинается после логотипа
GRAPH_Y = 5
GRAPH_HEIGHT = DISPLAY_HEIGHT - GRAPH_Y
GRAPH_WIDTH = DISPLAY_WIDTH - GRAPH_X
BUFFER_LEN = GRAPH_WIDTH
UPDATE_INTERVAL = 1.0
MAX_PING_MS = 100.0

def ping_once(host, timeout_s=1.0):
    system = platform.system().lower()
    try:
        if system == "windows":
            proc = subprocess.run(["ping", "-n", "1", "-w", str(int(timeout_s*1000)), host],
                                   capture_output=True, text=True, timeout=timeout_s+1)
            m = re.search(r"time[=<]\s*([0-9]+)ms", proc.stdout)
            if m: return int(m.group(1))
        else:
            proc = subprocess.run(["ping", "-c", "1", host],
                                   capture_output=True, text=True, timeout=timeout_s+1)
            m = re.search(r"time[=<]?\s*([0-9]+(?:\.[0-9]+)?)\s*ms", proc.stdout)
            if m: return int(round(float(m.group(1))))
    except Exception:
        return None
    return None

def render_graph_image(values, width=GRAPH_WIDTH, height=GRAPH_HEIGHT, max_ping=MAX_PING_MS):
    """Рисует столбиковый график пинга с цветами по диапазону."""
    img = Image.new("RGBA", (width, height), (0,0,0,255))
    draw = ImageDraw.Draw(img)
    for x, v in enumerate(values):
        if v is None: continue
        v = max(0.0, min(v, max_ping))
        h = int(round((v / max_ping) * (height - 1)))
        y0 = height - h
        if v <= 20:
            color = (0, 255, 0, 255)      # зелёный
        elif v <= 50:
            color = (255, 255, 0, 255)    # жёлтый
        else:
            color = (255, 0, 0, 255)      # красный
        draw.line((x, y0, x, height - 1), fill=color)
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()

def upload_image_to_device(device_ip, app_id, filename, img_bytes):
    url = f"http://{device_ip}/api/assets/upload"
    params = {"app_id": app_id, "file": filename}
    try:
        r = requests.post(url, params=params, data=img_bytes,
                          headers={"Content-Type": "application/octet-stream"}, timeout=5)
        r.raise_for_status()
        return True
    except Exception as e:
        print("Ошибка загрузки изображения:", e)
        return False

def display_on_device(device_ip, payload):
    url = f"http://{device_ip}/api/display/draw"
    try:
        r = requests.post(url, json=payload, timeout=5)
        r.raise_for_status()
        return True
    except Exception as e:
        print("Ошибка display/draw:", e)
        return False

def upload_logo(device_ip, app_id, logo_path, remote_name):
    if not os.path.exists(logo_path):
        print(f"⚠️ Логотип {logo_path} не найден. Пропускаем загрузку.")
        return False
    with open(logo_path, "rb") as f:
        img_bytes = f.read()
    print(f"Загружаем логотип {logo_path} на устройство...")
    return upload_image_to_device(device_ip, app_id, remote_name, img_bytes)

def run_loop(server_ip, device_ip=DEVICE_IP):
    buffer = collections.deque([None]*BUFFER_LEN, maxlen=BUFFER_LEN)
    upload_logo(device_ip, APP_ID, LOGO_FILE, LOGO_REMOTE_PATH)
    print(f"Пингуем {server_ip} каждую {UPDATE_INTERVAL:.1f}s, обновляем дисплей {device_ip}")

    try:
        while True:
            t0 = time.time()
            ping_ms = ping_once(server_ip, timeout_s=0.9)
            text_value = "--" if ping_ms is None else f"{ping_ms} ms"
            buffer.append(ping_ms)

            img_bytes = render_graph_image(buffer)
            upload_image_to_device(device_ip, APP_ID, GRAPH_FILE, img_bytes)

            payload = {
                "app_id": APP_ID,
                "elements": [
                    {
                        "id": "ping_text",
                        "timeout": 2,
                        "type": "text",
                        "text": text_value,
                        "x": GRAPH_X,
                        "y": 0,
                        "font": TEXT_FONT,
                        "color": TEXT_COLOR,
                        "width": 56,
                        "scroll_rate": 60
                    },
                    {
                        "id": "logo_img",
                        "timeout": 2,
                        "type": "image",
                        "path": LOGO_REMOTE_PATH,
                        "x": 0,
                        "y": 0
                    },
                    {
                        "id": "graph_img",
                        "timeout": 2,
                        "type": "image",
                        "path": GRAPH_FILE,
                        "x": GRAPH_X,
                        "y": GRAPH_Y
                    }
                ]
            }
            display_on_device(device_ip, payload)
            print(f"{time.strftime('%H:%M:%S')} | ping={text_value}")
            t_elapsed = time.time() - t0
            if (to_sleep := UPDATE_INTERVAL - t_elapsed) > 0:
                time.sleep(to_sleep)
    except KeyboardInterrupt:
        print("\nОстановлено пользователем.")


def main():
    parser = argparse.ArgumentParser(description="Ping -> LED display 72x16 bar graph + CS:GO logo")
    parser.add_argument("--server", "-s", required=True, help="IP/hostname игрового сервера")
    parser.add_argument("--device", "-d", default=DEVICE_IP, help=f"IP LED-девайса (по умолчанию {DEVICE_IP})")
    args = parser.parse_args()
    run_loop(args.server, args.device)


if __name__ == "__main__":
    main()
