# Changelog

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
