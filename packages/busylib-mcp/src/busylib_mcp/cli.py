from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from .config import MCPSettings
from .server import serve_stdio


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """
    Разобрать аргументы запуска MCP-сервера.

    CLI позволяет переопределить env-параметры без изменения окружения и
    поддерживает отдельный режим проверки конфигурации.
    """
    parser = argparse.ArgumentParser(
        description="Run busylib MCP server over stdio transport.",
    )
    parser.add_argument(
        "--addr",
        default=None,
        help="Busy Bar base URL override.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Busy Bar API token override.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=None,
        help="Request timeout override in seconds.",
    )
    parser.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS certificate verification.",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Validate config and print effective safe values.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def load_settings(args: argparse.Namespace) -> MCPSettings:
    """
    Собрать объект настроек из окружения и CLI override.

    Поля со значением `None` не передаются в конструктор, чтобы сохранить
    приоритет значений из переменных окружения.
    """
    override: dict[str, str | float | bool] = {}
    if args.addr is not None:
        override["addr"] = args.addr
    if args.token is not None:
        override["token"] = args.token
    if args.timeout_seconds is not None:
        override["timeout_seconds"] = args.timeout_seconds
    if args.insecure:
        override["verify_ssl"] = False
    return MCPSettings(**override)


def main(argv: Sequence[str] | None = None) -> int:
    """
    Выполнить запуск CLI и вернуть код завершения процесса.

    В режиме `--check-config` печатается безопасный конфиг для быстрой
    диагностики. В обычном режиме запускается stdio-bootstrap сервера.
    """
    args = parse_args(argv)
    settings = load_settings(args)

    if args.check_config:
        print(settings.safe_dict())
        return 0

    return serve_stdio(settings)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
