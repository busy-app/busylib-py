import argparse
import asyncio
import curses
import io
import logging
import random
import sys
import threading
import time
from collections.abc import Coroutine
from logging.handlers import RotatingFileHandler

from PIL import Image

from busylib import display, types
from busylib.client import AsyncBusyBar

APP_ID = "snake-demo"

logger = logging.getLogger(__name__)


class SnakeState:
    """
    Mutable snake game state.
    """

    def __init__(
        self,
        width: int,
        height: int,
        snake: list[tuple[int, int]],
        direction: tuple[int, int],
        food: tuple[int, int],
    ) -> None:
        """
        Store board size, snake body, direction, and current food position.
        """
        self.width = width
        self.height = height
        self.snake = snake
        self.direction = direction
        self.food = food
        self.score = 0
        self.alive = True


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


def parse_args() -> argparse.Namespace:
    """
    Parse CLI args for device, display, and tick interval.
    """
    parser = argparse.ArgumentParser(description="BusyBar snake example.")
    parser.add_argument("--addr", default="http://10.0.4.20", help="Device address.")
    parser.add_argument("--token", default=None, help="Bearer token.")
    parser.add_argument("--app-id", default=APP_ID, help="App id for assets.")
    parser.add_argument("--display", default="front", help="Display name: front/back.")
    parser.add_argument(
        "--tick", type=float, default=0.2, help="Tick interval in seconds."
    )
    parser.add_argument("--log-level", default="INFO", help="Logging level.")
    parser.add_argument("--log-file", default=None, help="Log file path.")
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=True,
        help="Disable console logs (default: quiet).",
    )
    return parser.parse_args()


def _validate_assets() -> None:
    """
    No-op placeholder for future asset validation.
    """
    return None


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


def _build_client(addr: str, token_arg: str | None) -> AsyncBusyBar:
    """
    Build AsyncBusyBar with the provided address and token.
    """
    base_addr = addr if addr.startswith(("http://", "https://")) else f"http://{addr}"
    return AsyncBusyBar(addr=base_addr, token=token_arg)


