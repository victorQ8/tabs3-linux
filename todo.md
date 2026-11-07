# TabS3 Linux to-do

One plan, kept short. The detailed log is `docs/hardware-sm-t825.md`, the
evidence is in `docs/*-validation-*.json`, the patches are in
`kernel/PATCHES.md`. Update this file in the same commit as the work it
describes; do not add a second list elsewhere.

**State (2026-11-05).** Debian 13 runs as a console/server on the SM-T825
from internal storage: kernel package 80 (boot partition and modules),
`tabs3-base` 0.1.35, `tabs3-dashboard` 0.1.9 (five themes, camera wake),
`tabs3-sensors` 0.1.1.
Branch `drivers-62` holds everything since the public `display-bringup` tip.
The tablet is mounted upright permanently; the book cover folds behind it.

## When you are home (about fifteen minutes at the tablet)

1. [x] **Flash kernel package 68** (done 2026-10-15 09:47: the battery
       keeper's forced descent from a full battery; 67 on 2026-10-14 22:32 with
       two thermistors, 66 with the rear focus actuator, 65 with the front
       camera). The procedure, for the next package:
       ```sh
       scp artifacts/linux-tabs3_6.18.56-68_arm64.deb dev@172.16.42.2:/tmp/
       ssh dev@172.16.42.2 'sudo apt install -y /tmp/linux-tabs3_6.18.56-68_arm64.deb && sudo systemctl reboot --reboot-argument=recovery'
       sleep 40   # recovery answers on the same address
       tools/recovery-ssh 'cat > /tmp/boot.img' < private/images/package68/tabs3-internal-gpu-boot.img
       tools/recovery-ssh 'tabs3-recovery flash-boot /tmp/boot.img && tabs3-recovery reboot'
       ```
       Then on the tablet: `sudo cat /sys/kernel/debug/mmc1/ios` says SDR104,
       `CAM=front tools/camera-capture-test` captures with the screen off and
       `sudo tabs3-snapshot --camera rear x.png` reports a focus position.
2. [x] **Vibration:** buzzes (owner felt the pulses, 2026-10-14 17:44;
       `tools/vibration-test`).
3. [x] **Cover magnet:** three closes and opens on 2026-10-14 17:44; the screen
       went off within a second of each close and lit on each open.
4. [x] **Tilt:** gyroscope and magnetometer both moved far beyond noise while
       the owner handled the tablet (2026-10-14 17:43-17:46).
5. [ ] **Ears:** [x] speakers: the LL/LR pair is on the right of the screen in
       the landscape mount and UL/UR on the left (owner, 2026-10-14);
       `/etc/asound.conf` (`tabs3-base` 0.1.23) routes stereo accordingly and
       is the default output, mixer state stored for reboots; [x] 24-bit
       playback is audible but quiet (sample-container mismatch suspected,
       16-bit stays the format); [x] headphones: left, right and both
       heard cleanly (owner, 2026-10-14 18:12).
6. [ ] **SIM:** insert it, `sudo tabs3-modem-status`, then try SMS over QMI.
7. [ ] **Recovery:** [x] the "Enter fastboot" tile is on the menu and works
       (owner, 2026-10-14); [x] Home + Volume Up + Power during power-on
       enters recovery (owner, 2026-10-14 18:17; verified over USB).
8. [x] **microSD hot insertion:** three pulls and reinsertions on 2026-10-14,
       each re-detected at SDR104 within ten seconds, no stuck card; a udev
       rule (`tabs3-base` 0.1.24) mounts `/srv` again when the card appears.
