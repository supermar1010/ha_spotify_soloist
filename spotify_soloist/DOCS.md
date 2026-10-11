# Spotify Soloist add-on

Runs [Spotify Soloist](https://developer.spotify.com/documentation/soloist),
Spotify's official headless Spotify Connect receiver, on Home Assistant.
Audio plays through the host's audio output (see the **Audio** section on
this add-on's page).

This add-on is unofficial and not affiliated with Spotify. It does not ship
Soloist: on first start it downloads Soloist from Spotify's CDN on your
machine. Soloist is subject to Spotify's terms.

## Setup

1. Create a Soloist API key on the
   [Spotify for Developers dashboard](https://developer.spotify.com/dashboard).
   This needs a Spotify Premium account.
2. Enter the key as `api_key` and start the add-on.
3. In the Spotify app on the same network, select the device named
   `device_name`. Soloist stores the session, so pairing happens once.
4. Optionally, install the **Spotify Soloist** integration to control the
   device from Home Assistant automations.

## Choosing the audio output

Soloist plays through Home Assistant's audio service (PulseAudio). To pick
the speaker, open this add-on's **Configuration** tab, set **Output** in the
**Audio** section to your device (for example a USB DAC or HDMI), save, and
restart the add-on.

If the list is empty or the device is missing, check what the host sees
with the [Terminal & SSH add-on](https://github.com/home-assistant/addons/tree/master/ssh):

```bash
ha audio info                        # lists outputs and the default
ha audio default output --name <output-name>   # sets the system default
ha audio reload                      # after plugging in a USB DAC
```

With **Default** selected, the add-on uses the system default output.

## Options

| Option | Default | Description |
|---|---|---|
| `device_name` | `Home Assistant` | Name in Spotify's device picker. |
| `api_key` | | Your Soloist API key. Required. |
| `websocket_port` | `9090` | Port of the local control API, bound to `127.0.0.1`. |
| `initial_volume` | | Volume 0–100 at startup. Empty uses Soloist's default (40). |
| `cache_size_mb` | | Playback cache limit. `0` means unlimited, otherwise at least 100. |
| `update_check_interval_hours` | `12` | How often to look for a new Soloist build. |
| `update_hour` | `4` | Local hour (0–23) when a downloaded update is installed. |
| `reset_pairing` | `false` | Clear the stored Spotify session at start. Turn it off again afterwards. |
| `verbose` | `false` | Verbose Soloist logs. |

## Updates

Soloist builds expire 90 days after they are built. The add-on checks
Spotify's CDN regularly, downloads new builds in the background, and
installs them at `update_hour`. If a build expires anyway, the add-on
replaces it right away. The log shows the installed build at every start.

## Troubleshooting

- **Device does not show up in Spotify:** the phone must be on the same
  network as Home Assistant, and mDNS must not be blocked between them.
- **No sound:** check the output in the add-on's **Audio** section and run
  `ha audio info` (see [Choosing the audio output](#choosing-the-audio-output)).
- **"Could not install Soloist":** Home Assistant cannot reach
  `soloist-builds.spotifycdn.com`. The add-on retries every 5 minutes.
- **Wrong account / start over:** enable `reset_pairing`, restart, pair
  again, then disable it.

Do not post your API key, unredacted logs or the `/data` folder in public
issues.
