ARG BUILD_FROM
FROM ${BUILD_FROM}

# libatomic1: linked by Soloist.
# libpulse0:  dlopen'd by Soloist to play through Home Assistant's PulseAudio.
# pulseaudio-utils: pactl, to move Soloist's stream to the selected output.
# libavformat61/libavcodec61: dlopen'd by Soloist (FFmpeg) for some content.
# The Soloist binary itself is NOT part of this image; it is downloaded from
# Spotify at runtime (see /usr/bin/soloist-supervisor).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libatomic1 \
        libavcodec61 \
        libavformat61 \
        libpulse0 \
        pulseaudio-utils \
    && rm -rf /var/lib/apt/lists/*

COPY rootfs /
