# AMS968HH01 panel: how it works, and why ours misbehaves

The SM-T825 panel is a Samsung AMS968HH01 AMOLED (2048x1536) driven by an
Anapass ANA38401 display driver IC (DDI) over two DSI links in command mode.
This document is the reference for how Samsung drives it and how our mainline
driver differs. It was written on 2026-10-11 from Samsung's GPL kernel for
this tablet, read line by line, and the tablet's own stock device tree.

Sources:

- Samsung kernel: [awesometic/android_kernel_samsung_msm8996](https://github.com/awesometic/android_kernel_samsung_msm8996/tree/f48aec90fcebf4615fdee4a8abac7339930db856)
  at `f48aec90`, `drivers/video/msm/mdss/` and
  `drivers/video/msm/mdss/samsung/ANA38401_AMS968HH01/`.
- The panel node of the tablet's stock DT (`private/backups/20261010T094140Z/live.dts`,
  from line 3276). It is byte-identical to the dtsi in that kernel; the
  `_usa` variant is not used.
- Our driver as on the tablet on 2026-10-11 (patches up to `0027`),
  saved as [`panel-ams968hh01/ours-20261011.c`](panel-ams968hh01/ours-20261011.c).

Detailed, line-cited reports:

- [Power-on, first frame, sleep and wake](panel-ams968hh01/lifecycle.md)
- [Brightness and colour](panel-ams968hh01/brightness.md)
- [DSI transport and timing](panel-ams968hh01/transport.md)

Tags used below: **[proven]** = stated by Samsung's source or the stock DT;
**[seen]** = observed on our hardware; **[inferred]** = our explanation, not
yet confirmed by an experiment.

## 1. How Samsung drives the panel

### Wiring [proven]

| Signal | Pin |
|---|---|
| Panel supply (3.3 V, fixed regulator) | TLMM 46 |
| Reset (released high, no low pulse) | TLMM 143 |
| TCON ready (input, polled after reset) | TLMM 45 |
| Tearing effect (TE) | TLMM 10 |
| Error/ESD line (falling edge means the panel needs re-initialising) | TLMM 121 |

All commands and reads go to the left link (DSI0) only; nothing is
broadcast. Pixel data uses both links.

### Registers [proven]

Most settings are not DCS commands but a two-step write: `B0 nn` sets an
offset ("global parameter"), then a long write `B1 vv` or `B2 vv` stores the
value in one of two banks at that offset. Brightness settings take effect
together when the update key `B0 35 / B2 01` is written; it is always the
last packet.

### Power-on [proven]

Every power-on, including every wake from screen-off, is a cold start:

1. Panel supply on, 10 ms.
2. Both DSI links up with **every lane, clock lane included, held in
   low-power stop state (LP-11)**.
3. 75 ms, then reset released, then TCON ready polled (up to 1 s).
4. Only now the continuous high-speed (HS) clock is started on both links.
5. First boot only: panel ID and calibration (MTP) reads, before any
   initialisation.
6. The on-command list, in low-power (LP) mode: dual-link and compression
   setup (`B0 51 / B1 06`, `B0 D9 / B1 08`), tear line, a neutral gamma,
   AID for 360 nit, ELVSS `0x0F`, ACL off, CAPS, update key, the internal
   clock (`B0 D0 / B1 1D`), 215 ms, then display on (`29h`).
7. Immediately, in HS: the **brightness block** (below) and the mDNIe colour
   tables, then tear-on (`35h`).
8. The first frame within about one TE period (16.7 ms).
9. The brightness block again after that first frame.

There is no sleep-in/sleep-out (`10h`/`11h`) anywhere, and no workaround for
the dual-link or compression setting: Samsung writes it once per power-on.

### The brightness block [proven]

Brightness is not one value but a set that must match:

| Order | Packet | Meaning |
|---|---|---|
| 1 | `90 HH 00 LL` | AID (emission duty) for the level |
| 2-7 | `B0 4D / B2 05`, `B0 49 / B2 7F`, `B0 36 / B2 12` | ACL (automatic current limit): 32-frame average, starting at 50 %, 15 % |
| 8-9 | `B0 67 / B2 xx` | ELVSS (OLED cathode voltage) for the brightness, ACL state and temperature |
| 10-11 | `B0 6D / B2 81` or `85` | CAPS |
| 12 | `83` + 33 bytes | gamma for the brightness, computed from the panel's own calibration (smart dimming) |
| 13-14 | `B0 35 / B2 01` | update key |

