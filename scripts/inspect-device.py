#!/usr/bin/env python3
"""Read-only inventory of Tab S3 LTE devices; never issue shell commands to other devices."""
import argparse
import datetime
import json
import pathlib
import re
import subprocess
import sys

PROPERTIES = (
    "ro.product.model", "ro.product.device", "ro.product.name", "ro.product.board",
    "ro.board.platform", "ro.hardware", "ro.build.version.release",
    "ro.build.version.security_patch", "ro.build.display.id", "ro.bootloader",
    "gsm.version.baseband", "ro.boot.flash.locked", "ro.boot.verifiedbootstate",
    "ro.boot.vbmeta.device_state", "ro.oem_unlock_supported", "sys.oem_unlock_allowed",
    "ro.boot.warranty_bit",
)


def run(*args):
    return subprocess.run(args, text=True, capture_output=True, timeout=20, check=True).stdout.strip()


def parse_devices(output):
    devices = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 2:
            continue
        metadata = dict(field.split(":", 1) for field in fields[2:] if ":" in field)
        devices.append((fields[0], fields[1], metadata))
    return devices


def is_lte_candidate(metadata):
    return (metadata.get("device", "").startswith("gts3llte")
            or re.fullmatch(r"SM_T82[57][A-Z0-9]*", metadata.get("model", "")) is not None)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=pathlib.Path, help="Save report locally (serial number omitted).")
    args = parser.parse_args()
    devices = parse_devices(run("adb", "devices", "-l"))
    candidates = []
    for serial, state, metadata in devices:
        model = metadata.get("model", "unidentified device")
        print(f"USB/ADB: {model}: {state}", file=sys.stderr)
        if state == "device" and is_lte_candidate(metadata):
            candidates.append(serial)
    if len(candidates) != 1:
        print("Need exactly one authorized Tab S3 LTE. Power it on, enable USB debugging, "
              "and accept the PC prompt. Other devices are ignored.", file=sys.stderr)
        return 2
    serial = candidates[0]
    properties = {key: run("adb", "-s", serial, "shell", "getprop", key) for key in PROPERTIES}
    if not re.fullmatch(r"SM-T82[57][A-Z0-9]*", properties["ro.product.model"]):
        print("Unexpected model; stopping before further inspection.", file=sys.stderr)
        return 2
    report = {"timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "properties": properties}
    try:
        # Only battery/power state; no user files, identifiers, or full getprop dump.
        report["battery"] = run("adb", "-s", serial, "shell", "dumpsys", "battery")
    except subprocess.CalledProcessError:
        report["battery"] = "unavailable"
    rendered = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        print(f"Device inspection failed: {exc}", file=sys.stderr)
        sys.exit(1)
