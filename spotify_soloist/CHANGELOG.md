# Changelog

## 0.1.1

- Fix: play to the output selected in the add-on's **Audio** section.
  Soloist talks to PulseAudio directly and ignored it, playing to the
  system default output instead.

## 0.1.0

- First release: runs Spotify Soloist as a Spotify Connect device.
- Downloads Soloist from Spotify at runtime and keeps it updated before the
  90-day build expiry.