ACL is on by default (15 %). At room temperature and 360 nit, ELVSS is
`0x1B` with ACL on (`0x19` with ACL off). **`0x0F`, the value in the
on-command list, is the 360 nit value for −20 to 0 °C.** Samsung replaces it
before the first frame and never shows content with it. Android on this
tablet ran at level 86, which is 111 nit, with ACL on.

The AID values are only valid together with the gamma of their own level.
Our earlier note that AID `c9` gives 51 nit is wrong on the 360 nit gamma;
it gives roughly 190 nit.

### Screen off and wake [proven]

Screen off: brightness block for 2 nit, wait for the last frame, tear-off
(`34h`), display off (`28h`, HS) and 100 ms, reset low and 5 ms, panel supply
off and 25 ms. **The panel is unpowered while the screen is off.** Wake is
the full power-on above. Samsung has no "display off but powered" mode for
this panel. A falling edge on the error line (TLMM 121) triggers a full
re-initialisation.

### Transport [proven]

- Only the on-command list and tear-on go out in LP, and only before the first
  frame. Everything sent while running (brightness, colour, display off) is HS.
- LP and HS differ only in one bit of the DSI controller's command-DMA
  register. Mainline sets it per message exactly as Samsung does, so there is
  no hidden transport difference.
- Samsung holds a lock across each whole command set, so a `B0` offset and
  its data write can never be separated by another sender.
- Reads happen only before the first frame.

## 2. What the pre-fix driver did differently (snapshot through 0027)

| # | Samsung | Ours | Status |
|---|---|---|---|
| 1 | LP-11 on all lanes through reset and TCON ready; HS clock started afterwards | Mainline starts the HS clock when the DSI host powers on, before our `prepare()` releases reset | **different** |
| 2 | Calibration reads before the on-commands, first boot only | HS reads after the on-commands, before display on | different |
| 3 | `29h` directly after the 215 ms wait | `29h` later, in `enable()` | different |
| 4 | HS brightness block right after `29h`, before any frame | None, or later (fixup step, or patches `0023`–`0027`) | **different** |
| 5 | First frame within one TE | Whenever the first DRM commit arrives (0.9–3.5 s at boot) | different |
| 6 | No compression toggle | Toggle 5 s after enable (fixup, patches `0009`–`0015`) | extra |
| 7 | Screen off = full power-down; wake = cold start | `28h`/`29h` with the panel powered (backlight device, `0019`) | **not stock** |
| 8 | Error line watched; full re-init on a falling edge | TLMM 121 reserved in our DTS, not watched | missing |
| 9 | Each command set atomic (one lock) | `B0` + data pairs from the fixup worker, `bl_power`, debugfs and enable/disable can interleave | **bug** |
| 10 | Brightness levels with matching AID/ELVSS/gamma/ACL | Fixed 360 nit | missing |
| 11 | mDNIe `UI_AUTO` (bypass plus a small white-point trim) | Bypass | minor |

## 3. Measured causes and the package-28 implementation

The source analysis below is retained as the experiment history. The later
[retention tests](panel-lifecycle-measurements-20261011.json) and
[clock-order/physical validation](panel-lp11-validation-20261011.json)
supersede the initial hypotheses:

- **Startup:** two fixup-disabled boots lacked the intended dual-link,
  compression and drive values. Deferring both continuous clocks until
  after reset release and TCON_RDY made two further boots correct from
  their first visible text, with the intended register values and no
  fixup. Package 27 implements that order for SM-T825 and removes the timer.
- **Colour:** normal ACL/ELVSS remain necessary. They now arrive during
  initialization and the real recovery has correct colours. LP long writes
  were demonstrated to work on a settled screen; mode alone was not the
  cause of every failed earlier write.
- **Wake:** raw off/on did not erase the measured drive registers. The
  bright image nevertheless stayed dark, and one fresh frame did not
  recover it. Cutting the supply and repeating initialization did recover
  it. Package 27 uses that full lifecycle; physical Power/touch wake passed.
