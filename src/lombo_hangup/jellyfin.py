"""A small Jellyfin client, standard library only. Add the calls your app needs here.

Authentication uses an API key (Jellyfin: Dashboard > API Keys) in the Authorization header.
Every failure becomes a JellyfinError with a short message, so callers print it instead of crashing.
"""

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any, cast


class JellyfinError(Exception):
    """A request failed. The message names the path and the reason."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """urllib would turn a redirected POST into a GET (nothing closed, no error) and resend the key."""

    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None


_opener = urllib.request.build_opener(_NoRedirect)
LOG_NAME = re.compile(r"log_\d{8}(_\d+)?\.log")


class Jellyfin:
    def __init__(self, base_url: str, api_key: str, timeout: float = 10):
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.timeout = timeout

    def _open(self, path: str, auth: bool = True, method: str = "GET") -> Any:
        # S310 is silenced: config.py only accepts http(s) URLs.
        req = urllib.request.Request(self.base + path, method=method)  # noqa: S310
        if auth:
            req.add_header("Authorization", f'MediaBrowser Token="{self.key}"')
        try:
            return _opener.open(req, timeout=self.timeout)
        except urllib.error.HTTPError as e:
            raise JellyfinError(f"{path}: HTTP {e.code}") from e
        except (urllib.error.URLError, OSError) as e:
            raise JellyfinError(f"{path}: {e}") from e

    def _get(self, path: str, auth: bool = True) -> Any:
        try:
            with self._open(path, auth) as resp:
                return json.load(resp)
        except (OSError, ValueError) as e:
            raise JellyfinError(f"{path}: {e}") from e

    def public_info(self) -> dict[str, Any]:
        """Server name and version. Needs no key, so it tells 'unreachable' apart from 'bad key'."""
        return cast(dict[str, Any], self._get("/System/Info/Public", auth=False))

    def info(self) -> dict[str, Any]:
        """Needs a valid key."""
        return cast(dict[str, Any], self._get("/System/Info"))

    def sessions(self) -> list[dict[str, Any]]:
        return cast(list[dict[str, Any]], self._get("/Sessions"))

    def recordings(self) -> int:
        """Recordings running now."""
        return len(self._get("/LiveTv/Timers?isActive=true").get("Items") or [])

    def log_lines(self) -> Iterator[str]:
        """The live stream and start-up lines of the newest server logs, oldest first."""
        names = sorted(f["Name"] for f in self._get("/System/Logs") if LOG_NAME.fullmatch(f["Name"]))
        for name in names[-3:]:
            path = "/System/Logs/Log?" + urllib.parse.urlencode({"name": name})
            try:
                with self._open(path) as resp:
                    for raw in resp:
                        if b"ive stream" in raw or b"Jellyfin version" in raw:
                            yield raw.decode("utf-8", "replace").rstrip()
            except OSError as e:
                raise JellyfinError(f"{path}: {e}") from e

    def close(self, live_stream_id: str) -> None:
        """Removes ONE viewer from the stream; Jellyfin closes it when none are left."""
        path = "/LiveStreams/Close?" + urllib.parse.urlencode({"liveStreamId": live_stream_id})
        with self._open(path, method="POST"):
            pass
