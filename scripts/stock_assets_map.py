"""
Refresh the counts in the stock assets guide from a bar.

The guide names individual assets by hand, because a table is written for
a reader and not generated for one - but the counts go stale quietly with
every firmware release, and a stale count is what makes a reader stop
trusting the rest. So this reads the folders off a bar and rewrites the
numbers between the markers in the guide, leaving the prose alone.

    uv run python scripts/stock_assets_map.py --host 192.168.1.50 --token PIN

`--check` reports what would change and exits non-zero instead of
writing, which is what a firmware bump wants: see the drift, decide what
the prose should say about it.
"""

from __future__ import annotations

import argparse
import asyncio
import pathlib
import re
import sys

from busylib import AsyncBusyBar

GUIDE = pathlib.Path(__file__).resolve().parent.parent / "docs/guides/stock-assets.md"

BEGIN = "<!-- begin stock assets map -->"
END = "<!-- end stock assets map -->"

# What to count, in the order the table reads.
FOLDERS = (
    ("Icons and pictures", "shared/images"),
    ("Status animations", "shared/animations"),
    ("Fonts", "shared/fonts"),
    ("Notification sounds", "shared/sounds"),
    ("Timer animations", "busy/animations"),
    ("Timer pictures", "busy/images"),
    ("Timer sounds", "busy/sounds"),
    ("Themes", "busy/themes"),
)

ROOT = "/ext/apps_assets"


async def _count(client: AsyncBusyBar, folder: str) -> tuple[int, list[str]]:
    """
    How many assets a folder holds, and their names.
    """
    listing = await client.storage_list(f"{ROOT}/{folder}")
    names = sorted(item.name for item in listing.list)
    return len(names), names


async def collect(host: str, token: str) -> str:
    """
    Read every folder and render the table the guide carries.
    """
    opener = AsyncBusyBar(host, token=token)
    async with opener:
        access = (await opener.access_token_mint("stock-assets-map")).token

    rows = []
    async with AsyncBusyBar(host, token=access) as client:
        firmware = (await client.status_firmware()).version
        for title, folder in FOLDERS:
            total, names = await _count(client, folder)
            note = ""
            if folder == "shared/images":
                stickers = sum(1 for name in names if name.startswith("dt_"))
                note = f", {stickers} of them the `dt_*` sticker set"
            rows.append(f"| {title} | `{folder}/` | {total}{note} |")

    table = "\n".join(
        [
            f"Counted on firmware `{firmware}`:",
            "",
            "| | Folder | How many |",
            "| --- | --- | --- |",
            *rows,
        ]
    )
    return table


def rewrite(table: str, *, check: bool) -> int:
    """
    Put the table between the markers, or say what would change.
    """
    text = GUIDE.read_text()
    # Non-greedy across everything, including the empty case: the markers
    # sit on adjacent lines until this has run once.
    pattern = re.compile(f"{re.escape(BEGIN)}.*?{re.escape(END)}", re.DOTALL)
    if not pattern.search(text):
        print(f"{GUIDE}: markers not found", file=sys.stderr)
        return 2

    updated = pattern.sub(f"{BEGIN}\n{table}\n{END}", text)
    if updated == text:
        print("stock assets map is current")
        return 0
    if check:
        print("stock assets map is out of date - run make stock-assets", file=sys.stderr)
        return 1
    GUIDE.write_text(updated)
    print(f"{GUIDE}: updated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="bar address")
    parser.add_argument("--token", required=True, help="PIN or access token")
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of writing",
    )
    args = parser.parse_args()

    table = asyncio.run(collect(args.host, args.token))
    return rewrite(table, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
