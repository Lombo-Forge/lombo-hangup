"""A fake Jellyfin and webhook on localhost, so tests need no real server.

The log lines have the shape a real Jellyfin 12.4.0 wrote (media details cut out).
"""

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import pytest


def stamp(ago: float) -> str:
    t = datetime.now(timezone.utc) - timedelta(seconds=ago)  # noqa: UP017
    return t.strftime("[%Y-%m-%d %H:%M:%S.") + f"{t.microsecond // 1000:03d} +00:00] [INF] [6] "


def sid(orig: str) -> str:
    return f"aaaa_bbbb_{orig}"


def started(ago=100_000):
    return stamp(ago) + 'Main: Jellyfin version: "12.4.0"'


def opened(orig, ago=3600):
    body = f'MediaSourceInfo {{ Protocol: Http, Id: "{orig}", LiveStreamId: "{sid(orig)}", BufferMs: null }}'
    return stamp(ago) + "Emby.Server.Implementations.Library.MediaSourceManager: Live stream opened: " + body


def count(orig, n, ago=3600, who="Jellyfin.LiveTv.DefaultLiveTvService"):
    return stamp(ago) + f'{who}: Live stream "{orig}" consumer count is now {n}'


def closed(orig, ago=0):
    who = "Emby.Server.Implementations.Library.MediaSourceManager"
    return stamp(ago) + f'{who}: Closing live stream "{sid(orig)}"'


def player(orig=None, kind="TvChannel", name="TV"):
    state = {"LiveStreamId": sid(orig)} if orig else {}
    return {"DeviceName": name, "NowPlayingItem": {"Type": kind}, "PlayState": state}


class Fake:
    def __init__(self):
        self.requests: list[dict] = []
        self.key = "good-key"
        self.log: list[str] = [started()]
        self.sessions: list[dict] = []
        self.recording = 0
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _reply(self, code, payload=None, text=None):
                data = text.encode() if text is not None else json.dumps({} if payload is None else payload).encode()
                self.send_response(code)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path == "/System/Info/Public":
                    return self._reply(200, {"ServerName": "Fake", "Version": "0.0.0"})
                if self.headers.get("Authorization") != f'MediaBrowser Token="{outer.key}"':
                    return self._reply(401)
                if url.path == "/System/Info":
                    return self._reply(200, {})
                if url.path == "/System/Logs":
                    return self._reply(200, [{"Name": "log_20260101.log"}, {"Name": "FFmpeg.log"}])
                if url.path == "/System/Logs/Log" and parse_qs(url.query)["name"] == ["log_20260101.log"]:
                    return self._reply(200, text="\r\n".join(["noise", *outer.log]) + "\r\n")
                if url.path == "/Sessions":
                    return self._reply(200, outer.sessions)
                if url.path == "/LiveTv/Timers":
                    return self._reply(200, {"Items": [{}] * outer.recording})
                return self._reply(404)

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0) or 0))
                if self.path != "/hook" and self.headers.get("Authorization") != f'MediaBrowser Token="{outer.key}"':
                    return self._reply(401)
                outer.requests.append({"path": self.path, "body": body.decode()})
                return self._reply(204, text="")

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def closes(self):
        return [r["path"].split("=")[1] for r in self.requests if r["path"].startswith("/LiveStreams/Close")]


@pytest.fixture
def fake():
    f = Fake()
    yield f
    f.server.shutdown()


@pytest.fixture
def env(fake):
    return {
        "LOMBO_HANGUP_JELLYFIN_URL": fake.url,
        "LOMBO_HANGUP_JELLYFIN_API_KEY": "good-key",
        "LOMBO_HANGUP_WEBHOOK_URL": fake.url + "/hook",
    }