- **Rapid wake:** package 27 could skip clock setup when off/on happened
  before the hosts' 200 ms runtime-autosuspend. The original bad values
  returned. Package 28 rearms LP11 before every panel prepare; three
  immediate cycles then passed all eight link/drive register checks.
- **Serialization:** driver command lists now share one mutex. The old
  diagnostic single-packet interface is for quiescent measurements; do not
  interleave its separate offset/data calls with lifecycle changes.

The internal reason the DDI rejects/mishandles initialization under the
old clock order is not decoded. A supply-protection trip during failed wake
is not established: GPIO121 low with a pull-down is not proof. Package 29
adds calibrated normal brightness levels with a 111-nit target default;
see the [brightness measurements](panel-brightness-20261011.json). Temperature-based
panel settings and error-line recovery remain future work.

## 4. Experiments that settle the open points

All but the clock experiments use the existing debugfs command interface
(`/sys/kernel/debug/ams968hh01/cmd`, `lp` prefix for LP). Reads must be done
with frames stopped (console in graphics mode, no DRM clients), as in the
checks below.

### Results so far (2026-10-11, [`panel-experiments-20261011.json`](panel-experiments-20261011.json))

- **LP reads work** on a settled, static panel: `06 DA/DB/DC` returned the
  right, alternating ID bytes in LP and HS. This disproves a blanket HS-only claim; it does not establish that
  streaming alone explains every previous failure.
- **`B1`/`B2` cannot be read back.** `15 B0 nn` followed by a read of `B1` or
  `B2` (generic or DCS) returned whatever the previous read returned. This
  matches the stock source, which never reads `B1`/`B2` (below).
- Host registers match the expected values (DSI0/1 `CMD_DMA_CTRL`
  `0x14000000`, `TRIG_CTRL` `0x80001004`, clock lane forced HS). The error
  line (TLMM 121) reads low as an input with pull-down; DCS `0A` = 04,
  `0E` = 80, `0F` = 80. These were the early measurements; the later
  failed-wake comparison is recorded in the clock-order validation report.

### Reading panel registers the way Samsung does

Samsung reads only these, each as `15 B0 <offset>` followed by a generic read
`24 <register> <count>` [proven, stock dtsi]:

| Register | Offset, count | Contents |
|---|---|---|
| `D8` | `5A`, 33 (as 8+8+8+8+1) | gamma calibration (MTP) |
| `D8` | `7F`, 2 / `7B`, 4 / `81`, 1 | manufacture date / colour coordinates / HBM ELVSS |
| `D4` | `5B`, 33 | HBM gamma calibration |
| `D2` | `70`, 1 | value written back to `B2` at `70` when leaving HBM |
| `DA`, `DB`, `DC` | DCS read, 1 | panel ID |

So `B1`/`B2` are write banks; `D2` is the readable mirror of `B2` (R3).

