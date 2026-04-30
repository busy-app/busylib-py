from __future__ import annotations

import io
import re

import httpx
from PIL import Image

from busylib.client import AsyncBusyBar

from examples.bc.runner import AsyncRunner

from examples.hltv_live.hltv_api import HltvTeam
from examples.hltv_live.rendering import shorten_team_name


class LogoCache:
    """
    Кэш логотипов команд для BusyBar.

    Скачивает логотипы, приводит их к нужному размеру и загружает в ассеты.
    """

    def __init__(
        self,
        client: AsyncBusyBar,
        runner: AsyncRunner,
        *,
        app_id: str,
        logo_size: int,
        timeout_seconds: float,
    ) -> None:
        """
        Инициализировать кэш логотипов.

        Принимает клиента BusyBar и параметры загрузки.
        """
        self._client = client
        self._runner = runner
        self._app_id = app_id
        self._logo_size = logo_size
        self._timeout = timeout_seconds
        self._uploaded: set[str] = set()
        self._by_url: dict[str, str] = {}
        self._http = httpx.Client(timeout=timeout_seconds)

    def close(self) -> None:
        """
        Закрыть HTTP-клиент.

        Нужен для освобождения ресурсов.
        """
        self._http.close()

    def logo_path_for_team(self, team: HltvTeam) -> str | None:
        """
        Вернуть путь ассета для логотипа команды.

        Возвращает None, если логотип отсутствует или загрузка не удалась.
        """
        if team.logo_url is None:
            return None
        cached = self._by_url.get(team.logo_url)
        if cached is not None:
            return cached
        filename = _build_logo_filename(team)
        data = _download_logo(self._http, team.logo_url)
        if data is None:
            return None
        png_data = _prepare_logo_png(data, self._logo_size)
        if png_data is None:
            return None
        if filename not in self._uploaded:
            self._runner.run(self._client.upload_asset(self._app_id, filename, png_data))
            self._uploaded.add(filename)
        self._by_url[team.logo_url] = filename
        return filename


def _build_logo_filename(team: HltvTeam) -> str:
    """
    Сформировать безопасное имя файла для логотипа.

    Использует id команды или укороченное имя.
    """
    if team.id is not None:
        base = f"team_{team.id}"
    else:
        safe = shorten_team_name(team.name, 20).lower()
        base = re.sub(r"[^a-z0-9._-]+", "-", safe).strip("-") or "team"
    return f"{base}.png"


def _download_logo(client: httpx.Client, url: str) -> bytes | None:
    """
    Скачать изображение логотипа.

    Возвращает байты изображения или None при ошибке.
    """
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError:
        return None
    return response.content


def _prepare_logo_png(data: bytes, size: int) -> bytes | None:
    """
    Подготовить PNG логотипа нужного размера.

    Сохраняет пропорции и добавляет прозрачный фон.
    """
    try:
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:  # noqa: BLE001
        return None
    image.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    offset = ((size - image.width) // 2, (size - image.height) // 2)
    canvas.paste(image, offset, image)
    output = io.BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()
