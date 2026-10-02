"""
Finding versions of an application on GitHub, and getting them.

Only the standard library, on purpose: the manager is something a person
runs on whatever computer they have, and every package it needs is one more
thing that can fail to install. Public repositories only - a private one
would need the token carried across a redirect to a different host, which
is exactly the thing not to do quietly.
"""

from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import catalog, package
from .model import (
    MAX_PACKAGE_BYTES,
    REPO,
    AppManifest,
    Asset,
    ManagerError,
    Source,
    Version,
)

API = "https://api.github.com"
RAW = "https://raw.githubusercontent.com"
CODELOAD = "https://codeload.github.com"
USER_AGENT = "busylib-apps-example"

# A source archive can be big, and the limit is for the download, not the app.
MAX_SOURCE_BYTES = 200 * 1024 * 1024


@dataclass
class Reply:
    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


Fetch = Callable[[str, dict[str, str], int], Reply]


def urllib_fetch(url: str, headers: dict[str, str], limit: int) -> Reply:
    """
    One GET, with a size cap, never raising for an HTTP status.
    """
    request = Request(url, headers=headers)
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read(limit + 1)
            if len(body) > limit:
                raise ManagerError(
                    f"{url} is larger than {limit // (1024 * 1024)} MiB, "
                    "which is more than this should download"
                )
            return Reply(
                response.status,
                body,
                {key.lower(): value for key, value in response.headers.items()},
            )
    except HTTPError as err:
        return Reply(
            err.code,
            err.read(64 * 1024),
            {key.lower(): value for key, value in err.headers.items()},
        )
    except URLError as err:
        raise ManagerError(f"cannot reach GitHub: {err.reason}") from err
    except TimeoutError as err:
        raise ManagerError("GitHub did not answer in time") from err


class Cache:
    """
    What GitHub already told us, kept between runs.

    Two kinds of thing. A response comes with an ETag, and asking again with
    it gets a 304 that does not count against the hourly limit - which is what
    makes opening a catalog on every start affordable. A file is named by its
    blob sha, so it can never be stale and is kept for good.
    """

    LIMIT = 300

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.responses: dict[str, dict[str, str]] = {}
        self.blobs: dict[str, str] = {}
        if path is not None:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self.responses = dict(data.get("responses", {}))
                self.blobs = dict(data.get("blobs", {}))
            except (OSError, ValueError, AttributeError):
                # A cache is allowed to be lost; it is not allowed to be fatal.
                self.responses, self.blobs = {}, {}

    def save(self) -> None:
        if self.path is None:
            return
        # Newest last, so trimming from the front drops the oldest.
        for table in (self.responses, self.blobs):
            for key in list(table)[: max(0, len(table) - self.LIMIT)]:
                del table[key]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps({"responses": self.responses, "blobs": self.blobs}),
                encoding="utf-8",
            )
            os.replace(temporary, self.path)
        except OSError:
            pass