9. [ ] **GPS:** only if the tablet can sit by a window for fifteen minutes.
10. [x] **USB host with the charger** (2026-10-15, owner's adapters): the
        Ethernet adapter (Realtek RTL8156) got an address in 11 s and moved
        60 MB at 16.9 MB/s against Wi-Fi's 11.8; a four-port hub with HDMI and
        a Type-C power input works as a hub, but with the wall charger in its
        Type-C port the tablet saw no power at all (a hub only feeds upstream
        after a PD negotiation, which needs the s2mm005). Host mode on
        battery alone was about 800 mA with traffic; item 11 ended that.
11. [x] **USB-C hub** (2026-10-15 12:20): package 71 RAM-booted with the PC
        cable, written to the boot partition, then the hub with its charger:
        `tabs3-usb-host host` turned the tablet's VBUS on, the hub took the
        source role 70 ms later, the data roles swapped and the hub
        enumerated by itself with the charger online at 1.5 A
        (`docs/kernel71-validation-20261015.json`). After a reboot with the
        hub in, the tablet charges at once but the USB role is the boot
        default until the tool runs: item 13.
12. [x] **Camera wake** (owner, 2026-10-15 13:59): a wave at the dark
        tablet without a sound woke the screen, "camera: 32 % of the
        picture changed"; two wakes earlier that afternoon were the owner
        moving about (19 % and 5 %). `WAKE_ON_CAMERA=0` in
        `/etc/tabs3/dashboard.conf` turns it off, `CAMERA_CHANGE_PERCENT`
        (3.5) tunes it. The dashboard shows no camera picture (owner's choice).
13. [x] **USB role from the controller** (packages 72 to 76, 2026-10-15):
        the s2mm005 driver sets the USB role itself from the controller's
        data role. The chip's blips as the tablet's own 5 V comes on (a
        short detach, then a sink attach with the policy engine still
        detached) made the first version loop; since package 76 the host
        role is let go only after a second, those blips neither pause the
        boost nor fill the log, and the Ethernet adapter is hosted as it
        attaches while the hub takes over and charges at the first try,
        on plug and at boot (`docs/kernel76-validation-20261015.json`).
        The charger refuses the boost below 15 %. Codex's package 73 (the
        GPU ring fix, patch 0043) is in every package since.
14. [x] **Dashboard: say when the battery is being run down** (owner,
        2026-10-15: with the hub in, the panel said not charging while the
        keeper's descent from 94 % ran): show "on external power, running
        down to 80 %" from the charger's `charge_behaviour`. Dashboard 0.1.9
        installed 2026-10-15: every theme distinguishes the active descent
        (configured target) and inhibited/resting battery from missing power;
        five host tests and native-size previews passed. Charger policy unchanged.
15. [ ] **USB 3 with a USB 3 device (check later):** the M.2 SSD
        enclosure's USB-C cable straight into the tablet, no hub; I read
        `lsusb -t` for a 5000M device and time a read of the drive (read
        only, nothing mounted). If it stays at 480M, turn the plug over
        once: if only one way links, the lanes need switching. On disk
        since package 78: the USB 3 PHY on and clocked, the redriver on
        (PM8994 GPIO 14) while a partner is attached. Not tried yet: the
        OTG adapter and the hub are USB 2 (2026-10-15).
16. [ ] **Flash pulse (package 80, on disk 2026-10-15):** the torch works
        (owner, 20:17: `echo 5 | sudo tee /sys/class/leds/white:flash/brightness`
        lit it at 50 mA; 18 steps of 10 mA to 180 mA, 0 off). The flash
        controls are there since package 80 (`flash_brightness`,
        `flash_timeout`, `echo 1 | sudo tee .../flash_strobe`, 1.2 A and
        800 ms at most); one 600 mA, 400 ms pulse fired at 20:34 with the
        chip's flash boost confirmed. Left: the owner's look at one pulse.
17. [x] **PC after a hub session** (2026-10-15 20:43): the PC sees the
        tablet again by itself after the hub (package 80's data switch
        routing as Samsung's MUIC driver does, and `tabs3-base` 0.1.31's
        USB 2-only gadget; `docs/kernel80-validation-20261015.json`).
18. [ ] **Hub and its charger (check later):** on 2026-10-15 at 20:11,
        20:34 and 20:43 the hub did not take over the power with its wall
        charger in, and the tablet powered it from its battery (about
        1 A); at 12:20, 12:54 and 15:19 it did at the first try. Check the
        charger's cable at the hub's Type-C power input, then plug the hub
        in: the tablet should say Charging at the 1.5 A limit within two
        seconds.

## Hardware functions

The owner requires all hardware paths end to end. "Works" below means the
listed functional evidence exists, not full production qualification. Each
path must also survive repeated use, cold boot, recovery and relevant power
transitions. Current evidence and test limits are in
`docs/hardware-sm-t825.md` (2026-11-05 section). Missing accessories and firmware
limitations remain open; they are not waived because the dashboard is usable.

| Function | State | Notes |
|---|---|---|
| Panel, brightness, blanking | works | AMS968HH01 over dual DSI; calibrated levels |
| GPU (Adreno 530) | partial | accelerated rendering demonstrated; prior faults, 0043 serialization fix included since package 73; sustained qualification and display handoff still open; emulation retired |
| Touchscreen (Synaptics S5807) | works | |
| Buttons, touch keys, key backlight | works | |
| S Pen (Wacom W9019) | works | hover, pressure, tilt; no consumer on the console |
| Hall switch (cover) | works | closing the cover sleeps the screen, opening wakes it (checked by the owner) |
| Wi-Fi (QCA6174, PCIe) | works | |
| Bluetooth | works (HID) | Xbox paired and buttons/navigation/wake confirmed by owner; audio profiles and reconnect after cold boot still need qualification |
| USB device (SSH over USB) | works | |
| USB host (Ethernet adapter, hub) | partial | automatic role and RTL8156 transfer at 16.9 MB/s demonstrated; powered-hub takeover later failed intermittently, so item 18 remains open |
| USB 3 SuperSpeed | unverified | PHY and redriver enabled since package 77; need a known USB 3 device/cable, both plug orientations, 5000M link and transfer; gadget intentionally limited to high-speed for reliable rescue |
| eMMC (HS400) | works | |
| microSD | works | UHS-I SDR104 (package 64), hot insertion 3 of 3; `/srv` data disk, remounted on insertion |
| Speakers (4x RT5508) | works | stereo mapped for the landscape mount (`speakers` ALSA default); -10 dB ceiling, no protection algorithm |
| Headphones (WCD9335) | works | left and right heard cleanly; no jack detection in mainline, so the path is always offered |
| Microphones (ADC3/ADC4) | partial | live capture works but close/reopen can stall or return silence; 0046/0047 audio candidate built and host-tested, not installed; gain/SNR still limited |
| Modem (MPSS) | partial | boots, SIM and QMI; no data (IPA v2.5 missing); SMS and voice untried |
| GPS (modem QMI location) | partial | engine starts but no indications in a 15 min indoor test; antenna/firmware/assistance and outdoor fix need diagnosis |
| Battery gauge and charger (SM5705) | works | termination and health tests open; no AFC 9 V |
| Sensors | see below | |
| Grip sensor, LTE (SX9310) | works | bound by `tabs3-grip-sensor.service` at 11.8 s |
| Grip sensor, Wi-Fi (SX9310) | won't | nothing answers on TLMM 49/50 |
| Rear camera (IMX258) | works | streams since package 63; exposure loop and contrast autofocus (DW9807 at 0x0c since package 66, `tabs3-snapshot --camera rear`); module EEPROM readable while the lens is held; the folded cover covers its lens in the mount |
| Front camera (S5K5E3YX) | works | package 65: 2576x1932 at 30 fps and 640x480 at 120 fps through CSIPHY2 and CSID1; exposure loop (`tabs3-snapshot`) and the dashboard's presence wake (`tabs3-dashboard` 0.1.6, no picture on the panel) |
| Flash and torch LED (SM5705 FLED) | partial | torch seen by owner; package 80 pulse registers and timed shutoff checked at 600 mA/400 ms, visual confirmation pending (item 16) |
| Vibration motor | works | rumble through the force-feedback interface, felt by the owner |
| Video codec (Venus) | partial | installed package 80 still has encoder faults; temporary 81~drivers2 modules pass H.264 through 1080p, 300-frame encode, three reopen cycles, VP8 file/container output and 60-frame hardware decoding; exact output counts verified; original modules restored, full candidate boot/soak pending |
| Thermal sensors and throttling | works | 20 zones (TSENS, PMIC die, skin, battery, charger, LTE power amplifier and crystal thermistors since package 67) |
| Hardware watchdog | works | CPU0 stays in shallow idle for it |
| RTC | works | read-only RTC, offset file restores the time |
| CPU idle | works | WFI and per-core power collapse on CPU1-3 |
| Crypto engine (QCE/BAM) | incomplete | disabled after BAM probe failure; secure ownership, register/pipe mapping and known-answer hardware tests required; CPU crypto remains usable |
| Hardware random generator | limited by upstream support | `qcom,prng-ee` is deliberately not exposed as trusted entropy by this kernel; a driver bind alone cannot create a hardware entropy source; never relabel it `qcom,trng` |
| Keyboard cover (STMPE1801 keypad) | no | not attempted; needs the keyboard cover |
| Native USB-C video out | hardware path unproven | Samsung lists MHL as unsupported; shared SoC HDMI/controller nodes do not establish board wiring; investigate before promising a driver |
| Fingerprint (Egis ET5xx) | incomplete | SPI pins owned by TrustZone; needs a supported secure transport and a userspace enrollment/matching path |
| ANT+ | unverified | listed in Samsung's SM-T825 specifications; firmware transport and a real accessory test not yet established |
| NFC, FM radio, MST | none | pin states only in the stock tree; not on this model |

### Sensors, end to end

The sensor DSP (SLPI) reports exactly four sensors; the others are wired to
the application processor.

| Sensor | Chip and path | Kernel | Consumer today | Physically checked |
|---|---|---|---|---|
| Accelerometer | ST K6DS3TR, SLPI | `qcom-smgr-accel` | iio-sensor-proxy (rotation); dashboard motion wake (off on the mount) | yes, rotation |
| Gyroscope | ST K6DS3TR, SLPI | `qcom-smgr-gyro` | none | yes, moves with the tablet |
| Magnetometer | AKM AK09916, SLPI | `qcom-smgr-mag` | none | yes, moves with the tablet |
| Light | Capella CM3323, SLPI | `qcom-smgr-light` (lux) | dashboard presence wake | yes, hand over the sensor; RGB channels not exposed |
| Hall switch | GPIO | `gpio-keys` SW_LID | `tabs3-screen` | yes, three close/open cycles with owner |
| Grip, LTE | SX9310, bit-banged I2C | `sx9310`, 4 proximity channels | none | reads; no hand test |
| Touch | Synaptics S5807, RMI4 | input | screen wake, console | yes |
| Pen | Wacom W9019 | `wacom_i2c` input | none on the console | yes, drawing |
| Front camera | S5K5E3YX, CAMSS | `s5k5e3` V4L2 | dashboard presence wake (motion), `tabs3-snapshot` | yes; a wave woke the screen 2026-10-15 |
| Thermistors | PM8994 VADC and TSENS | thermal zones | throttling, dashboard | yes; the stock tree's quiet_therm channel is unpopulated |
| Battery | SM5705 fuel gauge | power_supply | dashboard, charger | yes |

## Next, in order

1. [x] **Flash kernel package 63** (2026-10-14 13:02, recovery `flash-boot`,
       readback verified); the screen-off capture from disk passed.
2. [x] **Owner's physical checks:** all but the SIM done 2026-10-14 (see the
       at-home list).
3. [x] **Cover closes, screen sleeps:** `tabs3-screen` acts on SW_LID
       (`tabs3-base` 0.1.21), checked by the owner.
4. [ ] **Presence wake, next sources:** [x] sound-level trigger from the
       microphone (`tabs3-dashboard` 0.1.3, 2026-10-14: a tone through the
       speakers woke the screen from 17 dB over the room floor); [ ] Bluetooth
       proximity to the owner's phone (needs the phone's address and the owner
       nearby). The grip sensor only covers a hand at one edge.
