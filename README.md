# Spotify Soloist for Home Assistant

Turn your Home Assistant machine into a Spotify Connect speaker and control
it from automations.

This repository contains two parts that work together:

| Part | What it does |
|---|---|
| **Add-on** (`spotify_soloist/`) | Runs [Spotify Soloist](https://developer.spotify.com/documentation/soloist), Spotify's official headless Connect receiver, on Home Assistant OS. Plays through the host's audio output. Downloads Soloist from Spotify and keeps it updated before each build's 90-day expiry. |
| **Integration** (`custom_components/spotify_soloist/`) | Connects to Soloist's local WebSocket API and exposes a `media_player` entity with live state, track metadata, cover art, volume, shuffle, repeat, seek and `play_media`. |

```
Spotify app ──Connect──▶ Soloist (add-on) ──audio──▶ HA host speaker / DAC
                              ▲
                     ws://127.0.0.1:9090
                              │
                  media_player.<device> (integration) ◀── automations
```

> [!IMPORTANT]
> **Unofficial project.** This project is not affiliated with or endorsed by
> Spotify. Spotify Soloist is proprietary software, and you use it under
> [Spotify's terms](https://developer.spotify.com/terms). This repository
> **does not contain or redistribute** the Soloist binary. The add-on
> downloads it from Spotify's CDN on your own machine. Spotify's terms do not
> clearly allow running Soloist this way, so use it at your own risk.

## Requirements

- Home Assistant OS or Supervised (for the add-on), on `aarch64` or `amd64`.
  32-bit ARM is not supported: Home Assistant dropped it, and Soloist needs
  glibc 2.38 or newer (Debian trixie).
- An audio output on the Home Assistant host, such as a USB DAC, HDMI or a
  Pi's headphone jack. Pick it under **Settings → System → Hardware → Audio**,
  or in the add-on's **Audio** section.
- A **Spotify Premium** account to create the Soloist API key. Once the
  device is set up, Free and Premium users can both play to it.

## Installation

### 1. Create a Soloist API key

1. Sign in to [Spotify for Developers](https://developer.spotify.com/dashboard).
2. Open the **Spotify Soloist API Key** page and generate a key.
3. Keep the key secret. Each user must generate their own key.

### 2. Install the add-on

[![Add repository](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsupermar1010%2Fha_spotify_soloist)

1. **Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then add
   `https://github.com/supermar1010/ha_spotify_soloist`.
2. Install **Spotify Soloist**.
3. In **Configuration**, set `api_key`, and change `device_name` if you like.
4. Start the add-on. The first start downloads Soloist from Spotify.
5. Open Spotify on a phone or computer on the same network and pick the
   device in the device picker. This pairs Soloist with your account. The
   session is stored, so you only do this once.

See [the add-on docs](spotify_soloist/DOCS.md) for every option.

### 3. Install the integration

With [HACS](https://hacs.xyz): **HACS → ⋮ → Custom repositories**, then add
this repository as type **Integration**, install **Spotify Soloist**, and
restart Home Assistant.

Manual: copy `custom_components/spotify_soloist` into your
`config/custom_components/` folder and restart.

Then go to **Settings → Devices & services → Add integration → Spotify
Soloist**. The defaults (`127.0.0.1`, port `9090`) match the add-on.

## Using it in automations

The entity is a standard `media_player`, so all the usual services work.

| Action | Soloist command |
|---|---|
| `media_player.turn_on` / `turn_off` | Take over / release the Spotify Connect session |
| `media_player.media_play` / `media_pause` / `media_stop` | Play / pause |
| `media_player.media_next_track` / `media_previous_track` | Skip |
| `media_player.media_seek` | Seek |
| `media_player.volume_set` / `volume_up` / `volume_down` | Volume (0–100 in Soloist) |
| `media_player.shuffle_set` / `repeat_set` | Shuffle, repeat `off` / `all` / `one` |
| `media_player.play_media` | Play a `spotify:` URI or `open.spotify.com` link (track, album, playlist, artist, episode, show) |
| `media_player.play_media` with `enqueue: add` or `next` | Add a single track to the queue |

The entity state is `off` when Soloist is not the active Connect device,
`unavailable` when the add-on is not reachable, and otherwise `playing`,
`paused`, `buffering` or `idle`.

Extra attributes: `context_uri` (the playing album or playlist) and `queue`
(the next 10 items).

### Example: wake-up playlist

```yaml
automation:
  - alias: Morning music
    triggers:
      - trigger: time
        at: "07:00:00"
    conditions:
      - condition: state
        entity_id: binary_sensor.workday
        state: "on"
    actions:
      - action: media_player.volume_set
        target:
          entity_id: media_player.home_assistant
        data:
          volume_level: 0.25
      - action: media_player.play_media
        target:
          entity_id: media_player.home_assistant
        data:
          media_content_type: playlist
          media_content_id: spotify:playlist:37i9dQZF1DXcBWIGoYBM5M
```

### Example: pause when the doorbell rings

```yaml
automation:
  - alias: Pause music for doorbell
    triggers:
      - trigger: state
        entity_id: binary_sensor.doorbell
        to: "on"
    conditions:
      - condition: state
        entity_id: media_player.home_assistant
        state: playing
    actions:
      - action: media_player.media_pause
        target:
          entity_id: media_player.home_assistant
```

### Example: react to a track change

```yaml
automation:
  - alias: Announce track
    triggers:
      - trigger: state
        entity_id: media_player.home_assistant
        attribute: media_title
    actions:
      - action: notify.mobile_app_phone
        data:
          message: >-
            Now playing {{ state_attr('media_player.home_assistant', 'media_title') }}
            by {{ state_attr('media_player.home_assistant', 'media_artist') }}
```

## How the auto-update works

Each Soloist build stops working 90 days after its build date: it exits with
code `10`. The add-on handles this for you:

1. On first start, it downloads the build for your CPU from
   `soloist-builds.spotifycdn.com`.
2. Every `update_check_interval_hours` (default 12), it compares the CDN
   archive's `ETag` with the installed build.
3. When Spotify publishes a new build, the add-on downloads it, extracts only
   the `soloist` executable, checks that `soloist --version` runs, and stages
   it.
4. It installs the staged build at `update_hour` (default 04:00), so
   playback is not interrupted during the day.
5. If the running build expires anyway (exit code `10`), the add-on replaces
   it right away. If Spotify has not published a newer build yet, it retries
   every hour.

The binary lives in the add-on's `/data` folder, so it survives add-on
updates and restarts.

## Security

Soloist's WebSocket API has **no authentication**. The add-on binds it to
`127.0.0.1` only, so only processes on the Home Assistant host can reach it.
Do not expose it to your network.

## Development

```
custom_components/spotify_soloist/   Home Assistant integration
spotify_soloist/                     Home Assistant add-on
  rootfs/usr/bin/soloist-supervisor  Run loop and auto-updater
tests/                               Unit tests (client, media player)
tests/addon/smoke.sh                 Add-on smoke test (Docker)
```

Lint and test:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
ruff check . && ruff format --check .
pytest
```

Build the add-on and smoke-test it. This downloads Soloist from Spotify and
checks that it starts and opens its WebSocket API (no API key needed):

```bash
docker build -t soloist-addon:dev \
  --build-arg BUILD_FROM=ghcr.io/home-assistant/amd64-base-debian:trixie \
  spotify_soloist
tests/addon/smoke.sh soloist-addon:dev
```

CI (`.github/workflows/ci.yaml`) runs Ruff, ShellCheck, the unit tests,
hassfest, HACS validation, the add-on linter, and builds and smoke-tests
the add-on for `amd64` and `aarch64`.

### Releasing

Home Assistant pulls prebuilt images from GHCR (`image:` in
`config.yaml`), so a version must be published before users can install
or update to it. To release:

1. Bump `version` in `spotify_soloist/config.yaml` and
   `custom_components/spotify_soloist/manifest.json`, and update both
   changelogs.
2. Create a GitHub release with tag `v<version>`. The **Publish add-on**
   workflow pushes `ghcr.io/supermar1010/{arch}-addon-spotify_soloist`.
3. The GHCR packages must be public, or Home Assistant cannot pull them
   (package settings → visibility; set once per package).

HACS installs the integration from the release tags. It needs no build.

Contributions are welcome. Please open an issue first for larger changes.
Never attach Soloist binaries, API keys, unredacted logs or data
directories to issues.

## License

MIT, see [LICENSE](LICENSE). This license covers only the code in this
repository, not Spotify Soloist.
