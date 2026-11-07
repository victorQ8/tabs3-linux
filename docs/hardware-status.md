# Hardware status

Evidence through **2026-11-05**, on one **SM-T825 rev05**. “Verified” below
means the stated function passed a bounded test; it does not mean every mode,
accessory, workload, or long-running use is qualified.

The last recorded installed kernel is `6.18.56-80`, with base `0.1.35` and
dashboard `0.1.9`. This repository builds `6.18.56-81~drivers2`. Its complete
boot image has not been installed or boot-qualified; candidate video modules
were tested temporarily and the original modules restored.

| Component | Observed result | Remaining work |
| --- | --- | --- |
| Internal Debian boot | Internal storage, software reboot, USB/Wi-Fi SSH verified | Candidate boot, recovery/fsck path and production soak |
| AMOLED | 2048 × 1536, calibrated brightness, blank/wake and dashboard verified | Longer endurance; high-brightness/cold-voltage modes absent |
| Touch / S Pen | Touch, pen hover/pressure/tilt physically checked | Broader application qualification |
| Buttons / cover | Power, Home, Volume, touch keys and hall switch checked | Keyboard-cover accessory not tested |
| Adreno 530 | Accelerated rendering and shared-buffer lifetime fixes tested | Longer soak and broader workloads; not Vulkan qualification |
| eMMC / microSD | HS400 eMMC; SDR104 SD and hot-insert checks; 32 MiB file write/readback passed on both | Broader cards, workloads and endurance |
| Wi-Fi | Connectivity, SSH and factory address restoration verified | Broader AP/roaming qualification |
| Bluetooth | Xbox controller pairing and input verified | Audio and reconnect/endurance qualification |
| USB 2 | PC network gadget and host Ethernet tested | Cable/role-transition matrix and repeated hub takeover |
| Powered USB hub | Hosting while charging observed | Intermittent takeover still needs qualification |
| USB 3 | PHY/redriver support enabled in source | No qualified 5 Gbit/s link in both orientations |
| Battery / charger | Reporting, thermal cutoffs, charge control and keeper tested | Varied chargers, power loss, restart and long soak |
| Speakers / headphones | Four RT5508 speakers and headphone playback tested | Headphone detection; broader audio lifecycle |
| Microphones | Capture produces audio | Close/reopen stalls or silence; candidate fixes await hardware test |
| Cameras | Front/rear frames and physical wave checks passed | Full application pipeline and endurance |
| Sensors | Accelerometer, gyro, magnetometer, light and grip return data; rotation tested | Calibration/performance across modes; RGB/ANT+ unqualified |
| Temperature / cooling | SoC and board thermal readings and CPU/GPU cooling tested | Long production workload qualification |
| Vibration / torch | Vibration and visible 50 mA torch tested | Flash pulse has register evidence; visual confirmation pending |
| Video codec | Candidate H.264 encode/decode and VP8 encode passed bounded tests | Full boot, all codecs/resolutions/concurrency and endurance |
| Modem | Firmware boots with read-only EFS service | IPA 2.5 mobile-data driver missing; SIM/SMS/voice not qualified |
| GNSS | Engine can start | No position fix in recorded test; not working end to end |
| Fingerprint | Hardware identified | Secure transport/userspace integration missing |
| Suspend | Deliberately disabled in appliance profile | Reliable suspend/resume not qualified |
| QCE / hardware RNG | Conservative configuration | Crypto ownership/BAM unresolved; PRNG is not treated as trusted hardware entropy |
| External display | No qualified path | No supported external-display promise |

CPU0 uses WFI for watchdog reliability; other cores retain deeper idle.
The appliance profile is intentionally a console/dashboard system. Optional
desktop support does not change the hardware qualification above.

## Evidence and open release gates

- [Detailed hardware notes](hardware-sm-t825.md): driver provenance and dated tests.
- [Production readiness](production-readiness.md): backup, power, reboot,
  offline filesystem and 72-hour observation gates; **not yet passed**.
- [Data-path measurements](driver-data-paths-20261105.json): sensors/storage.
- [Video validation](driver-video-validation-20261105.json): both failed earlier
  attempts and the successful `final_candidate` results. Earlier failure
  entries are preserved; read them with that final section.
- [Patch stack](../kernel/PATCHES.md): carried fixes and sources.

The video candidate completed H.264 runs up to 1920 × 1080 for 60 frames,
640 × 480 for 300 frames, three reopen cycles, VP8 encoding, and bounded H.264
decoding. Independent decoding checked frame counts; this is not an endurance
or complete-codec qualification. The microphone patches have host tests only.

A loaded driver, a firmware process marked “running,” or an active systemd
unit alone does not establish that its hardware data path works.
