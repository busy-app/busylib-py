import json
import sys

from .config import MCPSettings


def serve_stdio(settings: MCPSettings) -> int:
    """
    Запустить stdio-точку входа MCP-сервера.

    На этапе bootstrap функция валидирует конфигурацию и сообщает текущий
    статус инициализации. Реальный MCP runtime и tools будут добавлены в
    следующем этапе реализации.
    """
    payload = {
        "status": "bootstrap",
        "message": "busylib-mcp server skeleton is ready; tools are not wired yet",
        "config": settings.safe_dict(),
    }
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    return 0
