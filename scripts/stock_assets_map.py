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
import io
import json
import pathlib
import re
import subprocess
import sys
import zipfile

GUIDE = pathlib.Path(__file__).resolve().parent.parent / "docs/guides/stock-assets.md"

BEGIN = "<!-- begin stock assets map -->"
END = "<!-- end stock assets map -->"

GALLERY_BEGIN = "<!-- begin stock assets gallery -->"
GALLERY_END = "<!-- end stock assets gallery -->"

ANIMATIONS_BEGIN = "<!-- begin stock animations gallery -->"
ANIMATIONS_END = "<!-- end stock animations gallery -->"

SOUNDS_BEGIN = "<!-- begin stock sounds gallery -->"
SOUNDS_END = "<!-- end stock sounds gallery -->"

# Animations are the one thing that cannot be linked: the source is a zip
# of frames, and no browser unpacks one. So they are the exception to the
# rule above - built into a GIF and committed here - and these are the
# numbers that keep that exception small.
# Beside the guide, not under a site-wide assets folder: a relative
# link from here resolves both in the built site and in GitHub's own
# view of the file.
ANIMATION_DIR = GUIDE.parent / "assets/animations"
ANIMATION_FRAMES = 16
ANIMATION_WIDTH = 160
ANIMATION_SCALE = (2, 6)

# One palette for the whole animation. Quantising each frame on its own
# put a different palette under every frame, and the colours jumped
# between them - the acid look this exists to avoid.
ANIMATION_COLOURS = 128

# The firmware is public, so the sounds can be played straight from it.
RAW = "https://raw.githubusercontent.com/busy-app/busybar-firmware"

# The pictures are built rather than linked, because the two places this
# guide is read disagree about what they allow. The site takes styling
# and would enlarge a linked original with CSS; GitHub strips style
# attributes, which would leave a 5x5 white icon blurred onto a white
# page. So the enlargement and the unlit-black background are baked into
# the file, and the tag asks for the size the file already is - which
# needs no styling anywhere and cannot be smoothed by anyone.
IMAGE_DIR = GUIDE.parent / "assets/images"
IMAGE_WIDTH = 48
IMAGE_SCALE = (2, 8)

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


def _preview(firmware: pathlib.Path, ref: str, path: str, *, write: bool) -> str:
    """
    One picture, built beside the guide and shown at its own size.

    Markdown rather than an `<img>` tag, and no width. The site serves
    each page from a directory of its own, and only the Markdown form has
    its relative path rewritten to match - a raw tag resolves against the
    page's URL and gives a broken picture. The size is baked into the
    file, so a width attribute would have nothing to add.
    """
    name = pathlib.Path(path).stem
    picture, _ = _thumbnail(firmware, ref, path)
    if write:
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        (IMAGE_DIR / f"{name}.png").write_bytes(picture)
    return f"![{name}](assets/images/{name}.png)"


def _grid(
    firmware: pathlib.Path,
    ref: str,
    paths: list[str],
    *,
    write: bool,
    columns: int = 6,
) -> list[str]:
    """
    A table of pictures with their names, which is how a person picks one.
    """
    cells = [
        f"{_preview(firmware, ref, path, write=write)}<br>`{pathlib.Path(path).stem}`"
        for path in paths
    ]
    rows = [
        "| " + " | ".join(cells[i : i + columns]) + " |"
        for i in range(0, len(cells), columns)
    ]
    header = "|" + " |" * columns
    divider = "|" + " --- |" * columns
    return [header, divider, *rows]


