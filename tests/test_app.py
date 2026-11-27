import re
import time
from pathlib import Path

import pytest

from conftest import closed, count, opened, player, sid, started
from lombo_hangup import cli, core, notify
from lombo_hangup.cli import main
from lombo_hangup.config import ConfigError, from_env
from lombo_hangup.jellyfin import Jellyfin, JellyfinError

LIVE = {"LOMBO_HANGUP_DRY_RUN": "false"}


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(cli, "CONFIRM_SECONDS", 0)


def found(lines, sessions=(), grace=600):
    return [s.id for s in core.stuck(core.read_log(lines), list(sessions), time.time(), grace)]


def test_a_stream_nobody_plays_is_stuck_and_a_played_one_is_not():
    lines = [opened("one"), opened("two")]
    assert found(lines, [player("two")]) == [sid("one")]


def test_the_older_stream_being_watched_is_left_alone():
    assert found([opened("old", 90_000), opened("new")], [player("old")]) == [sid("new")]


def test_shared_stream_with_one_stuck_viewer():
    lines = [opened("one"), count("one", 2), opened("one")]
    assert found(lines, [player("one")]) == [sid("one")]
    assert found(lines, [player("one"), player("one")]) == []


def test_closed_streams_and_streams_from_before_a_restart_are_forgotten():
    assert found([opened("one"), count("one", 0), closed("one")]) == []
    assert found([opened("one"), started(10)]) == []


def test_a_newcomer_restarts_the_grace_period_but_a_leaver_does_not():
    assert found([opened("one", 3600), count("one", 2, 30), opened("one", 30)]) == []
    assert found([opened("one", 3600), count("one", 2, 3600), opened("one", 3600), count("one", 1, 5)]) == [sid("one")]
    assert found([opened("one", 30)]) == []


def test_text_inside_another_message_is_not_a_stream():
    assert core.read_log(['[2026-01-01 00:00:00.000 +00:00] [INF] [1] Foo: title was "x" ' + opened("one")]) == {}


@pytest.mark.parametrize("kind", ["TvChannel", "Program"])
def test_stand_down_for_recordings_and_players_that_name_no_stream(kind):
    assert "recording" in core.stand_down([], 1)
    assert "without saying" in core.stand_down([player(None, kind)], 0)
    assert core.stand_down([player("one", kind), player(None, "Movie")], 0) is None


def test_plan_and_dry_run_close_nothing(env, fake, capsys):
    fake.log += [opened("one")]
    assert main(["plan"], {**env, **LIVE}) == 0
    assert main(["run"], env) == 0
    assert "would close one viewer of stream one" in capsys.readouterr().out
    assert fake.requests == []


def test_live_run_closes_the_stuck_one_and_says_so(env, fake):
    fake.log += [opened("one"), opened("two")]
    fake.sessions = [player("two")]
    assert main(["run"], {**env, **LIVE}) == 0
    assert fake.closes() == [sid("one")]
    assert fake.requests[-1]["path"] == "/hook"


@pytest.mark.parametrize("change", ["recording", "silent player"])
def test_live_run_stands_down(env, fake, change, capsys):
    fake.log += [opened("one")]
    if change == "recording":
        fake.recording = 1
    else:
        fake.sessions = [player(None)]
    assert main(["run"], {**env, **LIVE}) == 0
    assert "standing down" in capsys.readouterr().out
    assert fake.closes() == []


@pytest.mark.parametrize("event", ["player appears", "recording starts", "someone joins"])
def test_anything_changing_before_the_second_look_closes_nothing(env, fake, monkeypatch, event):
    fake.log += [opened("one")]

    def during(_seconds):
        if event == "player appears":
            fake.sessions = [player("one")]
        elif event == "recording starts":
            fake.recording = 1
        else:
            fake.log += [count("one", 2, 0), opened("one", 0)]

    monkeypatch.setattr(cli.time, "sleep", during)
    assert main(["run"], {**env, **LIVE}) == 0
    assert fake.closes() == []


def test_nothing_open_asks_nothing_more(env, fake, capsys):
    assert main(["run"], {**env, **LIVE}) == 0
    assert "Nothing stuck (0 live stream(s) open)" in capsys.readouterr().out


def test_doctor_passes_warns_and_fails(env, fake, capsys):
    assert main(["doctor"], env) == 0
    assert "[WARN]" not in capsys.readouterr().out
    fake.log = []
    assert main(["doctor"], env) == 0
    assert "log level" in capsys.readouterr().out
    assert main(["doctor"], {**env, "LOMBO_HANGUP_JELLYFIN_API_KEY": "wrong"}) == 1


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("JELLYFIN_URL", "jellyfin:8096"),
        ("JELLYFIN_API_KEY", "changeme"),
        ("WEBHOOK_URL", "ftp://x"),
        ("INTERVAL_SECONDS", "5"),
        ("GRACE_SECONDS", "10"),
        ("GRACE_SECONDS", "soon"),
        ("DRY_RUN", "treu"),
    ],
)
def test_config_rejects_bad_values_and_names_the_setting(env, name, value):
    with pytest.raises(ConfigError, match=f"LOMBO_HANGUP_{name}"):
        from_env({**env, f"LOMBO_HANGUP_{name}": value})


def test_defaults_are_safe_and_env_example_is_complete(env):
    cfg = from_env(env)
    assert (cfg.dry_run, cfg.interval_seconds, cfg.grace_seconds) == (True, 300, 600)
    root = Path(__file__).parent.parent
    listed = set(re.findall(r"^LOMBO_HANGUP_(\w+)=", (root / ".env.example").read_text(), re.M))
    config = (root / "src/lombo_hangup/config.py").read_text()
    assert listed == set(re.findall(r'(?:get|seconds)\("([A-Z_]+)"', config))


def test_failures_are_messages(env, fake, capsys):
    assert main(["plan"], {}) == 2
    assert main(["run"], {**env, "LOMBO_HANGUP_JELLYFIN_URL": "http://127.0.0.1:1"}) == 1
    assert "[FAIL]" in capsys.readouterr().err
    with pytest.raises(JellyfinError, match="HTTP 401"):
        Jellyfin(fake.url, "wrong").close("x")
    notify.send(fake.url + "/hook", "hello")
    with pytest.raises(notify.NotifyError):
        notify.send("http://127.0.0.1:1/hook", "x", timeout=1)
