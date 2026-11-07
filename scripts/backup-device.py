#!/usr/bin/env python3
"""Read current SM-T825 boot/recovery partitions and live DTB through existing root access."""
import datetime
import argparse
import hashlib
import importlib.util
import json
import os
import pathlib
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inspector", ROOT / "scripts/inspect-device.py")
inspector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inspector)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--calibration-only", action="store_true",
                        help="Privately preserve EFS, modemst1/2 and persist instead of boot/recovery.")
    args = parser.parse_args()
    devices = inspector.parse_devices(inspector.run("adb", "devices", "-l"))
    candidates = [serial for serial, state, meta in devices
                  if state == "device" and inspector.is_lte_candidate(meta)]
    if len(candidates) != 1:
        raise SystemExit("Need exactly one authorized Tab S3 LTE")
    serial = candidates[0]
    model = inspector.run("adb", "-s", serial, "shell", "getprop", "ro.product.model")
    if model != "SM-T825":
        raise SystemExit(f"Backup procedure only validated for SM-T825; found {model}")

    def remote(command, **kwargs):
        # One remote command argument, with the command to su explicitly quoted.
        return subprocess.run(["adb", "-s", serial, "exec-out", "su -c " + shlex.quote(command)],
                              check=True, timeout=120, stderr=subprocess.PIPE, **kwargs)

    identity = remote("id", stdout=subprocess.PIPE).stdout.decode()
    if "uid=0(root)" not in identity:
        raise SystemExit("Root access was not granted; no backup was attempted")
    os.umask(0o077)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ROOT / "private" / "backups" / stamp
    dest.mkdir(parents=True)
    manifest = {"model": model, "timestamp_utc": stamp, "images": {},
                "bootloader": inspector.run("adb", "-s", serial, "shell", "getprop", "ro.bootloader"),
                "note": "Current rooted-device images, not claimed to be untouched stock firmware."}
    partition_listing = remote("ls -l /dev/block/bootdevice/by-name", stdout=subprocess.PIPE).stdout
    (dest / "partitions.txt").write_bytes(partition_listing)
    sources = (
        ("boot.img", "/dev/block/bootdevice/by-name/boot"),
        ("recovery.img", "/dev/block/bootdevice/by-name/recovery"),
        ("live.dtb", "/sys/firmware/fdt"),
    )
    if args.calibration_only:
        sources = tuple((name + ".img", "/dev/block/bootdevice/by-name/" + name)
                        for name in ("efs", "modemst1", "modemst2", "persist"))
        manifest["note"] = "Sensitive LTE identity/calibration backups. Never publish these images."
    for name, source in sources:
        print(f"Reading {name}...", flush=True)
        if name.endswith(".img"):
            size = int(remote("blockdev --getsize64 " + source, stdout=subprocess.PIPE).stdout)
        else:
            size = int(remote("stat -c %s " + source, stdout=subprocess.PIPE).stdout)
        part = dest / (name + ".partial")
        with part.open("xb") as out:
            remote("cat " + source, stdout=out)
        if part.stat().st_size != size:
            raise SystemExit(f"Short/oversized read for {name}; retained .partial file")
        with part.open("rb") as stream:
            magic = stream.read(8)
            stream.seek(0)
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        expected_magic = {"boot.img": b"ANDROID!", "recovery.img": b"ANDROID!",
                          "live.dtb": b"\xd0\x0d\xfe\xed"}.get(name)
        if expected_magic and not magic.startswith(expected_magic):
            raise SystemExit(f"Unexpected header in {name}; retained .partial file")
        device_digest = remote("sha256sum " + source, stdout=subprocess.PIPE).stdout.decode().split()[0]
        if digest != device_digest:
            raise SystemExit(f"Device/local hash mismatch for {name}; retained .partial file")
        part.rename(dest / name)
        manifest["images"][name] = {"source": source, "size": size, "sha256": digest}
        (dest / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(f"Verified {name}: {size} bytes", flush=True)
    print(f"Backup complete: {dest}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Backup failed: {exc}", file=sys.stderr)
        sys.exit(1)
