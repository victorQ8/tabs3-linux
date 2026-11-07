#!/usr/bin/env python3
"""Install the project's tracked LTE DTS in the verified kernel work tree."""
import hashlib
import json
import pathlib
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]
subprocess.run(["python3", str(ROOT / "scripts/prepare-kernel.py")], check=True)
src = ROOT / "work" / json.loads((ROOT / "config/sources.json").read_text())["kernel"]["directory"]
# Local patches stack in order and may touch the same file, so record what
# was applied (name and hash) instead of probing each patch in isolation.
patches = sorted((ROOT / "kernel/patches").glob("*.patch"))
wanted = [f"{patch.name} {hashlib.sha256(patch.read_bytes()).hexdigest()}" for patch in patches]
stamp = src / ".tabs3-local-patches"
applied = stamp.read_text().splitlines() if stamp.exists() else []
if applied != wanted[:len(applied)]:
    raise SystemExit("Local patches changed after they were applied; re-extract the kernel work tree")
for patch, entry in zip(patches[len(applied):], wanted[len(applied):]):
    print(f"Applying {patch.name}", flush=True)
    subprocess.run(["patch", "--batch", "--forward", "--fuzz=0", "-p1", "-i", str(patch)],
                   cwd=src, check=True)
    applied.append(entry)
    stamp.write_text("".join(line + "\n" for line in applied))
# Board variants (.dts) and their per-topic includes (.dtsi).
for path in sorted((ROOT / "kernel").glob("msm8996-samsung-gts3llte*.dts*")):
    shutil.copyfile(path, src / "arch/arm64/boot/dts/qcom" / path.name)
shutil.copyfile(ROOT / "kernel/sm5705-gts3l-policy.h",
                src / "drivers/power/supply/sm5705-gts3l-policy.h")
for name in ("ams968hh01-dimming.h", "ams968hh01-dimming-data.h"):
    shutil.copyfile(ROOT / "kernel" / name, src / "drivers/gpu/drm/panel" / name)
print("LTE bring-up DTS installed; no hardware validation is implied.")