def gallery(firmware: pathlib.Path, ref: str, *, write: bool) -> str:
    """
    Show the pictures, since a name alone does not say what an icon is.

    Only the pictures: an animation is a zip of frames and a sound is a
    sound, and neither previews in a document. Those keep their names and
    their counts.
    """
    named = [
        ("check", "checkmark_front_8x8"),
        ("error", "error_front_8x8"),
        ("info", "info_front_8x8"),
        ("low_battery", "low_battery_front_8x8"),
        ("clock", "clock_5x5"),
        ("hourglass", "hourglass_5x5"),
        ("start", "start_11x11"),
        ("setup", "setup_11x11"),
    ]
    shared = "assets/shared/images/external"
    lines = [
        "The eight with short names:",
        "",
        "| | Name | File |",
        "| --- | --- | --- |",
    ]
    for short, file_name in named:
        picture = _preview(firmware, ref, f"{shared}/{file_name}.png", write=write)
        lines.append(f"| {picture} | `{short}` | `{file_name}.image` |")

    stickers = [
        path
        for path in _files(firmware, ref, shared, ".png")
        if pathlib.Path(path).name.startswith("dt_")
    ]
    lines += [
        "",
        "The Draw Tool's set, under the names the Draw Tool shows - these are"
        " 16x16, twice the width of most built-in icons, and the layout moves"
        " the text along accordingly:",
        "",
        *_grid(firmware, ref, stickers, write=write),
    ]

    rest = [
        path
        for path in _files(firmware, ref, shared, ".png")
        if not pathlib.Path(path).name.startswith("dt_")
        and pathlib.Path(path).stem not in {name for _, name in named}
    ]
    lines += [
        "",
        "The rest of what the firmware ships, mostly its own furniture:",
        "",
        *_grid(firmware, ref, rest, write=write),
    ]

    timer = _files(firmware, ref, "assets/images/external/busy", ".png")
    lines += [
        "",
        "And the timer's own:",
        "",
        *_grid(firmware, ref, timer, write=write),
    ]
    return "\n".join(lines)


def _lit(data: bytes):
    """
    One picture on the black the panels show behind whatever is drawn.

    Composited rather than left transparent, because these are read on a
    white page as often as a dark one, and a white icon on white is not a
    preview of anything.
    """
    from PIL import Image

    frame = Image.open(io.BytesIO(data)).convert("RGBA")
    lit = Image.new("RGBA", frame.size, (0, 0, 0, 255))
    lit.alpha_composite(frame)
    return lit.convert("RGB")


def _thumbnail(firmware: pathlib.Path, ref: str, path: str) -> tuple[bytes, int]:
    """
    Build one enlarged picture, and say how wide it came out.
    """
    from PIL import Image

    raw = subprocess.run(
        ["git", "-C", str(firmware), "show", f"{ref}:{path}"],
        capture_output=True,
        check=True,
    ).stdout
    picture = _lit(raw)
    low, high = IMAGE_SCALE
    scale = min(high, max(low, round(IMAGE_WIDTH / picture.width)))
    enlarged = picture.resize(
        (picture.width * scale, picture.height * scale), Image.NEAREST
    )
    buffer = io.BytesIO()
    enlarged.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue(), enlarged.width


def _gif(firmware: pathlib.Path, ref: str, path: str) -> tuple[bytes, int, int, int]:
    """
    Build one animation into a GIF, and say how much of it was kept.

    The sources run at up to sixty frames a second and up to a hundred
    and eighty frames long, which is a quarter of a megabyte per picture -
    too much to carry for something a reader glances at. So the frames
    are thinned to about two dozen and the delay stretched to match, which
    keeps the movement honest at a fraction of the weight.
    """
    from PIL import Image

    raw = subprocess.run(
        ["git", "-C", str(firmware), "show", f"{ref}:{path}"],
        capture_output=True,
        check=True,
    ).stdout
    archive = zipfile.ZipFile(io.BytesIO(raw))

    # Zips made on a Mac carry a shadow copy of every file; they are not
    # frames, and neither are the dotfiles beside them.
    names = sorted(
        name
        for name in archive.namelist()
        if name.endswith(".png") and "__MACOSX" not in name and "/." not in name
    )
    if not names:
        raise ValueError(f"{path} holds no frames")

    fps = 30
    for entry in archive.namelist():
        if entry.endswith("meta.json"):
            fps = int(json.loads(archive.read(entry)).get("fps", fps)) or fps
            break

    step = max(1, round(len(names) / ANIMATION_FRAMES))
    kept = names[::step]

    first = Image.open(io.BytesIO(archive.read(kept[0])))
    low, high = ANIMATION_SCALE
    scale = min(high, max(low, round(ANIMATION_WIDTH / first.width)))

    lit = [_lit(archive.read(name)) for name in kept]

    # Every frame indexes the same palette, built from all of them at
    # once. Per-frame palettes made the colours jump between frames.
    width, height = lit[0].size
    montage = Image.new("RGB", (width, height * len(lit)))
    for index, frame in enumerate(lit):
        montage.paste(frame, (0, index * height))
    palette = montage.quantize(colors=ANIMATION_COLOURS, method=Image.MEDIANCUT)

    frames = [
        frame.quantize(palette=palette, dither=Image.Dither.NONE).resize(
            (width * scale, height * scale), Image.NEAREST
        )
        for frame in lit
    ]

    buffer = io.BytesIO()
    frames[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=round(1000 / fps * step),
        loop=0,
        optimize=True,
    )
    return buffer.getvalue(), len(kept), len(names), frames[0].width


