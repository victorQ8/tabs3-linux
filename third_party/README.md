# Third-party sources

## sns-reg

- Source: <https://gitlab.com/msm8996-mainline/sns-reg>, commit
  `4d238e5f0baba3fb77456fe2bffbf8e8f18a71a0` (2025-07-06), exported with
  `git archive`; unmodified.
- License: GPL-3.0-or-later (`sns-reg/LICENSE`), copyright Yassine Oudjana.
  Original project files default to MIT; kernel/Samsung-derived files retain
  their own GPL notices. The `tabs3-sensors` package carries both its project
  and sns-reg notices.
- Local change: `sns-reg-image-mode.patch`, applied at build time with
  `patch -p1 --fuzz=0` by `scripts/build-sensors-package.sh`. It serves the
  SM-T825's binary registry image, see the patch description.

The package installs the server as `/usr/libexec/tabs3-sns-reg`. The registry
image it serves derives from Samsung's software and is never committed; see
`tools/sensor-registry/README.md`.
