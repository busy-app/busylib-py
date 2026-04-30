import argparse
import asyncio
import ipaddress
import logging
import os
import queue
import random
import select
import sys
import termios
import threading
import time
import tty
import wave
from collections.abc import Coroutine
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List

from busylib import display, types
from busylib.client import AsyncBusyBar
from busylib.features import sync_app_assets

WIDTH = display.FRONT_DISPLAY.width  # 72
HEIGHT = display.FRONT_DISPLAY.height  # 16
CAR_W = 2
CAR_H = 1
APP_ID = "busylib-demo"
OB_W = 3
OB_H = 1
OBSTACLE_CHAR = "O"
BACKGROUND_CHAR = " "
CAR_CHAR = "X"
CAR_COLOR = "#FF0000"
HUD_COLOR = "#00E5FF"
TRACK_COLOR = "#FFFFFF"
OBSTACLE_COLORS = ["#FFA500", "#00FF7F", "#1E90FF", "#FF69B4", "#FFD700"]
OBSTACLE_SPRITES = [
    "racer-blue",
    "racer-cyan",
    "racer-yellow",
    "racer-black",
    "racer-green",
    "racer-white",
]
CAR_SPRITE = "racer-red"
SCORES_FILE = "speed_racer_scores.txt"
ASSET_DIR = Path(__file__).resolve().parent / "assets"


class AsyncRunner:
    """
    Run coroutines in a background thread event loop.
    """

    def __init__(self) -> None:
        """
        Initialize the event loop and thread.
        """
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._started = threading.Event()
        self._stopped = threading.Event()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._started.set()
        self._loop.run_forever()
        self._stopped.set()

    def start(self) -> None:
        """
        Start the background event loop.
        """
        if self._thread.is_alive():
            return
        self._thread.start()
        self._started.wait()

    def stop(self) -> None:
        """
        Stop the background event loop.
        """
        if not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._stopped.wait(timeout=1)

    def run(
        self,
        coro: asyncio.Future[object] | Coroutine[object, object, object],
    ) -> object:
        """
        Run a coroutine in the background loop and return its result.
        """
        if not self._thread.is_alive():
            raise RuntimeError("AsyncRunner not started")
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result()


def _build_client(
    addr: str,
    token_arg: str | None,
    *,
    lan_token_env: str,
    cloud_token_env: str,
) -> AsyncBusyBar:
    """
    Build AsyncBusyBar with LAN/cloud token selection and optional headers.
    """
    base_addr = addr if addr.startswith(("http://", "https://")) else f"http://{addr}"
    parsed_host = base_addr.split("://", 1)[-1].split("/", 1)[0]
    token = token_arg
    extra_headers: dict[str, str] = {}

    if token is None:
        if is_private_host(parsed_host):
            lan_token = os.getenv(lan_token_env)
            if lan_token:
                extra_headers["x-api-token"] = lan_token
        else:
            cloud_token = os.getenv(cloud_token_env)
            if cloud_token:
                token = cloud_token

    client = AsyncBusyBar(addr=base_addr, token=token)
    if extra_headers:
        client.client.headers.update(extra_headers)
    return client


