# Using the tablet

## USB SSH

Use a data-capable USB cable directly between tablet and Linux computer. The
tablet exposes a USB network adapter; installed Debian is `172.16.42.2`.
Find the computer-side interface with `ip -br link`. Its project-assigned MAC
is `02:54:53:33:00:01` (a fixed development address, not a factory identifier).

Replace the placeholder with that interface only:

```sh
USB_IF=YOUR_USB_INTERFACE
sudo ip address replace 172.16.42.1/30 dev "$USB_IF"
sudo ip link set "$USB_IF" up
ssh -i private/id_ed25519 -o IdentitiesOnly=yes \
    -o UserKnownHostsFile=private/installed-known-hosts dev@172.16.42.2
```

This temporary computer-side address does not configure internet sharing.
Use Wi-Fi for internet access. Do not assign it to your Wi-Fi/Ethernet interface.
Only one tablet with the default USB addressing should use this link at a time.
If you prefer an account password, follow the
[password-login setup and connection example](accounts.md#enable-ssh-password-login).

## Wi-Fi

The console/appliance image uses IWD. On the tablet:

```sh
sudo iwctl
```

At its interactive prompt:

```text
device list
station wlan0 scan
station wlan0 get-networks
station wlan0 connect "Your network name"
exit
```

Enter the Wi-Fi password when prompted. Use the interface from `device list`
if it is not `wlan0`. Check `ip -br address` afterward. From the computer, SSH
to that Wi-Fi address with the same user/key and
`-o HostKeyAlias=172.16.42.2` to verify the same pinned host identity.
The optional Phosh desktop uses NetworkManager with IWD; use its network UI
instead of mixing both configuration paths.

## Dashboard and screen

```sh
tabs3-dashboard-theme
sudo tabs3-dashboard-theme silicon
```

Other choices: `original`, `observatory`, `folio`, `terminal`.
The selected theme survives reboot. [See all screenshots](screenshots.md).
Edit `/etc/tabs3/dashboard.conf`, then restart
`sudo systemctl restart tabs3-dashboard` to change fonts, refresh interval or
presence-wake settings.

The appliance profile turns the panel off after 60 seconds idle. Touch or Power
wakes it; sensor-based wake depends on firmware and enabled settings. Pixel
shifting and true-black backgrounds reduce static exposure but do not make
an AMOLED immune to aging. Leave panel idle protection enabled.

Presence wake can use light, motion, microphone or front camera. To keep only
manual wake, set all four `WAKE_ON_LIGHT`, `WAKE_ON_MOTION`, `WAKE_ON_SOUND`, and
`WAKE_ON_CAMERA` values to `0`. Camera frames are processed in memory and not
saved. Microphone close/reopen behavior is still under qualification.

Brightness uses levels 0–255. Restore the project's normal setting with:

```sh
echo 86 | sudo tee /sys/class/backlight/ams968hh01/brightness
```

Level 0 is still lit. Use Power or normal screen blanking to turn it fully off.
For a console session, stop the dashboard and switch to tty1:

```sh
sudo systemctl stop tabs3-dashboard
sudo chvt 1
```

Start it again with `sudo systemctl start tabs3-dashboard`.

## Charging and battery care

The keeper normally holds a **65–80% charge window**. If a full battery is
plugged in, it may deliberately descend to 80% before resting on external
power. “Reducing to 80%” and “Battery resting” describe this; “Discharging”
alone does not prove the charger is disconnected.

Settings are in `/etc/tabs3/battery.conf`. The low-battery power guard requests
an orderly shutdown after sustained critical discharge. Do not disable it to
hide a charging fault. PC USB is capped at 500 mA; a tested wall-powered hub
used a 1.5 A input limit. These are current limits, not measured wall watts.
Battery voltage × battery current measures cell-side power, not total adapter
input. Readings and behavior must be checked for your own cable/hub.

USB host/device selection is automatic on recent kernels. A separately powered
hub has hosted devices while charging the tablet, but hub takeover/replug and
USB 3 qualification are still open. [Hardware status](hardware-status.md).

## Updates, backups, and logs

```sh
sudo apt update
sudo apt upgrade
systemctl --failed
sudo journalctl -u tabs3-dashboard -b --no-pager
sudo journalctl -u tabs3-server-health -b --no-pager
sudo dmesg --level=emerg,alert,crit,err
```

The server profile configures security updates without automatic reboots and
excludes the custom hardware packages. A kernel `.deb` does not update the
actual boot partition. Use [maintenance](maintenance.md) for matched kernel,
modules, images, backup and rollback steps.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Black screen after idle | Touch/Power wake first; then dashboard and screen service logs over SSH |
| No USB adapter | Data cable, tablet power and USB role; unplug/replug once; try known Wi-Fi address |
| SSH rejects key | Correct `dev` vs recovery `root`, selected key, permissions, host fingerprint |
| No Wi-Fi | `iwctl device list`, firmware and `tabs3-wifi-board` logs |
| Missing sensor values | Sensor package, same-device firmware/registry; do not treat dashes as zero |
| Plugged in but discharging | External-power status, keeper mode and actual current; charging can be intentionally inhibited |
| Service active but display broken | Inspect kernel GPU/display errors too; an active process is not proof of a working panel |

When reporting a problem, include versions, exact reproduction and redacted
logs. See [CONTRIBUTING.md](../CONTRIBUTING.md). Do not post credentials,
calibration, serial numbers, Wi-Fi profiles or full private backups.