| # | Purpose | Commands (frames stopped) | Reading |
|---|---|---|---|
| R1 | Validate the read method on known data | `15 b0 5a` + `24 d8 01 1`, then `15 b0 5b` + `24 d8 01 1`, alternating, with an ID read in between | must return `33`, then `51` (this panel's MTP, as the driver logs it), not the previous reply |
| R2 | What `D2` holds | `15 b0 70`, `15 b0 67`, `15 b0 36`, `15 b0 4d`, each + `24 d2 01 1` | values per offset |
| R3 | Is `D2` live? | `15 b0 36` + `39 b2 10` + `15 b0 35` + `39 b2 01`, read `D2` at `36`; then the same with `b2 12`, which leaves ACL on | follows the write: live mirror, so E2/E3 can use it; constant: factory defaults, so E2/E3 need visual or current measurements |

**R1–R3 passed** (2026-10-11,
[`panel-read-protocol-20261011.json`](panel-read-protocol-20261011.json),
[raw results](panel-measurements-20261011/r1-r3-results.txt)): `D8` returned
`33`/`51` in LP and HS; `D2` read `08` at `70`, `1b` at `67`, `12` at `36`,
`05` at `4D` (the drive state of Codex's current driver); and `D2` at `36`
followed a write from `10` to `12`. **`D2` is a live readback of `B2`.**

### Retention measurements (completed; historical experiment definitions)

Frames stopped for every read, as in R1–R3; each ends in the good state
(ACL `12`, ELVSS `1b`) or with a reboot.

| # | Question | Steps | Reading |
|---|---|---|---|
| R4 | Is `D1` the mirror of `B1`? | Read `D1` (`24 d1 01 1`) at `D0`, `51`, `D9`, alternating with known `D8` reads | `1d`, `06`, `08`: the dual-link and compression settings become readable |
| M1 | Does the compression change reset the drive settings? (E3) | On the good panel: `B1[D9]` = `00`, one frame, 1 s, `B1[D9]` = `08` and `B1[51]` = `06`, one frame, 1 s, then read `D2` at `67`, `36`, `4D` (and `D1` if R4 passed) | back to `0f`/`10`/`04` or other defaults: the re-latch discards drive settings, so they must follow it |
| M2 | Do display off/on reset them? (wake) | On the good panel: `28h` (HS), 100 ms, `29h` (HS), read `D2` | reset: explains the washed or dark wake |
| M3 | Did our LP initialisation land, and what holds it? (E2) | Boot with `options panel_samsung_ams968hh01 fixup=0` in `/etc/modprobe.d`; after boot read `D1`/`D2` and DCS `0A`/`0E`/`0F`; run the fixup by hand (debugfs `fixup`) and read again; remove the option and reboot | init values present while garbled: the DDI holds the right settings but has not latched them (points at the link/clock state); absent: the LP init was lost |

| # | Question | Experiment | Reading |
|---|---|---|---|
| E1 | Do LP long writes land? | On a settled panel: `lp 39 90 00 00 c9` (should dim), back with `39 90 00 00 0e` | dims: LP works |
| E2 | Did our LP initialisation land? | Only if R3 shows a live mirror: boot with `fixup=0`, read `D2` at `4D`, `36`, `67` | values present: the init landed, the latch is the problem |
| E3 | Does the compression toggle reset the drive registers? | On a correct panel, toggle `D9` by hand, then read `D2` (if live) and measure the battery current | colours go bad or current rises: confirmed |
| E7 | Is the HS clock at reset the cause? | In the garbled state, drop and restore the clock-lane HS force on DSI1, then DSI0 (`devmem`, bit 28 of `0x009960ac` / `0x009940ac`) | becomes dual-link: supports clock-state involvement, not proof of reset cause |
| E8 | Fix for E7 | Keep both clock lanes out of HS until TCON ready (small msm DSI host hook), boot with `fixup=0` | clean from the first frame |
| E13 | ACL or ELVSS? | On a bad panel, send ACL alone, then ELVSS alone (each with the update key) | which one removes the lines and the current |
| ESD | What happens on a failed wake? | Unreserve TLMM 121, log its edges, read DCS `0A`, `0E`, `0F` after the flash | a falling edge: correlate with the fault; cause still needs confirmation |
| Race | Real-world impact of row 9 | Toggle `bl_power` repeatedly in the first 8 s after enable | capture an actual interleaved offset/data pair before attributing a fault |

## 5. The driver we should end up with

Once E1–E8 confirm the above:

1. **Power-on in Samsung's order**: supply, LP-11 clock lanes through reset
   and TCON ready, then HS; calibration read once before the on-commands;
   the on-command list with `29h` at its end; the HS brightness block
   straight after; tear-on; an immediate first frame; the brightness block
   again. No timer-based fix-up.
2. **Brightness as complete sets** (AID, ACL, ELVSS, CAPS, gamma, update
   key) for every change. The brightness report lists exact packets for 360,
   249, 183, 111, 60, 20 and 2 nit for this panel. A full 256-level control
   needs Samsung's smart dimming ported to C (about 300 lines;
   [`tools/panel/smartdim.py`](../tools/panel/smartdim.py) is a bit-exact
   reference). Default around 111–183 nit with ACL on, as Android did, which
   also reduces AMOLED wear.
3. **Screen off and wake as power cycles**, replacing the `28h`/`29h`
   backlight trick, once the cold start is reliable.
4. **One lock** around every multi-packet register sequence.
5. **Watch the error line** (TLMM 121) and re-initialise on a falling edge.
6. Optional: low-temperature ELVSS from the battery thermistor, HBM, mDNIe.

Two existing notes are corrected by this work: AID `c9` is not 51 nit on
the 360 nit gamma, and patch `0007`'s comment that Samsung reads in HS is
wrong for the read requests themselves (they are LP on stock; only the
offset writes before them are HS).
