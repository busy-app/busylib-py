from __future__ import annotations

import json

import pytest

from apps_support import BRANCH, RAW, TREE, CatalogNet, manifest_bytes, program

from examples.apps.github import Cache, GitHub, Reply
from examples.apps.model import Asset, ManagerError, Source, Version

MANIFEST = json.dumps({"id": "demo.app", "name": "Demo", "version": "1.2.0"}).encode()


class _Net:
    """
    A GitHub that answers from a table and remembers what it was asked.
    """

    def __init__(self, routes: dict[str, Reply | object]) -> None:
        self.routes = routes
        self.asked: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str], limit: int) -> Reply:
        self.asked.append((url, headers))
        answer = self.routes.get(url, Reply(404))
        if isinstance(answer, Reply):
            return answer
        return Reply(200, json.dumps(answer).encode())


def _release(tag: str, *files: str, **extra: object) -> dict[str, object]:
    return {
        "tag_name": tag,
        "name": f"Release {tag}",
        "published_at": "2026-09-30T10:00:00Z",
        "assets": [
            {
                "name": name,
                "browser_download_url": f"https://dl/{tag}/{name}",
                "size": 10,
            }
            for name in files
        ],
    } | extra


SOURCE = Source(repo="busy-app/demo")
RELEASES = "https://api.github.com/repos/busy-app/demo/releases?per_page=30"


def test_releases_with_a_package_are_the_versions() -> None:
    net = _Net(
        {
            RELEASES: [
                _release("v1.1.0", "demo.tgz", "notes.txt"),
                _release("v1.0.0", "demo.tgz", prerelease=True),
            ]
        }
    )

    versions = GitHub(net, token="").versions(SOURCE)

    assert [(v.ref, v.prerelease) for v in versions] == [
        ("v1.1.0", False),
        ("v1.0.0", True),
    ]
    assert versions[0].asset == Asset("demo.tgz", "https://dl/v1.1.0/demo.tgz", 10)
    assert versions[0].published == "2026-09-30"


def test_a_release_without_the_package_is_not_offered() -> None:
    net = _Net(
        {RELEASES: [_release("v2", "source-only.zip"), _release("v1", "demo.tgz")]}
    )

    assert [v.ref for v in GitHub(net, token="").versions(SOURCE)] == ["v1"]


def test_drafts_are_not_versions() -> None:
    net = _Net(
        {RELEASES: [_release("v2", "demo.tgz", draft=True), _release("v1", "demo.tgz")]}
    )

    assert [v.ref for v in GitHub(net, token="").versions(SOURCE)] == ["v1"]


def test_a_repository_with_nothing_to_install_says_how_to_fix_it() -> None:
    net = _Net({RELEASES: []})

    with pytest.raises(
        ManagerError, match="no release with a file matching '\\*.tgz'.*build source"
    ):
        GitHub(net, token="").versions(SOURCE)


def test_the_package_file_is_picked_by_the_sources_pattern() -> None:
    net = _Net({RELEASES: [_release("v1", "demo-linux.tar.gz", "demo.tgz")]})
    source = Source(repo="busy-app/demo", asset="*.tar.gz")

    (version,) = GitHub(net, token="").versions(source)

    assert version.asset is not None and version.asset.name == "demo-linux.tar.gz"


def test_a_build_source_offers_the_default_branch_then_the_tags() -> None:
    net = _Net(
        {
            "https://api.github.com/repos/busy-app/demo": {"default_branch": "trunk"},
            "https://api.github.com/repos/busy-app/demo/tags?per_page=30": [
                {"name": "v1.1.0"},
                {"name": "v1.0.0"},
            ],
        }
    )

    versions = GitHub(net, token="").versions(
        Source(repo="busy-app/demo", mode="build")
    )

    assert [(v.ref, v.kind) for v in versions] == [
        ("trunk", "branch"),
        ("v1.1.0", "tag"),
        ("v1.0.0", "tag"),
    ]


@pytest.mark.parametrize("repo", ["demo", "a/b/c", "has space/x", "../x"])
def test_something_that_is_not_a_repository_is_refused_before_asking(repo: str) -> None:
    net = _Net({})

    with pytest.raises(ManagerError, match="not an owner/name repository"):
        GitHub(net, token="").versions(Source(repo=repo))

    assert net.asked == []


def test_a_missing_repository_asks_whether_it_is_public() -> None:
    with pytest.raises(ManagerError, match="public"):
        GitHub(_Net({}), token="").versions(SOURCE)


def test_the_rate_limit_is_explained_not_reported_as_a_failure() -> None:
    net = _Net(
        {
            RELEASES: Reply(
                403,
                headers={
                    "x-ratelimit-remaining": "0",
                    "x-ratelimit-reset": "1893456000",
                },
            )
        }
    )

    with pytest.raises(ManagerError, match="request limit is used up.*GITHUB_TOKEN"):
        GitHub(net, token="").versions(SOURCE)


