# How it is built

## Contents

- [The shape](#the-shape)
- [Jellyfin behaviour it relies on](#jellyfin-behaviour-it-relies-on)
- [Safe by default](#safe-by-default)

## The shape

```
Jellyfin  <--  jellyfin.py  -->  cli.py  -->  core.py (reads the log lines, decides)
                                    |
                                    +-->  notify.py  -->  your webhook
```

`core.py` never touches the network, the disk or the clock.

## Jellyfin behaviour it relies on

Seen on a real Jellyfin 12.4.0:

- Nothing in the API lists open live streams. The log does: `Live stream opened: ... LiveStreamId`,
  `Live stream "<short id>" consumer count is now N` and `Closing live stream "<id>"`.
- A channel gets the same stream id every time. A second viewer raises the count instead of opening another.
- A player's progress reports put the id in `PlayState.LiveStreamId` on `/Sessions`.
- A recording opens a stream with no session. `/LiveTv/Timers?isActive=true` lists it.
- `POST /LiveStreams/Close` removes one viewer; for a stream that is already gone it logs nothing.
- A restart drops streams without logging it, so everything is forgotten at each `Jellyfin version:` line.

## Safe by default

- `DRY_RUN` is true until set to false. `plan` and dry run close and alert nothing.
- The only change it can make is closing one viewer of one stream.
- The log is read before the players, so someone joining in between is still seen.
- Two looks, 30 seconds apart, must agree.
- Log patterns are anchored to the start of the line, so text inside another message cannot pose as one.
- Redirects are refused, so a close cannot silently turn into something else.
