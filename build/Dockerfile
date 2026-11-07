FROM debian:trixie-slim@sha256:a29215f6a35e51e22adffa17f89e9d2ef06214e64a2bad10d765c46aea49f11f
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git python3 build-essential gcc-aarch64-linux-gnu gcc-arm-none-eabi \
    bison flex bc libssl-dev libelf-dev libfdt-dev device-tree-compiler \
    cpio kmod xz-utils zstd rsync dpkg-dev fakeroot shellcheck e2fsprogs \
    mmdebstrap arch-test qemu-user-static qemu-user-binfmt \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /project