def _build_pixel_png(color: tuple[int, int, int]) -> bytes:
    """
    Build a 1x1 PNG image for a single pixel.
    """
    image = Image.new("RGB", (1, 1), color=color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _upload_pixel_assets(
    runner: AsyncRunner,
    client: AsyncBusyBar,
    app_id: str,
) -> tuple[str, str]:
    """
    Upload snake and food pixel assets and return their filenames.
    """
    snake_name = "snake_pixel.png"
    food_name = "food_pixel.png"
    runner.run(
        client.upload_asset(app_id, snake_name, _build_pixel_png((255, 255, 255)))
    )
    runner.run(
        client.upload_asset(app_id, food_name, _build_pixel_png((0, 255, 0)))
    )
    return snake_name, food_name


def _draw_text_lines(
    runner: AsyncRunner,
    client: AsyncBusyBar,
    app_id: str,
    spec: display.DisplaySpec,
    lines: list[str],
    *,
    font: str = "small",
) -> None:
    """
    Draw a list of text lines on the device display.
    """
    line_height = 8 if spec.height >= 16 else max(1, spec.height // max(1, len(lines)))
    elements = []
    for idx, line in enumerate(lines):
        elements.append(
            types.TextElement(
                id=f"line-{idx}",
                type="text",
                text=line,
                x=0,
                y=idx * line_height,
                align="top_left",
                font=font,
                display=spec.name,
            )
        )
    payload = types.DisplayElements(app_id=app_id, elements=elements)
    runner.run(client.draw_on_display(payload))


def _wait_for_enter(stdscr: curses.window) -> None:
    """
    Block until Enter is pressed.
    """
    stdscr.nodelay(False)
    stdscr.keypad(True)
    while True:
        key = stdscr.getch()
        if key in (ord("\n"), ord("\r")):
            return


def _place_food(
    rng: random.Random,
    width: int,
    height: int,
    snake: list[tuple[int, int]],
) -> tuple[int, int]:
    """
    Pick a free cell for food, avoiding the snake body.
    """
    occupied = set(snake)
    candidates = [
        (x, y) for y in range(height) for x in range(width) if (x, y) not in occupied
    ]
    return rng.choice(candidates) if candidates else (0, 0)


def _is_opposite(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """
    Check if direction b is the opposite of direction a.
    """
    return a[0] + b[0] == 0 and a[1] + b[1] == 0


def _update_direction(
    current: tuple[int, int],
    requested: tuple[int, int],
) -> tuple[int, int]:
    """
    Update direction unless it would reverse into itself.
    """
    if _is_opposite(current, requested):
        return current
    return requested


def _sanitize_nickname(value: str) -> str:
    """
    Normalize a nickname to up to three uppercase letters.

    Non-letter characters are ignored, and the result is uppercased.
    """
    letters = [ch for ch in value if ch.isalpha()]
    return "".join(letters).upper()[:3]


def _prompt_nickname(
    stdscr: curses.window,
    runner: AsyncRunner,
    client: AsyncBusyBar,
    app_id: str,
    spec: display.DisplaySpec,
    score: int,
) -> str:
    """
    Ask the player for a 3-letter nickname after game over.

    Shows the score centered and returns the entered nickname.
    """
    stdscr.nodelay(False)
    stdscr.keypad(True)
    nickname = ""

    while True:
        device_lines = [
            "GAME OVER",
            f"SCORE {score}",
            f"NAME {nickname.ljust(3, '_')}",
        ]
        _draw_text_lines(runner, client, app_id, spec, device_lines)

        key = stdscr.getch()
        if key in (curses.KEY_BACKSPACE, 127, 8):
            nickname = nickname[:-1]
            continue
        if key in (ord("\n"), ord("\r")):
            if len(nickname) == 3:
                return _sanitize_nickname(nickname)
            continue
        if key != -1:
            ch = chr(key)
            if ch.isalpha() and len(nickname) < 3:
                nickname += ch.upper()


def _step_game(state: SnakeState) -> str:
    """
    Advance one step and return the event type: move, eat, or dead.
    """
    if not state.alive:
        return "dead"
    dx, dy = state.direction
    head_x, head_y = state.snake[0]
    next_head = (head_x + dx, head_y + dy)
    nx, ny = next_head
    if nx < 0 or ny < 0 or nx >= state.width or ny >= state.height:
        state.alive = False
        return "dead"
    if next_head in state.snake:
        state.alive = False
        return "dead"

    if next_head == state.food:
        state.snake.insert(0, next_head)
        state.score += 1
        return "eat"

    state.snake.insert(0, next_head)
    state.snake.pop()
    return "move"


def _run_game(
    stdscr: curses.window,
    runner: AsyncRunner,
    client: AsyncBusyBar,
    app_id: str,
    spec: display.DisplaySpec,
    tick: float,
) -> None:
    """
    Main snake loop: handles input, updates state, and renders frames.
    """
    curses.curs_set(0)
    stdscr.nodelay(True)
    stdscr.keypad(True)
    rng = random.Random()

    start_x = spec.width // 2
    start_y = spec.height // 2
    snake = [(start_x, start_y), (start_x - 1, start_y)]
    state = SnakeState(spec.width, spec.height, snake, (1, 0), (0, 0))
    state.food = _place_food(rng, spec.width, spec.height, state.snake)
    snake_asset, food_asset = _upload_pixel_assets(runner, client, app_id)
    next_tick = time.monotonic()
    event = "move"

    _draw_text_lines(
        runner,
        client,
        app_id,
        spec,
        ["SNAKE", "PRESS ENTER"],
    )
    _wait_for_enter(stdscr)

    while state.alive:
        now = time.monotonic()
        if now >= next_tick:
            event = _step_game(state)
            if event == "eat":
                state.food = _place_food(rng, spec.width, spec.height, state.snake)
            if event == "dead":
                break
            elements = []
            for idx, (x, y) in enumerate(state.snake):
                elements.append(
                    {
                        "id": f"snake-{idx}",
                        "type": "image",
                        "x": x,
                        "y": y,
                        "path": snake_asset,
                        "display": spec.name.value,
                    }
                )
            fx, fy = state.food
            elements.append(
                {
                    "id": "food",
                    "type": "image",
                    "x": fx,
                    "y": fy,
                    "path": food_asset,
                    "display": spec.name.value,
                }
            )
            payload = {"app_id": app_id, "elements": elements}
            runner.run(client.draw_on_display(payload))
            next_tick = now + tick

        try:
            key = stdscr.getch()
        except curses.error:
            key = -1

        if key in (ord("q"), ord("Q")):
            break
        if key == curses.KEY_UP:
            state.direction = _update_direction(state.direction, (0, -1))
        elif key == curses.KEY_DOWN:
            state.direction = _update_direction(state.direction, (0, 1))
        elif key == curses.KEY_LEFT:
            state.direction = _update_direction(state.direction, (-1, 0))
        elif key == curses.KEY_RIGHT:
            state.direction = _update_direction(state.direction, (1, 0))

    nickname = _prompt_nickname(stdscr, runner, client, app_id, spec, state.score)
    logger.info("Snake game over score=%s nickname=%s", state.score, nickname)


def main() -> None:
    """
    Entry point for the snake example.
    """
    try:
        args = parse_args()
        _configure_logging(level=args.log_level, log_file=args.log_file)
        _validate_assets()
        spec = display.get_display_spec(args.display)
        runner = AsyncRunner()
        runner.start()
        client = _build_client(args.addr, args.token)
        try:
            curses.wrapper(_run_game, runner, client, args.app_id, spec, args.tick)
        finally:
            try:
                runner.run(client.clear_display())
                runner.run(client.aclose())
            finally:
                runner.stop()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
