from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable

from busylib.client import AsyncBusyBar

logger = logging.getLogger(__name__)

DANGEROUS_PREFIXES = (
    "set_",
    "delete_",
    "update_",
    "upload_",
    "write_",
    "install_",
    "abort_",
    "unlink_",
    "reboot",
    "reset",
    "usb_",
    "format_",
    "clear_",
)
BLACKLISTED_METHODS = {
    "aclose",
}


def _format_call_result(result: object) -> str:
    """
    Format a call result for status output.
    """
    if result is None:
        return "ok"
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    if isinstance(result, bytes):
        return f"bytes:{len(result)}"
    if isinstance(result, (dict, list, str, int, float, bool)):
        return json.dumps(result, ensure_ascii=True, separators=(",", ":"))
    return repr(result)


def build_call_handler(
    client: AsyncBusyBar,
    status_message: Callable[[str], None],
) -> Callable[[list[str]], Awaitable[None]]:
    """
    Build a handler that calls BusyBar client methods from command arguments.
    """

    async def _handler(args: list[str]) -> None:
        """
        Dispatch a method call with key=value arguments.
        """
        if not args:
            logger.warning("call: missing method name")
            status_message("call: missing method name")
            return

        method_name = args[0].strip()
        if not method_name:
            logger.warning("call: empty method name")
            status_message("call: empty method name")
            return
        if method_name.startswith("_") or method_name in BLACKLISTED_METHODS:
            logger.warning("call: method %s is not allowed", method_name)
            status_message(f"call {method_name}: not allowed")
            return

        method = getattr(client, method_name, None)
        if method is None or not callable(method):
            logger.warning("call: method %s not found", method_name)
            status_message(f"call {method_name}: not found")
            return

        force = False
        kwargs: dict[str, str] = {}
        for token in args[1:]:
            if token == "--force" or token.startswith("--force="):
                force = True
                continue
            if "=" not in token:
                logger.warning("call: argument %s must be key=value", token)
                status_message(f"call {method_name}: invalid arg {token}")
                return
            key, value = token.split("=", 1)
            if not key:
                logger.warning("call: empty argument name in %s", token)
                status_message(f"call {method_name}: empty arg name")
                return
            kwargs[key] = value

        if method_name.startswith(DANGEROUS_PREFIXES) and not force:
            logger.warning("call: method %s requires --force", method_name)
            status_message(f"call {method_name}: requires --force")
            return

        logger.info("command:call %s %s", method_name, kwargs)
        try:
            result = method(**kwargs)
            if asyncio.iscoroutine(result):
                result = await result
        except Exception as exc:  # noqa: BLE001
            logger.exception("call: failed %s", method_name)
            status_message(f"call {method_name}: error {exc}")
            return
        status_message(f"call {method_name}: {_format_call_result(result)}")

    return _handler
