#!/usr/bin/env python3
"""Fetch and patch the upstream research baseline. This does not create an LTE boot image."""
import hashlib
import json
import pathlib
import shutil
import subprocess
import tarfile
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    sources = json.loads((ROOT / "config/sources.json").read_text())
    kernel = sources["kernel"]
    port = ROOT / "upstream/gts3lwifi-mainline"
    actual = subprocess.check_output(["git", "-C", str(port), "rev-parse", "HEAD"], text=True).strip()
    if actual != sources["port"]["commit"]:
        raise SystemExit("Upstream checkout differs from config/sources.json")
    if subprocess.check_output(["git", "-C", str(port), "status", "--porcelain"], text=True).strip():
        raise SystemExit("Upstream checkout has local edits; preserve them and use a clean pinned checkout")
    work = ROOT / "work"
    work.mkdir(exist_ok=True)
    archive = work / pathlib.PurePosixPath(urllib.parse.urlparse(kernel["url"]).path).name
    if not archive.exists():
        part = archive.with_suffix(".part")
        print("Downloading pinned kernel source...", flush=True)
        with urllib.request.urlopen(kernel["url"], timeout=90) as response, part.open("wb") as out:
            shutil.copyfileobj(response, out)
        part.rename(archive)
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha512").hexdigest()
    if digest != kernel["sha512"]:
        raise SystemExit("Kernel archive SHA-512 mismatch; source was not extracted")
    destination = work / kernel["directory"]
    # Base patches: the msm8996-mainline community commits and upstream
    # backports this board needs on a kernel.org tree (kernel/base/*.patch).
    base = sorted((ROOT / kernel["base_patches"]).glob("*.patch"))
    stamp_text = "\n".join([actual] + [f"{p.name} {hashlib.sha256(p.read_bytes()).hexdigest()}"
                                       for p in base]) + "\n"
    stamp = destination / ".tabs3-prepared"
    if stamp.exists() and stamp.read_text() == stamp_text:
        print(f"Already prepared: {destination}")
        return
    if destination.exists():
        raise SystemExit(f"Unfinished or outdated source at {destination}; preserve or remove it explicitly before retrying")
    print("Verified SHA-512; extracting...", flush=True)
    with tarfile.open(archive) as tar:
        tar.extractall(work, filter="data")
    if not destination.is_dir():
        raise SystemExit(f"Archive did not create {destination}")
    patchdir = port / "pmaports/linux-postmarketos-qcom-msm8996"
    for patch in base + sorted(patchdir.glob("000*.patch")):
        print(f"Applying {patch.name}", flush=True)
        subprocess.run(["patch", "--batch", "--fuzz=0", "-p1", "-i", str(patch)], cwd=destination, check=True)
    shutil.copyfile(patchdir / "config-postmarketos-qcom-msm8996.aarch64", work / "kernel.config")
    stamp.write_text(stamp_text)
    print("Research baseline ready. LTE Linux DTS is still pending hardware verification.")


if __name__ == "__main__":
    main()
