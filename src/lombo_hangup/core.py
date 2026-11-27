"""The decisions. Pure: no network, no disk, no clock, so tests need no fakes.

Jellyfin has no call that lists open live streams, so they are rebuilt from its log, including how
many viewers each one counts. A stream is stuck when it counts more viewers than there are players
reporting its id. Anything that makes that unsure means nothing is closed.
"""

import re
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# Anchored at the start of the line, so text inside some other message cannot pose as one of these.
_HEAD = r"^\[(?P<at>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+ [+-]\d\d:\d\d)\] \[[A-Z]{3}\] \[\d+\] "
_START = re.compile(_HEAD + r"Main: Jellyfin version:")
_OPEN = re.compile(
    _HEAD + r'\S+MediaSourceManager: Live stream opened: MediaSourceInfo \{.*\bLiveStreamId: "(?P<id>\w+)"'
)
_COUNT = re.compile(_HEAD + r'\S+: Live stream "(?P<orig>\w+)" consumer count is now (?P<n>\d+)')
_CLOSE = re.compile(_HEAD + r'\S+MediaSourceManager: Closing live stream "(?P<id>\w+)"')

LIVE_TYPES = {"TvChannel", "Program", "LiveTvChannel", "LiveTvProgram"}


@dataclass
class Stream:
    id: str = ""  # the full LiveStreamId; empty until the "opened" line
    viewers: int = 1
    joined: float = 0.0  # when the newest viewer arrived


def _time(match: re.Match[str]) -> float:
    return datetime.strptime(match["at"], "%Y-%m-%d %H:%M:%S.%f %z").timestamp()


def read_log(lines: Iterable[str]) -> dict[str, Stream]:
    """{short stream id: Stream} for what is open at the end of these lines (oldest first)."""
    streams: dict[str, Stream] = {}
    for line in lines:
        if _START.match(line):
            streams.clear()  # a restart drops every stream without saying so
        elif m := _OPEN.match(line):
            s = streams.setdefault(m["id"].rsplit("_", 1)[-1], Stream())
            s.id, s.joined = m["id"], _time(m)
        elif m := _COUNT.match(line):
            s = streams.setdefault(m["orig"], Stream())
            if int(m["n"]) > s.viewers:
                s.joined = _time(m)
            s.viewers = int(m["n"])
        elif m := _CLOSE.match(line):
            streams.pop(m["id"].rsplit("_", 1)[-1], None)
    return {k: v for k, v in streams.items() if v.id and v.viewers > 0}


def stand_down(sessions: Sequence[Mapping[str, Any]], recordings: int) -> str | None:
    """Why nothing may be closed right now, or None."""
    if recordings:
        return f"{recordings} recording(s) running: a recording holds a stream with no player"
    for s in sessions:
        item = s.get("NowPlayingItem") or {}
        if item.get("Type") in LIVE_TYPES and not (s.get("PlayState") or {}).get("LiveStreamId"):
            name = s.get("DeviceName") or "a player"
            return f"{name} is playing live TV without saying which stream"
    return None


def stuck(
    streams: Mapping[str, Stream], sessions: Sequence[Mapping[str, Any]], now: float, grace: float
) -> list[Stream]:
    """Streams counting more viewers than the players reporting them, with nobody new for `grace` seconds."""
    players = Counter((s.get("PlayState") or {}).get("LiveStreamId") for s in sessions)
    return sorted(
        (s for s in streams.values() if s.viewers > players[s.id] and now - s.joined >= grace), key=lambda s: s.id
    )