def test_the_token_goes_to_the_api_and_nowhere_else() -> None:
    """
    A release file is served from another host, via a redirect, and a token
    sent along with it would be handed to that host.
    """
    net = _Net(
        {
            RELEASES: [_release("v1", "demo.tgz")],
            "https://dl/v1/demo.tgz": Reply(200, b"package"),
        }
    )
    github = GitHub(net, token="secret")

    (version,) = github.versions(SOURCE)
    github.release_package(version)

    api_headers = net.asked[0][1]
    download_headers = net.asked[1][1]
    assert api_headers["Authorization"] == "Bearer secret"
    assert "Authorization" not in download_headers


def test_a_manifest_is_found_where_the_defaults_look() -> None:
    net = _Net(
        {
            "https://raw.githubusercontent.com/busy-app/demo/v1/src/appmeta/manifest.json": Reply(
                200, MANIFEST
            )
        }
    )

    manifest = GitHub(net, token="").manifest(SOURCE, "v1")

    assert manifest is not None and (manifest.id, manifest.version) == (
        "demo.app",
        "1.2.0",
    )


def test_a_manifest_falls_back_to_the_built_layout() -> None:
    net = _Net(
        {
            "https://raw.githubusercontent.com/busy-app/demo/v1/appmeta/manifest.json": Reply(
                200, MANIFEST
            )
        }
    )

    assert GitHub(net, token="").manifest(SOURCE, "v1") is not None


def test_a_manifest_in_a_monorepo_is_read_from_its_folder() -> None:
    net = _Net(
        {
            "https://raw.githubusercontent.com/busy-app/demo/v1/apps/clock/custom/manifest.json": Reply(
                200, MANIFEST
            )
        }
    )
    source = Source(
        repo="busy-app/demo", subdir="apps/clock", manifest="custom/manifest.json"
    )

    assert GitHub(net, token="").manifest(source, "v1") is not None


def test_no_manifest_is_none_rather_than_an_error() -> None:
    """
    It only decorates the list; a source that keeps its manifest somewhere
    unexpected should still be installable.
    """
    assert GitHub(_Net({}), token="").manifest(SOURCE, "v1") is None


def test_a_manifest_that_is_not_one_is_skipped() -> None:
    net = _Net(
        {
            "https://raw.githubusercontent.com/busy-app/demo/v1/src/appmeta/manifest.json": Reply(
                200, b"<html>nope</html>"
            ),
            "https://raw.githubusercontent.com/busy-app/demo/v1/appmeta/manifest.json": Reply(
                200, MANIFEST
            ),
        }
    )

    manifest = GitHub(net, token="").manifest(SOURCE, "v1")

    assert manifest is not None and manifest.id == "demo.app"


def test_a_release_package_is_downloaded_from_its_asset() -> None:
    net = _Net({"https://dl/v1/demo.tgz": Reply(200, b"package bytes")})
    version = Version(
        "v1", "v1", "release", Asset("demo.tgz", "https://dl/v1/demo.tgz")
    )

    assert GitHub(net, token="").release_package(version) == b"package bytes"


def test_a_source_archive_comes_from_codeload() -> None:
    net = _Net(
        {"https://codeload.github.com/busy-app/demo/tar.gz/v1.0": Reply(200, b"src")}
    )

    assert GitHub(net, token="").source_archive(SOURCE, "v1.0") == b"src"


def test_a_manifest_path_that_climbs_out_of_the_repository_is_not_followed() -> None:
    net = _Net({})
    source = Source(repo="busy-app/demo", subdir="../../other/repo")

    assert GitHub(net, token="").manifest(source, "v1") is None
    assert net.asked == []


# Catalogs ----------------------------------------------------------------------


CATALOG = Source(repo="busy-app/programs", kind="catalog")


def test_a_catalog_is_the_programs_in_its_apps_folder() -> None:
    net = CatalogNet({"clock": program("Clock"), "weather": program("Weather")})

    found = GitHub(net, token="").catalog(CATALOG)

    assert [a.slug for a in found.apps] == ["clock", "weather"]
    assert found.commit == "c0ffee" and found.branch == "main"
    assert found.apps[0].manifest.description == "About Clock"
    assert sorted(found.apps[0].files) == ["app.py", "manifest.yaml"]


def test_the_cards_are_in_name_order_whatever_order_the_listing_came_in() -> None:
    net = CatalogNet({"z": program("Alpha"), "a": program("zulu")})

    assert [a.name for a in GitHub(net, token="").catalog(CATALOG).apps] == [
        "Alpha",
        "zulu",
    ]


