# User-space ARM64 cross builds (recovery UI). Derived from the main builder so
# kernel and bootloader builds keep their recorded toolchain unchanged.
FROM tabs3-builder:trixie
RUN apt-get update && apt-get install -y --no-install-recommends \
    libc6-dev-arm64-cross linux-libc-dev-arm64-cross \
    && rm -rf /var/lib/apt/lists/*
