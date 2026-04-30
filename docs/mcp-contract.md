# MCP Contract (v1)

Этот документ фиксирует публичный контракт MCP-сервера для `busylib-py`.

## Transport and scope

- Transport: `stdio`.
- Один процесс MCP-сервера управляет одним Busy Bar устройством.
- `v1` реализует только `tools` (без `resources` и `prompts`).

## Configuration

Обязательная конфигурация задается через переменные окружения:

- `BUSYLIB_MCP_ADDR`: адрес устройства (IP/hostname).
- `BUSYLIB_MCP_TOKEN`: API token устройства.

Опциональная конфигурация:

- `BUSYLIB_MCP_TIMEOUT_SECONDS`: таймаут HTTP-запросов (по умолчанию `10.0`).
- `BUSYLIB_MCP_VERIFY_SSL`: включить/отключить верификацию TLS для cloud/local HTTPS (по умолчанию `true`).

## Tool naming

Имена tools используют неймспейсы:

- `device.*`
- `display.*`
- `audio.*`
- `assets.*`

## Tools (v1)

### `device.get_version`

Возвращает данные версии устройства.

Input:
- пустой объект `{}`.

Output:
- объект с полями версии (`firmware`, `api`, дополнительные поля из `busylib.types.Version`).

### `device.get_info`

Возвращает базовый срез состояния устройства для диагностики.

Input:
- пустой объект `{}`.

Output:
- объект:
  - `name: str | null`
  - `time: str | null`
  - `brightness: int | null`
  - `volume: int | null`
  - `wifi_ssid: str | null`
  - `ip: str | null`
  - `field_errors: dict[str, str]` (частичные ошибки по полям)

### `display.draw_text`

Рисует текст на выбранном дисплее через `draw_on_display`.

Input:
- `text: str` (обязательно)
- `display: "front" | "back"` (опционально, по умолчанию `front`)
- `x: int` (опционально, по умолчанию `0`)
- `y: int` (опционально, по умолчанию `0`)
- `font: "small" | "medium" | "medium_condensed" | "big"` (обязательно)
- `color: str` (опционально, hex-цвет, по умолчанию `"#ffffff"`)
- `clear: bool` (опционально, очистить экран перед рисованием)

Output:
- `{"success": true, "display": "...", "rendered_elements": <int>}`

### `audio.play`

Запускает воспроизведение файла из `assets`.

Input:
- `application_name: str` (обязательно)
- `path: str` (обязательно, путь внутри app assets)
- `loop: bool` (опционально, по умолчанию `false`)
- `volume: int` (опционально, `0..100`; если передан, сервер сначала вызывает `set_volume`)

Output:
- `{"success": true}`

### `audio.stop`

Останавливает текущее воспроизведение.

Input:
- пустой объект `{}`.

Output:
- `{"success": true}`

### `assets.upload`

Загружает файл в assets-пространство приложения.

Input:
- `application_name: str` (обязательно)
- `filename: str` (обязательно)
- `content_base64: str` (обязательно, бинарные данные файла в base64)

Output:
- `{"success": true, "filename": "...", "size": <int>}`

### `assets.delete_app`

Удаляет все assets указанного приложения.

Input:
- `application_name: str` (обязательно)

Output:
- `{"success": true, "application_name": "..."}`

## Error contract

Все ошибки инструментов нормализуются в единый формат:

- `code: str`
- `message: str`
- `details: dict[str, str | int | float | bool | None]`

### Error codes (v1)

- `CONFIG_ERROR`: невалидная или неполная конфигурация MCP-сервера.
- `VALIDATION_ERROR`: невалидный input tool-вызова.
- `DEVICE_UNREACHABLE`: устройство недоступно по сети / timeout.
- `DEVICE_API_ERROR`: устройство вернуло HTTP-ошибку.
- `DEVICE_PROTOCOL_ERROR`: неожиданный формат ответа от устройства.
- `INTERNAL_ERROR`: непредвиденная ошибка на стороне MCP-сервера.

## Security and logging

- Логи не должны содержать `BUSYLIB_MCP_TOKEN` и значения `content_base64`.
- В `details` нельзя возвращать секреты и сырые бинарные payload.
- Для `DEVICE_API_ERROR` возвращать только безопасную диагностику: `status_code`, `path`, `request_id` (если есть).
