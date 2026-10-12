# Agent notes

## Releasing

- Every release adds an entry to `spotify_soloist/CHANGELOG.md`, the only
  changelog. Home Assistant shows it in the add-on's update dialog.
- Bump `version` in `spotify_soloist/config.yaml`, push, wait for CI, then
  create a GitHub release `v<version>`. The "Publish add-on" workflow builds
  the images and fails if the tag and `config.yaml` disagree.
- Docs-only changes need no release or changelog entry.