def _configure_logging(*, level: str, log_file: str | None) -> None:
    """
    Configure root logging to write only to a specified file.
    When no file is provided, attach a null handler to suppress output.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger_root = logging.getLogger()
    logger_root.handlers.clear()
    logger_root.setLevel(numeric_level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    if log_file:
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=1_000_000,
            backupCount=1,
            encoding="utf-8",
        )
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(fmt)
        logger_root.addHandler(file_handler)
    else:
        logger_root.addHandler(logging.NullHandler())


@dataclass
class Car:
    x: int = 2
    y: int = HEIGHT // 2 - 1  # top-left corner


@dataclass
class Obstacle:
    x: float
    y: int
    w: int
    h: int
    color: str = TRACK_COLOR
    passed: bool = False
    sprite: str = "racer_blue"

    def rect(self) -> tuple[float, float, float, float]:
        return self.x, self.y, self.x + self.w, self.y + self.h


def is_private_host(host: str) -> bool:
    """
    Decide if the host is on a local/private network.
    """
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return host.endswith(".local") or host.startswith("localhost")


class RawInput:
    def __enter__(self) -> None:
        self.fd = sys.stdin.fileno()
        self.old_settings = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        return None

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


def key_pressed() -> str | None:
    import select

    dr, _, _ = select.select([sys.stdin], [], [], 0)
    if dr:
        ch = sys.stdin.read(1)
        return ch
    return None


def rects_intersect(
    a: tuple[float, float, float, float], b: tuple[float, float, float, float]
) -> bool:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    return not (ax2 <= bx1 or ax1 >= bx2 or ay2 <= by1 or ay1 >= by2)


def make_obstacle(level: int) -> Obstacle:
    # Uniform rival cars.
    w = OB_W
    h = OB_H
    lane_positions = [1, HEIGHT // 2 - h // 2, HEIGHT - h - 1]
    y = random.choice(lane_positions)
    color = random.choice(OBSTACLE_COLORS)
    sprite = random.choice(OBSTACLE_SPRITES)
    return Obstacle(x=float(WIDTH - 1), y=y, w=w, h=h, color=color, sprite=sprite)


def load_scores(path: Path) -> List[tuple[str, int]]:
    if not path.is_file():
        return []
    scores: List[tuple[str, int]] = []
    for line in path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) >= 2:
            name = parts[0][:3]
            try:
                val = int(parts[-1])
            except ValueError:
                continue
            scores.append((name, val))
    return scores


def save_scores(path: Path, scores: List[tuple[str, int]]) -> None:
    path.write_text("\n".join(f"{name} {val}" for name, val in scores))


def prompt_name_on_screen(
    runner: AsyncRunner,
    client: AsyncBusyBar,
    score: int,
    scores_path: Path,
) -> None:
    """
    Prompt for 3-letter name using terminal keyboard, showing state on device.
    """
    name_chars: List[str] = ["_", "_", "_"]

    def render() -> None:
        name_str = "".join(name_chars)
        runner.run(client.clear_display())
        elements: List[types.DisplayElement] = [
            types.TextElement(
                id="prompt-name",
                type="text",
                x=WIDTH // 2,
                y=HEIGHT // 2,
                text=name_str,
                color="#FFFFFF",
                display=types.DisplayName.FRONT,
                font="medium",
                align="center",
            ),
        ]
        runner.run(
            client.draw_on_display(
                types.DisplayElements(app_id=APP_ID, elements=elements)
            )
        )

    input_q: queue.Queue[str] = queue.Queue()
    stop_event = threading.Event()

    def reader() -> None:
        while not stop_event.is_set():
            r, _, _ = select.select([sys.stdin], [], [], 0.1)
            if not r:
                continue
            ch = sys.stdin.read(1)
            input_q.put(ch)

    with RawInput():
        t = threading.Thread(target=reader, daemon=True)
        t.start()
        try:
            while True:
                render()
                try:
                    ch = input_q.get(timeout=0.05)
                except queue.Empty:
                    continue
                if ch in ("\n", "\r"):
                    if all(c != "_" for c in name_chars):
                        break
                    continue
                if ch in ("\x7f", "\b") and any(c != "_" for c in name_chars):
                    for i in range(2, -1, -1):
                        if name_chars[i] != "_":
                            name_chars[i] = "_"
                            break
                    continue
                if not ch:
                    continue
                if ch.isalpha():
                    ch = ch.upper()
                    for i in range(3):
                        if name_chars[i] == "_":
                            name_chars[i] = ch
                            break
        finally:
            stop_event.set()
            t.join(timeout=0.2)
    name = "".join(name_chars)
    scores = load_scores(scores_path)
    scores.append((name, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    scores = scores[:6]
    save_scores(scores_path, scores)


def build_obstacle_elements(obstacles: List[Obstacle]) -> List[types.ImageElement]:
    elements: List[types.ImageElement] = []
    for idx, obs in enumerate(obstacles):
        elements.append(
            types.ImageElement(
                id=f"obs-{idx}",
                type="image",
                x=int(obs.x),
                y=obs.y,
                path=f"{obs.sprite}.png",
                display=types.DisplayName.FRONT,
            )
        )
    return elements


def car_elements(car: Car) -> List[types.TextElement]:
    return [
        types.ImageElement(
            id="car-img",
            type="image",
            x=car.x,
            y=car.y,
            path=f"{CAR_SPRITE}.png",
            display=types.DisplayName.FRONT,
        )
    ]


def hud_elements(score: int, level: int, speed: float) -> List[types.TextElement]:
    return [
        types.TextElement(
            id="hud-score",
            type="text",
            align="top_right",
            x=WIDTH,
            y=0,
            text=f"{score:06d}",
            color=HUD_COLOR,
            display=types.DisplayName.FRONT,
            font="small",
        )
    ]


def wasted_element() -> List[types.TextElement]:
    return [
        types.TextElement(
            id="wasted",
            type="text",
            align="center",
            x=WIDTH // 2,
            y=HEIGHT // 2,
            text="WASTED",
            color="#FF0077FF",
            display=types.DisplayName.FRONT,
            font="big",
        )
    ]


def main() -> None:
    try:
        parser = argparse.ArgumentParser(
            description="Speed Racer mini-game for the front display."
        )
        parser.add_argument(
            "--addr", default="http://10.0.4.20", help="Device address."
        )
        parser.add_argument(
            "--token", default=None, help="Bearer token for Authorization header."
        )
        parser.add_argument(
            "--lan-token-env",
            default="BUSY_LAN_TOKEN",
            help="Env var for LAN token (x-api-token).",
        )
        parser.add_argument(
            "--cloud-token-env",
            default="BUSY_CLOUD_TOKEN",
            help="Env var for cloud bearer token.",
        )
        parser.add_argument("--log-level", default="INFO", help="Logging level.")
        parser.add_argument("--log-file", default=None, help="Log file path.")
        parser.add_argument(
            "--quiet",
            action="store_true",
            default=True,
            help="Disable console logs (default: quiet).",
        )
        parser.add_argument(
            "--assets-dir",
            default=str(ASSET_DIR),
            help="Local assets dir to read baraban.wav duration from.",
        )
        parser.add_argument(
            "--scores-file", default=SCORES_FILE, help="Path to scores file."
        )
        args = parser.parse_args()

        _configure_logging(level=args.log_level, log_file=args.log_file)
        logger = logging.getLogger("speed_racer")

        runner = AsyncRunner()
        runner.start()
        client = _build_client(
            args.addr,
            args.token,
            lan_token_env=args.lan_token_env,
            cloud_token_env=args.cloud_token_env,
        )
        runner.run(sync_app_assets(client, APP_ID, args.assets_dir))

        car = Car()
        obstacles: List[Obstacle] = []
        score = 0
        passed = 0
        level = 1
        base_speed = 18.0  # pixels/sec
        speed = base_speed
        spawn_cooldown = 0.8
        last_spawn = 0.0

        last_time = time.monotonic()
        last_audio = last_time
        drum_duration = 2.0  # default
        wav_path = Path(args.assets_dir) / "baraban.wav"
        if wav_path.is_file():
            try:
                with wave.open(str(wav_path), "rb") as wf:
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    drum_duration = max(0.1, frames / float(rate))
                    logger.info("baraban.wav duration detected: %.2fs", drum_duration)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to read baraban.wav duration: %s", exc)

        final_score: int | None = None

        running = True

        with RawInput():
            try:
                while running:
                    now = time.monotonic()
                    dt = now - last_time
                    last_time = now

                    if now - last_audio >= drum_duration:
                        try:
                            runner.run(client.play_audio(APP_ID, "baraban.wav"))
                        except Exception:
                            pass
                        last_audio = now

                    # Input
                    key = key_pressed()
                    if key in ("q", "\x03"):
                        break
                    if key == "\x1b":  # arrow keys start with ESC
                        seq = sys.stdin.read(2) if sys.stdin.readable() else ""
                        if seq and seq[0] == "[":
                            if seq[1] == "A" and car.y > 0:
                                car.y = max(0, car.y - 1)
                            elif seq[1] == "B" and car.y < HEIGHT - CAR_H:
                                car.y = min(HEIGHT - CAR_H, car.y + 1)
                            elif seq[1] == "C" and car.x < WIDTH - CAR_W:
                                car.x = min(WIDTH - CAR_W, car.x + 1)
                            elif seq[1] == "D" and car.x > 0:
                                car.x = max(0, car.x - 1)
                    elif key == "w":
                        car.y = max(0, car.y - 1)
                    elif key == "s":
                        car.y = min(HEIGHT - CAR_H, car.y + 1)
                    elif key == "d":
                        car.x = min(WIDTH - CAR_W, car.x + 1)
                    elif key == "a":
                        car.x = max(0, car.x - 1)

                    # Spawn obstacles
                    last_spawn += dt
                    if last_spawn >= spawn_cooldown:
                        obstacles.append(make_obstacle(level))
                        last_spawn = 0.0

                    # Update obstacles
                    for obs in obstacles:
                        obs.x -= speed * dt

                    # Collision + cleanup
                    car_rect = (car.x, car.y, car.x + CAR_W, car.y + CAR_H)
                    alive_obstacles: List[Obstacle] = []
                    for obs in obstacles:
                        if obs.x + obs.w < 0:
                            continue
                        # Award pass once when rival fully behind player.
                        if not obs.passed and (obs.x + obs.w) <= car.x:
                            obs.passed = True
                            passed += 1
                            progress = car.x / max(1, WIDTH - CAR_W)
                            bonus_mult = 1.0 + progress * 2.0
                            score += int(10 * bonus_mult)
                        # Skip collision if already passed.
                        if not obs.passed and rects_intersect(car_rect, obs.rect()):
                            elements = car_elements(car) + wasted_element()
                            payload = types.DisplayElements(
                                app_id=APP_ID,
                                elements=elements,
                            )
                            runner.run(client.draw_on_display(payload))
                            try:
                                runner.run(client.play_audio(APP_ID, "demo.wav"))
                            except Exception:
                                pass
                            print("Collision! Final score:", score)
                            time.sleep(5)
                            final_score = score
                            running = False
                            break
                        alive_obstacles.append(obs)
                    obstacles = alive_obstacles

                    if not running:
                        break

                    # Level progression
                    level = 1 + passed // 5
                    speed = base_speed + (level - 1) * 3
                    spawn_cooldown = max(0.4, 0.8 - (level - 1) * 0.05)

                    # Render frame
                    track_elements = build_obstacle_elements(obstacles)
                    elements: List[types.DisplayElement] = [
                        *track_elements,
                        *car_elements(car),
                        *hud_elements(score, level, speed),
                    ]
                    payload = types.DisplayElements(app_id=APP_ID, elements=elements)
                    logger.debug("Sending %s elements", len(elements))
                    runner.run(client.draw_on_display(payload))

                    time.sleep(0.05)
            finally:
                # Clear display when exiting.
                runner.run(client.clear_display())
                if final_score is not None:
                    scores_path = Path(args.scores_file)
                    prompt_name_on_screen(runner, client, final_score, scores_path)
                runner.run(client.aclose())
                runner.stop()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
