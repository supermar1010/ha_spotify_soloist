# Changelog

## 0.1.4

- Soloist could keep showing "playing" without any sound after Home
  Assistant's audio service restarted, until Soloist itself was restarted.
  The add-on now warns when Soloist plays without an audio stream and, as a
  last resort after a minute, restarts Soloist (press play again afterwards).
- Log audio diagnostics (outputs, volumes, Soloist's stream) when the
  watchdog warns, to help track down remaining no-sound cases.
- Log a warning when moving playback to the selected output fails.
- With `verbose` on, log the same audio snapshots when playback starts or
  moves and when the selected output appears or disappears. They also report
  whether sound reaches the output (`signal=audio` / `signal=silent`) and the
  stream latency, and are repeated 15 s after playback starts or moves and
  every 5 minutes while playing.

## 0.1.3

- Fix: sometimes no sound for minutes after starting playback, until the
  stream suddenly moved to the selected audio output. The add-on now notices
  new streams right away and re-checks every 10 seconds.

## 0.1.2

- Fix: playback failed and paused itself when the selected audio output was
  missing, for example while a USB DAC is switched off. Soloist's stream now
  moves to the selected output as soon as it appears, and back to it if it
  disappears and returns.
- Remove a deprecation warning from the Supervisor helper library.

## 0.1.1

- Fix: play to the output selected in the add-on's **Audio** section.
  Soloist talks to PulseAudio directly and ignored it, playing to the
  system default output instead.

## 0.1.0

- First release: runs Spotify Soloist as a Spotify Connect device.
- Downloads Soloist from Spotify at runtime and keeps it updated before the
  90-day build expiry.