class GitHub:
    """
    The few questions the manager asks GitHub.
    """

    def __init__(
        self,
        fetch: Fetch = urllib_fetch,
        token: str | None = None,
        cache: Cache | None = None,
    ) -> None:
        self.fetch = fetch
        self.cache = cache or Cache()
        # Raises the 60-requests-an-hour limit for anonymous calls. Read from
        # the environment because that is where people already keep it.
        self.token = token if token is not None else os.environ.get("GITHUB_TOKEN")

    # Plumbing ----------------------------------------------------------

    def _api(self, path: str) -> object:
        url = f"{API}{path}"
        headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
        if self.token:
            # Only ever to the API host. A download is sent to another host
            # by a redirect, and a token must not follow it.
            headers["Authorization"] = f"Bearer {self.token}"
        remembered = self.cache.responses.get(url)
        if remembered:
            headers["If-None-Match"] = remembered["etag"]

        reply = self.fetch(url, headers, 8 * 1024 * 1024)
        if reply.status == 304 and remembered:
            body = remembered["body"].encode()
        else:
            self._check(reply, path)
            body = reply.body
            etag = reply.headers.get("etag")
            if etag:
                self.cache.responses.pop(url, None)  # to the newest end
                self.cache.responses[url] = {
                    "etag": etag,
                    "body": body.decode("utf-8", errors="replace"),
                }
        try:
            return json.loads(body)
        except ValueError as err:
            raise ManagerError(
                f"GitHub sent something that is not JSON for {path}"
            ) from err

    @staticmethod
    def _check(reply: Reply, what: str) -> None:
        if reply.status < 400:
            return
        if (
            reply.status in (403, 429)
            and reply.headers.get("x-ratelimit-remaining") == "0"
        ):
            when = ""
            reset = reply.headers.get("x-ratelimit-reset")
            if reset and reset.isdigit():
                when = f" until {time.strftime('%H:%M', time.localtime(int(reset)))}"
            raise ManagerError(
                f"GitHub's anonymous request limit is used up{when}. "
                "Set GITHUB_TOKEN to raise it, or wait."
            )
        if reply.status == 404:
            raise ManagerError(f"{what} was not found (is the repository public?)")
        raise ManagerError(f"GitHub answered {reply.status} for {what}")

    def _download(self, url: str, limit: int) -> bytes:
        reply = self.fetch(url, {"User-Agent": USER_AGENT}, limit)
        self._check(reply, url)
        return reply.body

    # Questions ---------------------------------------------------------

    def versions(self, source: Source) -> list[Version]:
        """
        What can be installed from a source, newest first.

        For a release source that is the releases which carry a package.
        For a build source it is the default branch followed by the tags -
        a release does not have to exist for a version to be built.
        """
        if not REPO.match(source.repo):
            raise ManagerError(f"{source.repo!r} is not an owner/name repository")

        if source.mode == "release":
            found: list[Version] = []
            releases = self._api(f"/repos/{source.repo}/releases?per_page=30")
            for release in releases if isinstance(releases, list) else []:
                if release.get("draft"):
                    continue
                asset = next(
                    (
                        Asset(
                            a["name"], a["browser_download_url"], int(a.get("size", 0))
                        )
                        for a in release.get("assets", [])
                        if package.matches(a.get("name", ""), source.asset)
                    ),
                    None,
                )
                if asset is None:
                    continue
                found.append(
                    Version(
                        ref=release["tag_name"],
                        label=release.get("name") or release["tag_name"],
                        kind="release",
                        asset=asset,
                        published=(release.get("published_at") or "")[:10],
                        prerelease=bool(release.get("prerelease")),
                    )
                )
            if not found:
                raise ManagerError(
                    f"{source.repo} has no release with a file matching {source.asset!r}. "
                    "Add it as a build source, or change the file pattern."
                )
            return found

        repository = self._api(f"/repos/{source.repo}")
        default = (
            repository.get("default_branch", "main")
            if isinstance(repository, dict)
            else "main"
        )
        versions = [Version(ref=default, label=f"{default} (latest)", kind="branch")]
        tags = self._api(f"/repos/{source.repo}/tags?per_page=30")
        for tag in tags if isinstance(tags, list) else []:
            versions.append(Version(ref=tag["name"], label=tag["name"], kind="tag"))
        return versions

    def manifest(self, source: Source, ref: str) -> AppManifest | None:
        """
        The application's manifest as it is at `ref`, or None if there is none.

        Used to show a name and a version before anything is downloaded, so
        a failure here is never an error: the source may simply keep its
        manifest somewhere the defaults do not look.
        """
        prefix = f"{source.subdir.strip('/')}/" if source.subdir else ""
        candidates = (
            [source.manifest] if source.manifest else list(package.SOURCE_MANIFESTS)
        )
        # A path typed into a form that climbs out of the repository would
        # read some other repository's file under this one's name.
        if any(".." in PurePosixPath(part).parts for part in (prefix, *candidates)):
            return None
        for candidate in candidates:
            url = f"{RAW}/{source.repo}/{quote(ref)}/{prefix}{candidate}"
            try:
                reply = self.fetch(url, {"User-Agent": USER_AGENT}, 256 * 1024)
            except ManagerError:
                return None
            if reply.status != 200:
                continue
            try:
                return package.parse_manifest(reply.body)
            except ManagerError:
                continue
        return None

    def release_package(self, version: Version) -> bytes:
        if version.asset is None:
            raise ManagerError(f"{version.label} has no package attached")
        return self._download(version.asset.url, MAX_PACKAGE_BYTES)

    def source_archive(self, source: Source, ref: str) -> bytes:
        return self._download(
            f"{CODELOAD}/{source.repo}/tar.gz/{quote(ref)}", MAX_SOURCE_BYTES
        )

    # Catalogs ----------------------------------------------------------

    def raw(
        self, repo: str, ref: str, path: str, limit: int = 8 * 1024 * 1024
    ) -> bytes:
        """
        One file of a repository at a commit, from the host that serves files
        without counting requests against the API's limit.
        """
        return self._download(f"{RAW}/{repo}/{quote(ref)}/{quote(path)}", limit)

    def catalog(self, source: Source) -> catalog.Catalog:
        """
        The programs a catalog repository holds, as of its branch's newest
        commit.

        Two API calls for the listing (a branch, then its tree) and one raw
        fetch per manifest - none for a manifest seen before, since a file is
        named by its blob sha. A manifest that cannot be read costs that
        program's card and is reported; it does not cost the catalog.
        """
        if not REPO.match(source.repo):
            raise ManagerError(f"{source.repo!r} is not an owner/name repository")
        branch = source.branch or "main"
        head = self._api(f"/repos/{source.repo}/branches/{quote(branch, safe='')}")
        commit = head.get("commit", {}).get("sha") if isinstance(head, dict) else None
        if not isinstance(commit, str):
            raise ManagerError(f"{source.repo} has no branch {branch!r}")

        listing = self._api(f"/repos/{source.repo}/git/trees/{commit}?recursive=1")
        if not isinstance(listing, dict):
            raise ManagerError(f"GitHub did not list {source.repo}")
        if listing.get("truncated"):
            raise ManagerError(
                f"{source.repo} is too large for GitHub to list in one go"
            )

        folders: dict[str, dict[str, tuple[str, int]]] = {}
        for entry in listing.get("tree", []):
            if entry.get("type") != "blob":
                continue
            parts = str(entry.get("path", "")).split("/", 2)
            if len(parts) == 3 and parts[0] == "apps":
                folders.setdefault(parts[1], {})[parts[2]] = (
                    str(entry["sha"]),
                    int(entry.get("size", 0)),
                )

        problems: dict[str, str] = {}

        def card(slug: str) -> catalog.CatalogApp | None:
            entries = folders[slug]
            if not catalog.SLUG.match(slug):
                problems[slug] = "not a folder name this can install"
                return None
            if "manifest.yaml" not in entries or "app.py" not in entries:
                problems[slug] = "has no app.py and manifest.yaml"
                return None
            sha = entries["manifest.yaml"][0]
            text = self.cache.blobs.get(sha)
            try:
                if text is None:
                    data = self.raw(
                        source.repo, commit, f"apps/{slug}/manifest.yaml", 256 * 1024
                    )
                    if catalog.git_blob_sha(data) != sha:
                        problems[slug] = "its manifest did not match the listing"
                        return None
                    text = data.decode("utf-8-sig", errors="replace")
                    self.cache.blobs[sha] = text
                manifest = catalog.parse_manifest(text)
            except ManagerError as err:
                problems[slug] = str(err)
                return None
            return catalog.app_from_listing(slug, manifest, entries)

        with ThreadPoolExecutor(max_workers=8) as pool:
            cards = list(pool.map(card, sorted(folders)))
        self.cache.save()

        apps = sorted((app for app in cards if app), key=lambda app: app.name.lower())
        return catalog.Catalog(
            repo=source.repo,
            branch=branch,
            commit=commit,
            apps=tuple(apps),
            problems=problems,
        )