5. [ ] **GPS:** 2026-10-14, from the mount, no SIM: the QMI LOC session starts
       (engine lock none, mode set to standalone, NMEA types already gga, rmc,
       gsv, gsa, vtg) but delivers no indication at all in 15 min, not even
       empty sentences. Next: look for a GNSS enable or antenna pin in the
       stock tree, then ModemManager by a window or outdoors with assistance
       data. Never record coordinates.
6. [ ] **Cameras, remaining:** [x] exposure loop for both (`tabs3_camera`,
       2026-10-14), [x] `tabs3-snapshot` (the dashboard's corner picture of
       0.1.5 was removed in 0.1.6: the owner wants the camera for the wake
       only), [x] camera presence wake (the owner's wave test pending);
       [x] rear: DW9807 autofocus (package 66: the actuator answers at 0x0c,
       the stock 0x18 was its 8-bit address; contrast sweep in `tabs3-snapshot`,
       `tabs3-base` 0.1.26); [x] libcamera: 0.4's software ISP goes dark and
       green here, 0.7.2 built on the tablet works on both cameras and is
       installed under `/usr/local` (no autofocus in its simple IPA; the
       dashboard and `tabs3-snapshot` keep the raw path).
7. [ ] **Audio polish:** [x] capture gain measured 2026-10-14 with a tone: the
       analog `ADC3 Volume` 12 to 20 adds 9 dB of signal and 11 dB of noise
       (floor -63 to -52 dBFS), and the mainline WCD9335 driver has no digital
       capture volume, so the default stays 12 (quiet recordings, best SNR);
       [ ] speaker left/right in the mounted landscape orientation (Home key
       on the right: left speakers are the UL and UR amplifiers, right ones LL
       and LR; done, see the at-home list); [x] 24-bit playback audible but
       quiet; [ ] closing any capture stalls the DSP 5 s
       ("CMD 10bcd timeout") and the next one can come back silent (kernel
       q6asm; the dashboard avoids it by never closing). Candidate 81~audio1
       backports the missing upstream close-response fix and corrects the
       positive APR success return that skipped FLUSH. Host regression and
       full build passed; hardware repeated capture/playback test remains.
8. [ ] **Modem:** try SMS over QMI (no data path needed); voice later.
9. [x] **Torch LED** on the SM5705 flash driver; flash pulse visual check is
       still item 16 above.
10. [ ] **Keyboard cover:** STMPE1801 keypad at I2C 0x40 (TLMM 2/3), mainline
        `stmpe` MFD and keypad drivers; needs the keyboard cover.
11. [x] **microSD:** UHS-I SDR104 at 1.8 V since kernel package 64 (flashed
        2026-10-14; 59 MB/s reads); hot insertion 3 of 3 with the owner, the
        earlier stuck-card failures did not reproduce (patch 0019's retry stays).
12. [x] **USB host and charging at the same time:** the s2mm005 USB-C
        controller is described (package 69) and driven (patch 0042, packages
        70 and 71, flashed 2026-10-15): the owner's hub takes over VBUS, the
        tablet charges at the 1.5 A limit while it hosts the hub's ports,
        the SM5705 MUIC's switch held on USB meanwhile. The driver setting
        the USB role itself followed in package 72. USB 3 still needs a
        SuperSpeed partner test; native video output is not established.
13. [x] **Board thermistors** (owner asked 2026-10-14): the LTE power
        amplifier's and the crystal's are thermal zones since package 67; the
        stock tree's "quiet" channel is not populated on this board. No other
        sensor chip is missing from the tables above.

## Server platform (decided 2026-10-14)

- [x] **Data disk:** the 128 GB microSD is wiped and formatted ext4
      (label `tabs3-srv`), `/srv` in fstab with `nofail` and remounted by a
      udev rule on insertion (no autofs); SDR104 since package 64, TRIM works.
- [x] **Battery window:** `tabs3-battery-keeper.timer` inhibits charging at
      80 % and resumes below 65 % (`/etc/tabs3/battery.conf`); since kernel
      package 68 and `tabs3-base` 0.1.27 a battery above 83 % is run down to
      80 % on the tablet's own load, cable in (the charger's force-discharge,
      which ends itself at 15 %), because the owner found it stuck at 100 %
      for a day. Started 2026-10-15 09:48 from 100 %, 94 % at noon: the
      first descent is to be checked (expect 80 % the same afternoon). The
      health check knows the descent since `tabs3-base` 0.1.29 (no false
      "draining on external power" notice).
- [x] **Alerts:** panel only (the owner's choice); the dashboard turns amber.
- [ ] **Role:** not chosen yet; see the conversation of 2026-10-14.

## Server qualification (open)

- [ ] Production release candidate (2026-11-05): base 0.1.35 installed with
      sustained-drain battery shutdown protection and continuous qualification
      checks; verified off-device backup and daily appliance backups in place.
      Offline boot-fsck image built and staged, awaiting RAM/disk validation.
      Physical power/recovery and 72-hour gates remain open; see
      `docs/production-readiness.md`.

- [ ] Longer soak under the intended workload: router outages and reconnect,
      storage checksums, memory pressure, disk-full handling, filesystem-error
      policy; sustainable wall-powered load (capped runs passed, see
      `docs/server-platform-audit-20261013.md`).
- [ ] Battery: full-charge termination and recharge, current accuracy, health,
      low-battery shutdown, restart after a long power interruption.
- [ ] Qualify removal of `clk_ignore_unused` and `pd_ignore_unused` and a
      minimal firmware/service set; the modem, ADSP and SLPI stay.
- [x] Recovery hardening after Codex's audit (2026-10-14): image validation,
      operation lock, USB rollback, backup superblock, no journal replay on
      read-only mounts, UI and init fixes; installed and checked
      (`docs/recovery-fastboot.md`).
- [ ] ramoops retention and watchdog recovery (a saved console had damaged
      bytes); self-rescue into recovery when the USB network never comes up.
- [ ] Kernel update path: flash only validated images; off-device alerts and
      recurring backups of service data.
- [ ] Watch: the s2mm005 cycles its state every half second while the
      tablet sources to a partner without PD (the Ethernet adapter): quiet
      since package 76, the data path does not notice; the stock driver may
      tell the chip about VBUS (research NOTES.md section 15 has nothing yet).
- [ ] Watch: the intermittent `pclk0_clk_src: rcg didn't update its
      configuration` warnings at panel probe (one boot in five, display fine);
      the single autofs oops boot loop of 2026-10-14 (hang detectors and
      `panic=30` now reboot the tablet instead of wedging it).

## Full-device driver work

- **Native USB-C video out:** establish whether this board has a video path.
  Samsung specifies no MHL; do not infer a wired display feature solely from
  the SoC HDMI block or a controller driver used by other Samsung products.
- **LTE data:** an IPA v2.5 driver; mainline supports v3 and later only.
- **Fingerprint:** qualify secure ownership/transport before accessing the
  reserved SPI pins, then enrollment and matching in Debian.
- **Other gaps:** GNSS indications/fix, SIM-dependent SMS/voice, headset jack
  detection and Bluetooth audio, keyboard cover, RGB light channels, ANT+,
  hardware crypto and system suspend/resume remain part of the requested scope.
- **Desktop (Phosh):** works, retired as the default; open items in
  `docs/gpu-desktop-20261011.json`.

## Housekeeping

- [ ] Merge `drivers-62` (and the older `display-bringup`) into `main`;
      packages 63 to 65 are flashed and checked.
- [ ] `config/device.json`: display and touch status fields.
- [ ] `scripts/install-internal.py` still assumes TWRP; move installing to the
      tabS3 recovery; verify images before pausing; drop caches before readback.
- [ ] Boot-time root filesystem check: conservative preen and recovery fallback
      implemented/tested in the 2026-11-05 candidate; not yet flashed/boot-tested.
- [ ] Upstream candidates (`kernel/PATCHES.md`, generic scope): prepare only;
      nothing is sent without the owner's review and Signed-off-by.
- [ ] Decide `tabs3-wifi-pcie.service`; document where Wi-Fi credentials live.
- [x] `tabs3-dashboard-theme` saves the choice in `/var/lib/tabs3-dashboard/theme`
      (0.1.4); it used to edit the conffile, which made the 0.1.3 upgrade keep
      the old settings file.
- [ ] Display leftovers: cold-temperature panel voltages and high-brightness
      mode, panel error line (no ESD recovery), the DPU disabled-encoder log at
      every screen wake, mDNIe colour modes.
