# Credits and licenses

## Project development

Most of the project-specific development was carried out by **OpenAI Codex**
and **Anthropic Claude**. Their work includes kernel and driver development,
Debian integration, recovery and maintenance tools, dashboard design,
debugging, automated testing, and documentation.

## Upstream projects and licenses

This is an independent community project, not an official Samsung or Debian
device release. Source notices and patch authorship take precedence over a
repository-level license label.

| Component | Source / license |
| --- | --- |
| Original project tools and dashboard | [MIT](../LICENSE), except files with their own notices |
| Linux and kernel-derived work | [Linux](https://kernel.org/); retain kernel/file GPL notices |
| Samsung-derived dimming code, data and fixtures | GPL-2.0-only; [license text](../LICENSES/GPL-2.0-only.txt) and file provenance |
| Starting Tab S3 device port | [wh1ter0z3/gts3lwifi-mainline](https://github.com/wh1ter0z3/gts3lwifi-mainline), pinned submodule |
| MSM8996 community work | [msm8996-mainline](https://gitlab.com/msm8996-mainline/linux), sources in patch metadata |
| Bootloader | [lk2nd](https://github.com/msm8916-mainline/lk2nd), pinned submodule; its own license notices |
| Recovery graphics | [LVGL](https://github.com/lvgl/lvgl), MIT, pinned submodule |
| Sensor registry service | [sns-reg](../third_party/README.md), Yassine Oudjana, GPL-3.0-or-later |
| Dashboard rendering | [Pillow](https://github.com/python-pillow/Pillow), installed as a dependency |
| Typography | B612 / B612 Mono and DejaVu from Debian font packages; font files are not embedded in this source release |
| Terminal layout inspiration | [btop](https://github.com/aristocratos/btop) |

Exact source revisions and archive hashes are recorded in
[sources.json](../config/sources.json), [.gitmodules](../.gitmodules),
[kernel patch notes](../kernel/PATCHES.md), and [third_party](../third_party/README.md).
Copyright, sign-off and provenance lines in carried patches are retained.

Samsung signed firmware, sensor registry images reconstructed from proprietary
binaries, calibration and partition backups remain on the owner's systems.
Tools read them from the owner's device/backups; those binary files are not
redistributed here. Personalized images also remain private.
