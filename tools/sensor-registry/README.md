# Sensor registry for the SM-T825's sensor DSP

The SLPI (sensor DSP) starts its Sensor Manager only after it has read its
configuration from a registry that the application processor serves over
QRTR (QMI service `SNS_REG`, 0x10f). Android's `sensors.qti` built that
registry, `sns.reg`, as one byte image of 100 groups at fixed offsets, from
built-in defaults plus `/vendor/etc/sensors/sensor_def_qcomdev.conf`. The
SLPI crashes on a registry made from that configuration file alone, because
Samsung's own groups and defaults are missing.

`make-registry.py` rebuilds the image from this tablet's own Android system
backup: it runs Samsung's `sns_group_data_init()` from `sensors.qti` in a
Unicorn ARM64 emulator for every group, then applies the configuration file.
The image and the files it comes from are Samsung's software: they stay in
`private/` and are never committed or packaged.

## Steps

On the PC, from the project root:

```sh
python3 -m venv work/registry-venv
work/registry-venv/bin/pip install unicorn==2.1.4 pyelftools==0.33
work/registry-venv/bin/python -I tools/sensor-registry/make-registry.py \
    private/backups/<stamp>-system/system.img.zst
tools/sensor-registry/install-registry.sh
```

`make-registry.py` checks that `sensors.qti` is the build it was written for
(SHA-256 `5b7bf4d5…`) and reports whether the result matches the image
validated on 2026-10-13 (`381ca9df…`). It needs `zstd` and `debugfs`
(e2fsprogs) and briefly needs 4.2 GB of disk space for the unpacked image.

The tablet also needs the `tabs3-sensors` package (the registry server
`tabs3-sns-reg.service` and the accelerometer's udev rule) and the SLPI
firmware (`sudo tools/install-slpi-firmware`, on the tablet). The SLPI reads
the registry once per start, so reboot after the first install.
