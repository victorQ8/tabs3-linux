# Security Policy

Maintainer: [@victorQ8](https://github.com/victorQ8).

## Reporting a vulnerability

[Report a vulnerability privately](https://github.com/victorQ8/tabs3-linux/security/advisories/new)
through GitHub. Do not disclose vulnerability details in public issues,
pull requests, or discussions.

Include, where possible:

- The affected component, commit or package version, and device revision.
- Steps to reproduce or a minimal proof of concept.
- The observed impact and any access or configuration required to reproduce it.
- Relevant logs, with credentials and device identifiers removed.

Do not attach private keys, passwords, Wi-Fi profiles, calibration data, or
complete partition backups. If private reporting is unavailable, open an issue
asking for a private contact channel without including vulnerability details.

## Supported versions

Security fixes are developed on the default branch, `main`. Older commits,
packages, and boot images do not receive separate backports. The installed
baseline recorded in the [README](README.md) is a hardware-validation reference,
not a separately maintained security release.

TabS3 Linux is experimental and does not currently maintain long-term support
branches. See the [hardware status](docs/hardware-status.md) for qualification
limits.

## Scope

Reports are welcome for:

- Kernel and driver patches carried by this project.
- Bootloader modifications, initramfs, recovery, and flashing tools.
- Build scripts, packaging, and default system configuration.
- The dashboard and other project-maintained utilities.

For vulnerabilities solely in unmodified upstream code, use that project's
security reporting channel. If the cause is uncertain or involves this port's
integration, report it here so it can be assessed and routed appropriately.
Samsung firmware and Android components not distributed here are maintained
outside this project.

Expected administrator access or the ability to boot modified software with an
unlocked bootloader is not, by itself, a vulnerability. Unexpected privilege
escalation or a bypass of an intended security boundary remains in scope.

## Response and disclosure

The target is to acknowledge reports within **7 days** and provide an initial
assessment within **14 days**. These are best-effort response targets, not
guaranteed response or fix deadlines.

Confirmed issues may be addressed through a source fix, updated package, or
documented mitigation. Timing depends on severity, reproducibility, and hardware
validation. Disclosure timing will be coordinated with the reporter; reports
will be forwarded to upstream maintainers with the reporter's permission.
Reporters are credited with their permission.

Please test only on devices you own or have explicit permission to test.

## Authentication

- Users can choose SSH keys or account-password login for installed Debian.
  Password login can be enabled using the [account setup guide](docs/accounts.md#enable-ssh-password-login).
  Fresh builds start with password authentication disabled; root SSH login is
  disabled by default.
- Diagnostic and recovery images intentionally allow **root SSH using the
  owner's public key**; password authentication remains disabled.
- The initial `dev` account has **passwordless sudo**. See
  [account setup](docs/accounts.md) to change this policy.
- Users choose their console password and supply their SSH public key during
  the build. There is no shared password or public personalized login image.
- Samsung firmware, credentials, calibration backups, and personalized images
  are not distributed by this repository.
