from __future__ import annotations

from collections.abc import Iterable

from examples.hltv_live.hltv_api import LiveMatch


class LiveMatchRotator:
    """
    Ротатор live-матчей с обновлением по интервалам.

    Хранит список матчей, переключает их каждые N секунд и сообщает,
    когда нужно обновлять данные из источника.
    """

    def __init__(
        self,
        *,
        display_seconds: float,
        refresh_seconds: float,
    ) -> None:
        """
        Инициализировать ротатор с интервалами показа и обновления.

        Все интервалы задаются в секундах.
        """
        if display_seconds <= 0:
            raise ValueError("display_seconds должен быть больше 0")
        if refresh_seconds <= 0:
            raise ValueError("refresh_seconds должен быть больше 0")
        self._display_seconds = float(display_seconds)
        self._refresh_seconds = float(refresh_seconds)
        self._matches: list[LiveMatch] = []
        self._index = 0
        self._last_switch: float | None = None
        self._last_refresh: float | None = None
        self._last_ids: tuple[int, ...] = ()

    def should_refresh(self, now: float) -> bool:
        """
        Проверить, нужно ли обновить данные.

        Возвращает True, если с последнего обновления прошло refresh_seconds.
        """
        if self._last_refresh is None:
            return True
        return (now - self._last_refresh) >= self._refresh_seconds

    def mark_refreshed(self, now: float) -> None:
        """
        Отметить время последнего обновления.

        Сохраняет текущее время для следующих проверок should_refresh.
        """
        self._last_refresh = now

    def set_matches(
        self,
        matches: Iterable[LiveMatch],
        *,
        now: float,
    ) -> None:
        """
        Обновить список матчей для ротации.

        Если список изменился, сбрасывает индекс и таймер переключения.
        """
        items = list(matches)
        ids = tuple(match.match_id for match in items)
        if ids != self._last_ids:
            self._matches = items
            self._index = 0
            self._last_switch = now
            self._last_ids = ids
        else:
            self._matches = items

    def current(self, now: float) -> LiveMatch | None:
        """
        Вернуть текущий матч с учётом ротации.

        При превышении display_seconds переключает индекс на следующий.
        """
        if not self._matches:
            return None
        if self._last_switch is None:
            self._last_switch = now
            self._index = 0
            return self._matches[self._index]
        elapsed = now - self._last_switch
        if elapsed >= self._display_seconds:
            steps = int(elapsed // self._display_seconds)
            self._index = (self._index + steps) % len(self._matches)
            self._last_switch += steps * self._display_seconds
        return self._matches[self._index]

    @property
    def display_seconds(self) -> float:
        """
        Вернуть интервал показа матча.

        Используется для диагностики и тестов.
        """
        return self._display_seconds

    @property
    def refresh_seconds(self) -> float:
        """
        Вернуть интервал обновления данных.

        Используется для диагностики и тестов.
        """
        return self._refresh_seconds
