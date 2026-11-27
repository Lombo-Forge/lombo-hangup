"""Command line: doctor, plan, run. Talks to the outside world; core.py decides.

lombo-hangup doctor        check the settings, Jellyfin and that its log can be read; exit 1 on any failure
lombo-hangup plan          show which streams look stuck; changes nothing, ever
lombo-hangup run [--loop]  close them (only when DRY_RUN=false); --loop repeats every INTERVAL_SECONDS
"""

import argparse
import os
import sys
import time
from collections.abc import Callable

from . import __version__, core, notify
from .config import Config, ConfigError, from_env
from .jellyfin import Jellyfin, JellyfinError

CONFIRM_SECONDS = 30.0  # a second look before closing, so one odd moment closes nothing


def look(cfg: Config, jf: Jellyfin) -> tuple[list[core.Stream], str | None, int]:
    """(stuck streams, why nothing may be closed, open streams). The log is read first, players after it,
    so a viewer who joins in between is still seen."""
    streams = core.read_log(jf.log_lines())
    if not streams:
        return [], None, 0
    sessions = jf.sessions()
    why = core.stand_down(sessions, jf.recordings())
    return core.stuck(streams, sessions, time.time(), cfg.grace_seconds), why, len(streams)


def _label(s: core.Stream) -> str:
    return f"stream {s.id.rsplit('_', 1)[-1]} ({s.viewers} viewer(s) counted)"


def run_once(cfg: Config, change: bool) -> int:
    """One round. change=False (plan, or dry run) closes and alerts nothing."""
    jf = Jellyfin(cfg.jellyfin_url, cfg.jellyfin_api_key)
    found, why, total = look(cfg, jf)
    if why:
        print(f"standing down: {why}")
        return 0
    if not found:
        print(f"Nothing stuck ({total} live stream(s) open).")
        return 0
    if not change:
        for s in found:
            print(f"would close one viewer of {_label(s)}")
        return 0
    time.sleep(CONFIRM_SECONDS)
    again, why, _ = look(cfg, jf)
    if why:
        print(f"standing down: {why}")
        return 0
    first = {(s.id, s.viewers, s.joined) for s in found}
    done = [s for s in again if (s.id, s.viewers, s.joined) in first]  # unchanged between the two looks
    for s in done:
        jf.close(s.id)
        print(f"closed one viewer of {_label(s)}")
    if done and cfg.webhook_url:
        notify.send(cfg.webhook_url, f"Freed {len(done)} stuck Live TV stream(s) that nobody was watching.")
    return 0


def doctor(cfg: Config) -> int:
    jf = Jellyfin(cfg.jellyfin_url, cfg.jellyfin_api_key)
    ok = True

    def reachable() -> str:
        info = jf.public_info()
        return f"{info.get('ServerName')} {info.get('Version')}"

    def key_accepted() -> str:
        jf.info()
        return "yes"

    def log_readable() -> str:
        lines = list(jf.log_lines())
        if not lines:
            print("[WARN] no start-up or live stream line in the newest logs; is the log level above Information?")
        return f"{len(core.read_log(lines))} live stream(s) open"

    checks: list[tuple[str, Callable[[], str]]] = [
        ("Jellyfin reachable", reachable),
        ("API key accepted", key_accepted),
        ("server log", log_readable),
    ]
    for label, check in checks:
        try:
            print(f"[ ok ] {label}: {check()}")
        except JellyfinError as e:
            print(f"[FAIL] {label}: {e}")
            ok = False
    print(f"[ ok ] webhook: {'set' if cfg.webhook_url else 'not set (alerts are skipped)'}")
    print(f"[ ok ] mode: {'dry run (nothing is closed)' if cfg.dry_run else 'LIVE'}")
    return 0 if ok else 1


def main(argv: list[str] | None = None, env: dict[str, str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="lombo-hangup", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("plan")
    run = sub.add_parser("run")
    run.add_argument("--loop", action="store_true")
    args = p.parse_args(argv)

    try:
        cfg = from_env(dict(os.environ) if env is None else env)
    except ConfigError as e:
        print(f"[FAIL] settings: {e}", file=sys.stderr)
        return 2

    if args.cmd == "doctor":
        return doctor(cfg)
    change = args.cmd == "run" and not cfg.dry_run
    loop = args.cmd == "run" and args.loop
    while True:
        try:
            code = run_once(cfg, change)
        except Exception as e:  # noqa: BLE001  a loop survives one bad round, an odd reply included
            print(f"[FAIL] {e}", file=sys.stderr)
            code = 1
        if not loop:
            return code
        time.sleep(cfg.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
