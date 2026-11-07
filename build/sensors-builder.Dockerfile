# ARM64 user-space build of the sensor registry server (tabs3-sensors). Derived
# from the recovery UI builder so its toolchain and the kernel builder's stay
# unchanged; adds the ARM64 QRTR library from the Debian archive.
FROM tabs3-ui-builder:trixie
RUN dpkg --add-architecture arm64 && apt-get update \
    && apt-get install -y --no-install-recommends libqrtr-dev:arm64 \
    && rm -rf /var/lib/apt/lists/*