def animations(firmware: pathlib.Path, ref: str, *, write: bool) -> str:
    """
    Build every animation and list them, with the timer's own last.

    In check mode nothing is written, but a picture that should be here
    and is not is still reported - a gallery of broken images is exactly
    what this is meant to prevent.
    """
    missing: list[str] = []
    groups = (
        ("What the firmware ships", "assets/shared/animations"),
        ("The timer's own", "assets/animations/busy"),
    )
    lines: list[str] = []
    for title, directory in groups:
        cells = []
        for path in _files(firmware, ref, directory, ".zip"):
            name = pathlib.Path(path).stem
            gif, kept, total, _ = _gif(firmware, ref, path)
            if write:
                ANIMATION_DIR.mkdir(parents=True, exist_ok=True)
                (ANIMATION_DIR / f"{name}.gif").write_bytes(gif)
            elif not (ANIMATION_DIR / f"{name}.gif").exists():
                missing.append(name)
            cells.append(
                f"![{name}](assets/animations/{name}.gif)<br>`{name}`<br>"
                f"<small>{kept} of {total} frames</small>"
            )
        rows = [
            "| " + " | ".join(cells[i : i + 3]) + " |" for i in range(0, len(cells), 3)
        ]
        lines += [f"{title}:", "", "| | | |", "| --- | --- | --- |", *rows, ""]
    if missing:
        raise FileNotFoundError(
            "these animations are listed but not built: " + ", ".join(missing)
        )
    return "\n".join(lines).rstrip()


def sounds(firmware: pathlib.Path, ref: str) -> str:
    """
    The sounds, playable where the document is read.

    The firmware keeps them as WAV and GitHub serves that with a type a
    browser understands, so these need no copy and no conversion - the
    player points straight at the source.
    """
    sha = _git(firmware, "rev-parse", ref).strip()
    lines = ["| | Sound | Used for |", "| --- | --- | --- |"]
    used = {
        "calendar_event_starts": "an event is starting",
        "calendar_reminder_ends": "a reminder is over",
        "volume_change": "the volume moved",
        "countdown_tick": "a session's last seconds",
        "countdown_finish": "a phase ended",
        "session_completed": "the whole session ended",
    }
    for directory in ("assets/shared/sounds", "assets/sounds/busy"):
        for path in _files(firmware, ref, directory, ".wav"):
            name = pathlib.Path(path).stem
            player = (
                f'<audio controls preload="none" style="height:32px" '
                f'src="{RAW}/{sha}/{path}"></audio>'
            )
            lines.append(f"| {player} | `{name}` | {used.get(name, '-')} |")
    return "\n".join(lines)


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


def rewrite(sections: dict[tuple[str, str], str], *, check: bool) -> int:
    """
    Put each generated section between its markers, or say what would
    change.
    """
    text = GUIDE.read_text()
    updated = text
    for (begin, end), body in sections.items():
        # Non-greedy across everything, including the empty case: the
        # markers sit on adjacent lines until this has run once.
        pattern = re.compile(f"{re.escape(begin)}.*?{re.escape(end)}", re.DOTALL)
        if not pattern.search(updated):
            print(f"{GUIDE}: markers {begin} not found", file=sys.stderr)
            return 2
        updated = pattern.sub(
            lambda _, body=body, begin=begin, end=end: f"{begin}\n{body}\n{end}",
            updated,
        )
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
        sections = {
            (BEGIN, END): collect(args.firmware, args.ref),
            (GALLERY_BEGIN, GALLERY_END): gallery(
                args.firmware, args.ref, write=not args.check
            ),
            (ANIMATIONS_BEGIN, ANIMATIONS_END): animations(
                args.firmware, args.ref, write=not args.check
            ),
            (SOUNDS_BEGIN, SOUNDS_END): sounds(args.firmware, args.ref),
        }
    except subprocess.CalledProcessError as error:
        print(error.stderr.strip() or "git failed", file=sys.stderr)
        return 2
    return rewrite(sections, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