def test_asking_again_costs_two_cheap_requests_and_no_downloads() -> None:
    """
    The listing comes back as a 304, which GitHub does not count against the
    hourly limit, and every manifest is already known by its blob sha.
    """
    net = CatalogNet({"clock": program("Clock"), "weather": program("Weather")})
    cache = Cache()
    GitHub(net, token="", cache=cache).catalog(CATALOG)
    net.asked.clear()

    def revalidating(url: str, headers: dict[str, str], limit: int) -> Reply:
        net.asked.append((url, "If-None-Match" in headers))
        if "If-None-Match" in headers and url in (BRANCH, TREE):
            return Reply(304)
        return net(url, headers, limit)

    again = GitHub(revalidating, token="", cache=cache).catalog(CATALOG)

    assert [a.slug for a in again.apps] == ["clock", "weather"]
    api = [
        asked for asked in net.asked if asked[0].startswith("https://api.github.com")
    ]
    raw = [asked for asked in net.asked if asked[0].startswith(RAW)]
    assert [sent for _, sent in api[-2:]] == [True, True]
    assert raw == [], "nothing is downloaded that was seen before"


def test_the_cache_survives_a_restart(tmp_path) -> None:
    net = CatalogNet({"clock": program("Clock")})
    GitHub(net, token="", cache=Cache(tmp_path / "cache.json")).catalog(CATALOG)

    revived = Cache(tmp_path / "cache.json")

    assert BRANCH in revived.responses and revived.blobs


def test_a_cache_that_cannot_be_read_is_just_empty(tmp_path) -> None:
    (tmp_path / "cache.json").write_text("{ not json")

    cache = Cache(tmp_path / "cache.json")

    assert (cache.responses, cache.blobs) == ({}, {})


def test_a_cache_does_not_grow_without_end(tmp_path) -> None:
    cache = Cache(tmp_path / "cache.json")
    for number in range(Cache.LIMIT + 50):
        cache.blobs[f"sha{number}"] = "x"
    cache.save()

    kept = Cache(tmp_path / "cache.json")

    assert len(kept.blobs) == Cache.LIMIT
    assert "sha0" not in kept.blobs and f"sha{Cache.LIMIT + 49}" in kept.blobs


def test_one_unreadable_manifest_costs_one_card_not_the_catalog() -> None:
    net = CatalogNet(
        {
            "good": program("Good"),
            "broken": {"app.py": b"x", "manifest.yaml": b"name: X\n  nested: 1\n"},
            "no-name": {"app.py": b"x", "manifest.yaml": b"author: me\n"},
        }
    )

    found = GitHub(net, token="").catalog(CATALOG)

    assert [a.slug for a in found.apps] == ["good"]
    assert set(found.problems) == {"broken", "no-name"}
    assert "not readable" in found.problems["broken"]


def test_a_folder_without_a_program_in_it_is_reported_not_listed() -> None:
    net = CatalogNet({"docs-only": {"manifest.yaml": manifest_bytes("Docs")}})

    found = GitHub(net, token="").catalog(CATALOG)

    assert found.apps == ()
    assert "no app.py" in found.problems["docs-only"]


@pytest.mark.parametrize("slug", ["Has Space", "UPPER", "-lead", "a" * 80])
def test_a_folder_name_that_could_not_be_installed_safely_is_skipped(slug: str) -> None:
    net = CatalogNet({slug: program("X"), "fine": program("Fine")})

    found = GitHub(net, token="").catalog(CATALOG)

    assert [a.slug for a in found.apps] == ["fine"]
    assert slug in found.problems


def test_a_manifest_that_is_not_the_file_the_listing_named_is_not_trusted() -> None:
    """
    The listing names each file by its content; bytes that do not match are
    something else - a cache, a proxy - and must not become a card.
    """
    net = CatalogNet({"clock": program("Clock")})
    real = net.__call__

    def tampered(url: str, headers: dict[str, str], limit: int) -> Reply:
        if url.endswith("/apps/clock/manifest.yaml"):
            return Reply(200, manifest_bytes("Something else"))
        return real(url, headers, limit)

    found = GitHub(tampered, token="").catalog(CATALOG)

    assert found.apps == () and "did not match" in found.problems["clock"]


def test_a_branch_that_does_not_exist_is_said_plainly() -> None:
    with pytest.raises(ManagerError, match="was not found"):
        GitHub(lambda url, headers, limit: Reply(404), token="").catalog(CATALOG)


def test_a_listing_that_github_cut_short_is_refused() -> None:
    net = CatalogNet({"clock": program("Clock")})
    real = net.__call__

    def truncated(url: str, headers: dict[str, str], limit: int) -> Reply:
        if url == TREE:
            return Reply(200, json.dumps({"truncated": True, "tree": []}).encode())
        return real(url, headers, limit)

    with pytest.raises(ManagerError, match="too large"):
        GitHub(truncated, token="").catalog(CATALOG)


def test_a_catalog_names_its_branch_when_it_is_not_main() -> None:
    asked: list[str] = []

    def spy(url: str, headers: dict[str, str], limit: int) -> Reply:
        asked.append(url)
        return Reply(404)

    with pytest.raises(ManagerError):
        GitHub(spy, token="").catalog(
            Source(repo="busy-app/programs", kind="catalog", branch="next")
        )

    assert asked == ["https://api.github.com/repos/busy-app/programs/branches/next"]
