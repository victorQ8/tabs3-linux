# Contributing

Start with [hardware status](docs/hardware-status.md) and
[building](docs/building.md). The project targets the SM-T825 rev05; another
variant needs its own identity, power, memory and recovery validation.

For a change, explain the failure, the resulting behavior, source provenance,
and exactly what was tested. Distinguish compilation, host tests, RAM boot,
installed boot, physical observations, and endurance. Do not mark a driver
working only because it probes.

Run `python3 -m unittest discover -s tests`. Some tests require prepared kernel
source (`python3 scripts/prepare-lte-kernel.py`). Use `scripts/ci.sh HEAD` for
the clean container build of a committed revision. GitHub's source checks do
not access hardware and cannot certify it.

Preserve copyright/license notices. Keep local kernel patches focused, with
references and matching notes in `kernel/PATCHES.md`. Never weaken model,
partition, boot-image, charger, or recovery checks merely to make a test pass.

Issue reports should include model/revision, package versions, power/cable
setup, reproduction steps, expected vs actual behavior, and narrowly selected
redacted logs. Do not upload `private/`, firmware, partition images, passwords,
keys, Wi-Fi profiles, IMEI/IMSI/ICCID, serial numbers, MAC addresses or private
network addresses. Use `scripts/check-publication.py` before committing.

For security vulnerabilities, follow the [security policy](SECURITY.md) and
use [private reporting](https://github.com/victorQ8/tabs3-linux/security/advisories/new).
Do not include vulnerability details in public issues or pull requests.
