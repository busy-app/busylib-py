"""
Refresh the counts in the stock assets guide from the firmware sources.

From the firmware, not from a bar: a bar carries whatever its owner has
uploaded or deleted since it was unboxed, so counting one describes that
bar rather than the product. The firmware repository is where "what every
bar ships with" is actually decided.

    uv run python scripts/stock_assets_map.py --firmware ../bsb-firmware

It reads the tree with `git ls-tree`, so any ref works and the checkout
does not have to be on it. `--check` reports drift and exits non-zero
instead of writing, which is what a firmware release wants.

The guide names individual assets by hand - a table is written for a
reader, not generated for one - but the counts go stale quietly with
every release, and a stale count is what makes a reader stop trusting the
prose around it. So only the counts are generated.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import subprocess
import sys

GUIDE = pathlib.Path(__file__).resolve().parent.parent / "docs/guides/stock-assets.md"

BEGIN = "<!-- begin stock assets map -->"
END = "<!-- end stock assets map -->"

# Where each folder on the device comes from in the firmware tree, and
# which files in it end up there. The extensions differ because the build
# converts them: a .png becomes an .image, a .zip an .anim, a .wav a .snd.
SOURCES = (
    ("Icons and pictures", "shared/images", "assets/shared/images/external", ".png"),
    ("Status animations", "shared/animations", "assets/shared/animations", ".zip"),
    ("Fonts", "shared/fonts", "assets/shared/fonts", ".font"),
    ("Notification sounds", "shared/sounds", "assets/shared/sounds", ".wav"),
    ("Timer animations", "busy/animations", "assets/animations/busy", ".zip"),
    ("Timer pictures", "busy/images", "assets/images/external/busy", ".png"),
    ("Timer sounds", "busy/sounds", "assets/sounds/busy", ".wav"),
    (
        "Themes",
        "busy/themes",
        "applications/main/busy/resources/apps_assets/busy/themes",
        "theme.json",
    ),
)


def _git(firmware: pathlib.Path, *args: str) -> str:
    """
    Run one git command in the firmware checkout.
    """
    result = subprocess.run(
        ["git", "-C", str(firmware), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _files(firmware: pathlib.Path, ref: str, path: str, suffix: str) -> list[str]:
    """
    The files one folder contributes, ignoring anything else living there.

    Fonts keep their TrueType sources next to the built ones and themes
    are a directory each, so the suffix does the filtering rather than a
    plain listing.
    """
    listing = _git(firmware, "ls-tree", "-r", "--name-only", ref, "--", path)
    return sorted(
        name for name in listing.splitlines() if name.endswith(suffix) and name
    )


def _since(firmware: pathlib.Path, ref: str, path: str) -> str:
    """
    The earliest firmware release that carried this folder.

    Taken from the release containing the commit that added its first
    file: someone asking "can I rely on this" is asking which firmware,
    not which commit. Release candidates are ignored, and a folder no
    release has reached yet says so.
    """
    added = _git(
        firmware, "log", "--diff-filter=A", "--format=%H", "--reverse", ref, "--", path
    ).split()
    if not added:
        return "-"
    tags = [
        tag
        for tag in _git(firmware, "tag", "--contains", added[0]).split()
        if "rc" not in tag and tag[:1].isdigit()
    ]
    if not tags:
        return "unreleased"
    return min(tags, key=lambda tag: [int(part) for part in tag.split(".")])


def _last_change(firmware: pathlib.Path, ref: str, path: str) -> str:
    """
    When the folder last changed, which says whether it has settled.
    """
    return (
        _git(
            firmware, "log", "-1", "--format=%ad", "--date=short", ref, "--", path
        ).strip()
        or "-"
    )


def collect(firmware: pathlib.Path, ref: str) -> str:
    """
    Render the table the guide carries.
    """
    described = _git(firmware, "log", "-1", "--format=%h, %ad", "--date=short", ref)

    rows = []
    for title, target, path, suffix in SOURCES:
        names = _files(firmware, ref, path, suffix)
        note = ""
        if target == "shared/images":
            stickers = sum(1 for name in names if "/dt_" in name)
            note = f", {stickers} of them the `dt_*` sticker set"
        rows.append(
            f"| {title} | `{target}/` | {len(names)}{note} "
            f"| {_since(firmware, ref, path)} | {_last_change(firmware, ref, path)} |"
        )

    return "\n".join(
        [
            f"Counted from the firmware sources at `{described.strip()}`:",
            "",
            "| | On the device | How many | Since | Last changed |",
            "| --- | --- | --- | --- | --- |",
            *rows,
        ]
    )


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
        print(
            "stock assets map is out of date - run make stock-assets", file=sys.stderr
        )
        return 1
    GUIDE.write_text(updated)
    print(f"{GUIDE}: updated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--firmware",
        type=pathlib.Path,
        required=True,
        help="path to a bsb-firmware checkout",
    )
    parser.add_argument(
        "--ref",
        default="origin/dev",
        help="which ref to read (default: origin/dev)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="report drift and exit non-zero instead of writing",
    )
    args = parser.parse_args()

    if not (args.firmware / ".git").exists():
        print(f"{args.firmware}: not a git checkout", file=sys.stderr)
        return 2

    try:
        table = collect(args.firmware, args.ref)
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or "git failed", file=sys.stderr)
        return 2
    return rewrite(table, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
