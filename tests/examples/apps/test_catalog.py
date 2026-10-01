from __future__ import annotations

import pytest

from examples.apps import catalog
from examples.apps.model import ManagerError

# Manifests as they really are in the community catalog, quirks included.
AUDIO = """name: Audio Visualizer
author: maxswinkels
description: "Live microphone spectrum on the LEDs: five render styles (bars, mirror), and colour themes."
tags:
  - audio
  - effect
  - music
preview: ./preview.gif
"""

BAD_APPLE = """name: Bad Apple
author: codynhanpham
description: It has a screen? It can play Bad Apple. And yes, with audio, too!
tags:
  - animation
  - meme
preview: ./preview.gif
repo: https://github.com/codynhanpham/BadApple/tree/main/busy-apple
"""


def test_a_real_manifest_is_a_card() -> None:
    manifest = catalog.parse_manifest(AUDIO)

    assert manifest.name == "Audio Visualizer"
    assert manifest.author == "maxswinkels"
    assert manifest.tags == ("audio", "effect", "music")
    assert manifest.preview == "./preview.gif"
    assert manifest.description.startswith("Live microphone spectrum on the LEDs: five")


def test_a_program_that_lives_elsewhere_says_where() -> None:
    manifest = catalog.parse_manifest(BAD_APPLE)

    assert manifest.upstream.endswith("busy-apple")
    assert manifest.description.endswith("And yes, with audio, too!")


def test_a_question_mark_and_colon_in_a_plain_value_are_just_text() -> None:
    manifest = catalog.parse_manifest(
        "name: X\ndescription: It has a screen? Yes: it does.\n"
    )

    assert manifest.description == "It has a screen? Yes: it does."


def test_a_file_saved_on_windows_reads_the_same() -> None:
    """
    One manifest in the real catalog has CRLF line endings.
    """
    manifest = catalog.parse_manifest(AUDIO.replace("\n", "\r\n"))

    assert manifest.tags == ("audio", "effect", "music")
    assert manifest.preview == "./preview.gif"


@pytest.mark.parametrize(
    "text, key, expected",
    [
        ("name: 'It''s'\n", "name", "It's"),
        ('name: "say \\"hi\\""\n', "name", 'say "hi"'),
        ("name: Plain # a comment\n", "name", "Plain"),
        ("name: 'keeps # inside'\n", "name", "keeps # inside"),
        ("name: X\ntags: [a, 'b c', \"d\"]\n", "tags", ["a", "b c", "d"]),
        ("name: X\ntags:\n  - one\n  - 'two'\n", "tags", ["one", "two"]),
    ],
)
def test_the_ways_a_value_can_be_written(
    text: str, key: str, expected: str | list[str]
) -> None:
    assert catalog.parse_yaml(text)[key] == expected


def test_comments_blank_lines_and_a_document_marker_are_skipped() -> None:
    text = "---\n# a card\n\nname: X\n\n# tags next\ntags:\n  - a\n"

    assert catalog.parse_yaml(text) == {"name": "X", "tags": ["a"]}


@pytest.mark.parametrize(
    "text, complaint",
    [
        ("name: X\n  nested: 1\n", "nested values"),
        ("name: >\n  folded\n", "block scalars"),
        ("- stray\n", "list item with no list"),
        ("not a pair\n", "not a `key: value`"),
    ],
)
def test_what_is_not_understood_is_refused_not_guessed(
    text: str, complaint: str
) -> None:
    with pytest.raises(ValueError, match=complaint):
        catalog.parse_yaml(text)


def test_a_manifest_without_a_name_is_not_a_card() -> None:
    with pytest.raises(ManagerError, match="no name"):
        catalog.parse_manifest("author: x\n")


def test_an_unreadable_manifest_is_a_manager_error_with_the_line() -> None:
    with pytest.raises(ManagerError, match="line 2"):
        catalog.parse_manifest("name: X\n  nested: 1\n")


# What an install fetches --------------------------------------------------------


@pytest.mark.parametrize(
    "path, fetched",
    [
        ("app.py", True),
        ("manifest.yaml", True),
        ("requirements.txt", True),
        (".env.example", True),
        ("adapters/codex.py", True),
        ("assets/done.anim", True),
        ("LICENSE", True),
        ("preview.gif", False),
        ("Preview.PNG", False),
        ("tests/test_app.py", False),
        ("adapters/tests/x.py", False),
        (".gitignore", False),
        (".env", False),
        ("__pycache__/app.cpython-313.pyc", False),
        ("../escape.py", False),
        ("/abs.py", False),
        ("a\\b.py", False),
        ("", False),
    ],
)
def test_which_files_of_a_program_are_fetched(path: str, fetched: bool) -> None:
    assert catalog.is_runtime(path) is fetched


def test_a_preview_inside_a_subfolder_is_not_the_gallery_picture() -> None:
    """
    Only the top-level `preview.*` is the picture; a program may well keep an
    image of that name among its own assets.
    """
    assert catalog.is_runtime("assets/preview.png") is True


def test_a_listing_becomes_the_files_an_install_would_fetch() -> None:
    entries = {
        "app.py": ("aaa", 100),
        "manifest.yaml": ("bbb", 50),
        "requirements.txt": ("ccc", 20),
        ".env.example": ("ddd", 30),
        "preview.gif": ("eee", 9_000_000),
        "tests/test_x.py": ("fff", 500),
    }

    app = catalog.app_from_listing("clock", catalog.Manifest(name="Clock"), entries)

    assert sorted(app.files) == [
        ".env.example",
        "app.py",
        "manifest.yaml",
        "requirements.txt",
    ]
    assert app.size == 200, "the preview and the tests are not counted"
    assert app.requirements == "ccc" and app.needs_packages
    assert app.env_template == ".env.example"


def test_a_program_with_nothing_to_install_says_so() -> None:
    app = catalog.app_from_listing(
        "c", catalog.Manifest(name="C"), {"app.py": ("a", 1)}
    )

    assert not app.needs_packages
    assert app.env_template == ""


def test_the_blob_sha_is_the_one_git_gives() -> None:
    """
    The value for the empty file and for "hello\\n" are git's own, so what a
    listing reports can be compared with what was downloaded.
    """
    assert catalog.git_blob_sha(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert (
        catalog.git_blob_sha(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"
    )


def test_the_sha_is_taken_over_bytes_not_over_text() -> None:
    """
    A file with Windows line endings is a different file to git, and the
    check must see it as one - decode and re-encode would hide the difference.
    """
    assert catalog.git_blob_sha(b"a\r\nb\r\n") != catalog.git_blob_sha(b"a\nb\n")


# The environment a program reads ------------------------------------------------


def test_a_template_becomes_the_variables_a_program_reads() -> None:
    text = (
        "# Get one at example.com/keys\n"
        "# Free tier is fine\n"
        "API_KEY=\n"
        "\n"
        "export CITY=Utrecht  # default\n"
        'QUOTED="two words"\n'
        "API_KEY=ignored-second-time\n"
    )

    found = catalog.parse_env_template(text)

    assert [(v.key, v.example, v.help) for v in found] == [
        ("API_KEY", "", "Get one at example.com/keys Free tier is fine"),
        ("CITY", "Utrecht", ""),
        ("QUOTED", "two words", ""),
    ]


def test_a_comment_separated_by_a_blank_line_is_not_help() -> None:
    found = catalog.parse_env_template("# a heading for the file\n\nKEY=1\n")

    assert found[0].help == ""


def test_a_template_with_nothing_in_it_asks_for_nothing() -> None:
    assert catalog.parse_env_template("# nothing here\n\n") == []
