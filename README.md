<p align="center"><img src="assets/banner.svg" alt="LomboHangup" width="100%"></p>

<p align="center">
  <a href="LICENSE"><img alt="License: GPL-3.0" src="https://img.shields.io/github/license/Lombo-Forge/lombo-hangup"></a>
  <a href="https://github.com/Lombo-Forge/lombo-hangup/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/Lombo-Forge/lombo-hangup/ci.yml?branch=main&label=CI"></a>
  <a href="https://github.com/Lombo-Forge/lombo-hangup/actions/workflows/codeql.yml"><img alt="CodeQL" src="https://img.shields.io/github/actions/workflow/status/Lombo-Forge/lombo-hangup/codeql.yml?branch=main&label=CodeQL"></a>
  <a href="https://github.com/Lombo-Forge/lombo-hangup/releases"><img alt="Release" src="https://img.shields.io/github/v/release/Lombo-Forge/lombo-hangup?include_prereleases"></a>
  <img alt="Python 3.12+" src="https://img.shields.io/badge/python-3.12%2B-blue">
  <a href="https://ko-fi.com/datlombardo"><img alt="Support on Ko-fi" src="https://img.shields.io/badge/Ko--fi-support-FF5E5B?logo=ko-fi&logoColor=white"></a>
</p>

# LomboHangup

Frees Live TV tuner slots that Jellyfin keeps open after the viewer has gone. When a player vanishes without saying goodbye, its slot can stay taken, and with a limited IPTV connection or tuner the next channel fails with "Playback Error".

This is a known Jellyfin bug ([#18549](https://github.com/jellyfin/jellyfin/issues/18549), with a proposed fix in [#18550](https://github.com/jellyfin/jellyfin/pull/18550)). Once your server has the fix, you may not need this.

> **Status:** checked against a throwaway Jellyfin 12.4.0 with a fake M3U channel and API players, not yet with real TV apps or a tuner card. Keep it in dry-run mode for a while and read what `plan` says when you know who is watching.

```text
$ lombo-hangup plan
would close one viewer of stream 143b9c88da9c5d0b518fb0b3b57f294b (1 viewer(s) counted)
```

## Contents

- [How it decides](#how-it-decides)
- [What can go wrong](#what-can-go-wrong)
- [Install in a minute](#install-in-a-minute)
- [Commands](#commands)
- [Settings](#settings)
- [Contributing and licence](#contributing-and-licence)

## How it decides

It reads Jellyfin's log to learn which live streams are open and how many viewers each one counts, then compares that with the players reporting each stream. When a stream counts **more viewers than players**, and nobody new has joined for 10 minutes, it looks again 30 seconds later and then removes **one** viewer. Jellyfin closes the stream when none are left. A channel shared with someone who is still watching stays open for them.

It does nothing:

- while any recording is running (a recording holds a stream with no player);
- while any player shows live TV without saying which stream it is on;
- if anything about the stream changes between the two looks.

## What can go wrong

- **A player that never reports what it plays** (some external or DLNA players) looks exactly like a leak, and its stream would be closed after the grace time. If you use one, do not run this live.
- It depends on the wording of Jellyfin's log lines and needs the log level at Information (the default). If the wording changes, it finds nothing rather than guessing.
- It cannot see streams opened more than three log files ago, and leaves those alone.

## Install in a minute

1. In Jellyfin, open Dashboard > API Keys and create a key for LomboHangup.
2. Copy `.env.example` to `.env` and fill in the URL and key.
3. Start it:
   ```sh
   docker compose -f compose.example.yaml up -d
   docker compose -f compose.example.yaml exec lombo-hangup lombo-hangup doctor
   ```

It starts in dry-run mode and closes nothing. Set `LOMBO_HANGUP_DRY_RUN=false` when you are happy.

## Commands

| Command | What it does |
|---|---|
| `lombo-hangup doctor` | Checks settings, Jellyfin and that its log can be read. Exit code 1 if anything fails. |
| `lombo-hangup plan` | Shows which streams look stuck. Never changes anything. |
| `lombo-hangup run [--loop]` | Closes them. `--loop` repeats every `LOMBO_HANGUP_INTERVAL_SECONDS`. |

## Settings

Everything is an environment variable, listed with defaults in [.env.example](.env.example). A Jellyfin API key has full control of the server, so keep `.env` private.

## Contributing and licence

Contribution, security and conduct rules come from the [Lombo-Forge organisation](https://github.com/Lombo-Forge/.github). Licensed under [GPL-3.0](LICENSE). Credits are in [NOTICE.md](NOTICE.md). Not affiliated with or endorsed by the Jellyfin project.
