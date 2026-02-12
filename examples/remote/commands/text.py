from __future__ import annotations

import argparse
import logging

from busylib import display, types
from busylib.client import AsyncBusyBar

from examples.remote.command_core import CommandArgumentParser, CommandBase

logger = logging.getLogger(__name__)


class TextCommand(CommandBase):
    """
    Draw a large scrolling text on the front display.
    """

    name = "text"
    aliases = ("t",)

    def __init__(self, client: AsyncBusyBar) -> None:
        """
        Store the client used to send drawing commands.
        """
        self._client = client

    @classmethod
    def build(cls, **deps: object) -> TextCommand | None:
        """
        Build the command if the BusyBar client is available.
        """
        client = deps.get("client")
        if isinstance(client, AsyncBusyBar):
            return cls(client)
        return None

    def build_parser(self) -> CommandArgumentParser:
        """
        Build the argument parser for the text command.
        """
        parser = CommandArgumentParser(prog="text", add_help=True)
        parser.add_argument("text", nargs="+", help="Text to render")
        parser.add_argument(
            "--x",
            type=int,
            default=0,
            help="X-position",
        )
        parser.add_argument(
            "--y",
            type=int,
            default=8,
            help="Y-position",
        )
        parser.add_argument(
            "--font",
            choices=["small", "medium", "medium_condensed", "big"],
            default="big",
            help="Font name",
        )
        parser.add_argument(
            "--align",
            choices=[
                "top_left",
                "top_mid",
                "top_right",
                "mid_left",
                "center",
                "mid_right",
                "bottom_left",
                "bottom_mid",
                "bottom_right",
            ],
            default="mid_left",
            help="Text alignment",
        )
        parser.add_argument(
            "--scroll-rate",
            type=int,
            default=1000,
            help="Scroll rate for long text",
        )
        return parser

    async def run(self, args: argparse.Namespace) -> None:
        """
        Send the text element to the display.
        """
        logger.info("command:text")
        message = " ".join(args.text).strip()
        if not message:
            return
        spec = display.get_display_spec(display.FRONT_DISPLAY)
        scroll_rate = (
            args.scroll_rate if args.scroll_rate and args.scroll_rate > 0 else None
        )
        element = types.TextElement(
            id="remote_cmd_text",
            x=args.x,
            y=args.y,
            text=message,
            font=args.font,
            align=args.align,
            width=spec.width,
            scroll_rate=scroll_rate,
            display=types.DisplayName.FRONT,
        )
        payload = types.DisplayElements(app_id="remote_command", elements=[element])
        await self._client.draw_on_display(payload)
