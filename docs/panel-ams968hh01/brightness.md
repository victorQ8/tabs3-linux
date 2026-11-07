# AMS968HH01 / ANA38401 brightness and colour model (SM-T825), from Samsung's GPL source

> **File references.** `samsung-mdss/`, `samsung-extra/`, `fetched-mdss-fb/` and `re/dl/` hold files
> from Samsung's kernel, [awesometic/android_kernel_samsung_msm8996 @ f48aec90](https://github.com/awesometic/android_kernel_samsung_msm8996/tree/f48aec90fcebf4615fdee4a8abac7339930db856)
> (`drivers/video/msm/mdss/` and `drivers/video/msm/mdss/samsung/ANA38401_AMS968HH01/`).
> `stock-live-panel-node.dts` is lines 3276-3700 of the private stock DT backup
> (`private/backups/20261010T094140Z/live.dts`). `OURS` / `ours-20261011.c` is our driver as on the tablet
> on 2026-10-11 (patches up to `0027`), saved next to this report. Analysis scripts are kept outside
> the repository except [`tools/panel/smartdim.py`](../../tools/panel/smartdim.py).
> Summary and conclusions: [../panel-ams968hh01.md](../panel-ams968hh01.md).

Source analysis only; nothing was run on the tablet. Kernel source: awesometic/android_kernel_samsung_msm8996 at
`f48aec90fcebf4615fdee4a8abac7339930db856`. One extra file was fetched from that commit:
`drivers/video/msm/mdss/mdss_fb.c` (stored as `fetched-mdss-fb/mdss_fb.c`).

## Citation key

| Tag | File |
|---|---|
| PNL | `samsung-mdss/ss_dsi_panel_ANA38401_AMS968HH01.c` |
| CMN / CMNH | `samsung-mdss/ss_dsi_panel_common.c` / `.h` |
| SD / SDH | `samsung-mdss/ss_dsi_smart_dimming_ANA38401_AMS968HH01.c` / `.h` |
| SDC / SDCH | `samsung-mdss/ss_dsi_smart_dimming_common.c` / `.h` |
| MDN / MDNH | `samsung-mdss/ss_dsi_mdnie_lite_common.c` / `.h` |
| MDNP | `samsung-mdss/ss_dsi_mdnie_ANA38401_AMS968HH01.h` |
| DTSI / USA | `samsung-mdss/dsi_panel_ANA38401_AMS968HH01_qxga_octa_cmd.dtsi` / `..._usa.dtsi` |
| LIVE | `samsung-mdss/stock-live-panel-node.dts` (the tablet's own compiled DT node) |
| DSIP / DSIH / DSI / INTF | `samsung-mdss/mdss_dsi_panel.c` / `mdss_dsi_host.c` / `mdss_dsi.c` / `mdss_mdp_intf_cmd.c` |
| FB | `fetched-mdss-fb/mdss_fb.c` (fetched from the same commit) |
| OURS | `ours-20261011.c` |
| DOC | `docs/hardware-sm-t825.md` |
| STOCKDT | `private/backups/20261010T094140Z/live.dts` (full stock DT; used only for the cmdline) |

All paths without a prefix are relative to
``.

## 0. Summary

* **The live DT node is identical to the main dtsi.** All 94 valued properties and all 15 boolean
  properties match byte for byte (checked with `re-tools/dtsiparse.py`). The `_usa` variant
  (extra `B0 56 / B1 4C` porch, 895.4 MHz) is **not** what this tablet runs: LIVE:52 says 893.2 MHz.
  Every table below therefore cites both DTSI (readable) and LIVE (authoritative).
* **Brightness is a coherent tuple:** AID (`90`), ACL (`B0 4D`, `B0 49`, `B0 36`), ELVSS (`B0 67`), CAPS (`B0 6D`),
  gamma (`83`, 33 bytes) and finally the update key `B0 35 / B2 01`. It is sent as one HS command list
  (CMN:2448-2634, 2662-2740, 736). There are no level keys, no VINT, no IRC and no separate temperature packets for this panel.
* **The on-command ELVSS/ACL values (`B2 0F`, ACL off) are never what stock runs with at room temperature.** `0x0F` is the
  *low-temperature* (-20 °C < T <= 0 °C) ACL-off ELVSS for 360 cd (DTSI:767). Stock overwrites it straight
  after the on-command list, before mDNIe and before the first frame. It sends a full brightness packet: ACL on, 15 %, ELVSS `0x1B`
  at 360 cd (CMN:1669-1683; PNL:1015-1017; CMN:793).
* **Our 360 cd gamma matches stock byte for byte.** A bit-exact Python port of Samsung's smart dimming
  (`re-tools/smartdim.py`) reproduces the table our driver logged (`b3 d1 d5 c3 ...`, private
  `display-re-20261011/dmesg.txt:881`). The port also produces the gamma for all 65 levels for this panel's MTP
  (appendix).
* **The default mDNIe is `UI_AUTO`.** Apart from a per-panel white-point trim of at most a few percent, it equals bypass, so
  it cannot explain washed colours.
* **The most likely cause of the washed colours and rolling lines is drive state, not tone mapping (inference).**
  Our pre-0023 driver ran permanently at 360 cd with the cold-start ELVSS and ACL off. Stock never combines those at
  T > 0 °C. The symptom scales with bright area and disappears together with a large drop in power, which points at
  current-dependent mechanisms (ELVSS headroom, ACL) rather than gamma or mDNIe. Gamma and mDNIe are per-pixel maps that
  do not depend on how much of the screen is bright.

---

## A. Brightness pipeline

### A.1 From userspace level to `bl_level`

* LED class `lcd-backlight`: `max_brightness = brightness_max` (FB:1345-1346). Writes are clamped to
  `brightness_max` and scaled with `MDSS_BRIGHT_TO_BL(bl, v, bl_max, brightness_max)` (FB:295-301). Both are **355**
  (`qcom,mdss-dsi-bl-max-level` / `qcom,mdss-brightness-max-level`, DTSI:144-146, LIVE:27-28; parsed DSIP:2962-2967).
  The mapping is therefore the identity, and `bl_scale` is 1024 (FB:1272).
* `mdss_dsi_panel_bl_ctrl` (DSIP:854-912) leads to `mdss_dsi_panel_bklt_dcs` (DSIP:246-273), which calls
  `mdss_samsung_brightness_dcs(ctrl, level)` (CMN:2662). Only the left (DSI0) controller sends, because of
  `qcom,dcs-cmd-by-left` (DTSI:101, LIVE:11; DSIP:267-268).
* `mdss_samsung_brightness_dcs` stores `vdd->bl_level = level` (CMN:2677). It returns early if the continuous splash
  has not finished (CMN:2688-2691). It then chooses a path:
  * `bl_level >= hbm_min_lv` (268 = first `from` of the HBM table, CMN:949; DTSI:1195) takes the **HBM** path
    (CMN:2697-2699).
  * Otherwise the **normal** path runs (CMN:2700-2703). Levels 256-267 are clamped to 255 (CMN:2466-2468, comment "consider 256 ~ 281
    level for gallery ACL off").
* Normal path: `bl_level` (0..255) is looked up in `candela_map_table`, giving a row index (0..64) and a candela value
  (CMN:2232-2254; table parse CMN:850-896; DTSI:1125-1192).

### A.2 Normal (non-HBM) packet, exact order

Built by `mdss_samsung_normal_brightness_packet_set` (CMN:2448-2634) from the PNL callbacks
(PNL:984-998). Callbacks that are NULL for this panel and so produce no packet: `pre_acl_percent`, `acl_percent`,
`elvss_temperature1/2`, `vint` (PNL:988-997). `irc` and `tft_pwm_ldi` are never set. Every callback
returns `level_key = PANEL_CMD_NULL`, so no level-key packets are sent (PNL:635, 652, 669, 683, 730, 748, 776, 808).

| # | DSI type | Payload | What | Source |
|---|---|---|---|---|
| (a) | 15 | `B0 70` | only when leaving HBM: "HBM ELVSS" register offset | `mdss_hbm_off` PNL:368-380; DTSI:339-342 |
| (b) | 39 | `B2 <D2[0x70]>` | only when leaving HBM: restore the normal value read from MTP | PNL:358-364 |
| 1 | 39 | `90 HH 00 LL` | **AID / AOR**, 9-bit value `HH:LL` (HH is 00 or 01) **indexed by bl_level** (aid_subdivision) | `mdss_aid` PNL:605-642 (`aid_subdivision_enable = true`, PNL:78); DTSI:350-608 |
| 2 | 15 | `B0 4D` | ACL frame averaging offset | `mdss_acl_on/off` PNL:644-672 |
| 3 | 39 | `B2 05` (on) / `B2 04` (off) | 32-frame avg (ACL on) / 16-frame avg (ACL off) | DTSI:700-716 |
| 4 | 15 | `B0 49` | ACL start point offset | |
| 5 | 39 | `B2 7F` | start at 50 % | |
| 6 | 15 | `B0 36` | ACL percent offset | |
| 7 | 39 | `B2 12` (on) / `B2 10` (off) | 15 % (`gradual_acl_val`, default 0x12, overrides `cmds[5]`, PNL:654-656, 1017) / off | |
| 8 | 15 | `B0 67` | ELVSS offset (global parameter 103) | `mdss_pre_elvss` PNL:674-686; DTSI:723 |
| 9 | 39 | `B2 xx` | **ELVSS** per candela x ACL x temperature (B.2) | `mdss_elvss` PNL:689-737 |
| 10 | 15 | `B0 6D` | CAPS offset | `mdss_pre_caps_setting` PNL:739-751; DTSI:617-619 |
| 11 | 39 | `B2 81` (<= 39 cd) / `B2 85` (>= 41 cd) | **CAPS** | `mdss_caps_setting` PNL:754-784; DTSI:621-693 |
| 12 | 39 | `83` + 33 bytes | **gamma** ("brightness condition set"), from smart dimming for the candela | `mdss_gamma` PNL:786-812; DTSI:300-307 |
| 13 | 15 | `B0 35` | update-key offset | `gamma_tx_cmds` cmds[1], DTSI:308 |
| 14 | 39 | `B2 01` | **gamma update key** | DTSI:309 |

Notes:

* The ACL triple is sent **before** ELVSS, and the update key is always the **last** packet. That is true of every
  normal packet (CMN:2614-2621 is the last OCTA step).
* The ELVSS value depends on `acl_status || siop_status`, which switches the table (PNL:702-726).
* There is no backlight-IC dimming packet: `blic_dimming_cmds` is absent from the DT, so CMN:2716-2723 is skipped.
* After sending, `mdss_samsung_brightness_dcs` logs `level / candela / hbm / acl` (CMN:2725-2727). Android's
  "level 86 = 111 cd, acl 1" comes from that line, which agrees with the tables: bl 81-86 is row 45, 111 cd.

### A.3 HBM packet (bl_level 268..355)

Built by `mdss_samsung_hbm_brightness_packet_set` (CMN:2384-2446). `set_auto_brightness_value` (CMN:2257-2286)
looks up `hbm_candela_map_table` (DTSI:1194-1203; LIVE:110) to get `candela_level` and `auto_brightness` (6..13).

| # | DSI type | Payload | Source |
|---|---|---|---|
| 1 | 39 | `83` + 33 bytes: HBM gamma `hbm_interpolation_table[auto_brightness - 6]` | `mdss_hbm_gamma` PNL:166-188; SD:1956-1967, 1652-1667 |
| 2 | 39 | `90 00 00 0E` (AID fixed at the 360 cd value) | `hbm_etc_tx` cmds[0], DTSI:322 |
| 3-4 | 15/39 | `B0 67` / `B2 dim_off` (ELVSS dim offset; level and temperature table in B.4) | PNL:210-283 |
| 5-6 | 15/39 | `B0 70` / `B2 <D8[0x81]>` ("HBM ELVSS", read from MTP) | PNL:350-356 |
| 7-8 | 15/39 | `B0 4D` / `B2 05` | PNL:291-298 |
| 9-10 | 15/39 | `B0 49` / `B2 99` (60 % start) | PNL:294, 299 |
| 11-12 | 15/39 | `B0 36` / `B2 11` (8 %) | PNL:295, 300 |
| 13-14 | 15/39 | `B0 6D` / `B2 85` (CAPS on) | DTSI:333-334 |
| 15-16 | 15/39 | `B0 35` / `B2 01` (update key) | DTSI:335-336 |

HBM ignores `acl_status`: ACL is 8 % unless `gradual_acl_val == 0`, which never happens because it is fixed at 0x12 and no sysfs
writes it. `vdd->display_status_dsi[].hbm_mode` is set, so the next normal packet starts with `B0 70 / B2 <D2[0x70]>`
(CMN:2476-2485). When `auto_brightness >= HBM_CE_MODE (9)`, i.e. >= 430 cd, mDNIe is re-evaluated as well
(CMN:2733-2737; CMNH:89).

### A.4 Transport: LP/HS, batching, timing

* **Brightness packets are HS.** `brightness_packet_tx_cmds_dsi.link_state = DSI_HS_MODE` (CMN:734-736). This becomes
  `CMD_REQ_HS_MODE` (DSIP:223-227) and the host switches to HS for the transfer (DSIH:2798-2807).
* **On-commands are LP** (`qcom,mdss-dsi-on-command-state = "dsi_lp_mode"`, DTSI:187, LIVE:53). Off-commands are HS (DTSI:188).
* **mDNIe is HS** (MDN:1411). The Samsung DT command sets (including reads) default to HS when they have no `-state` key
  (DSIP:1397-1411; CMN:3253-3255 passes `link_key = NULL`).
* **One request:** the whole tuple is one `mdss_dsi_panel_cmds_send(..., PANEL_BRIGHT_CTRL)` (CMN:2714, 1127-1129,
  1302-1362), a single `cmdlist_commit`. Before transmitting, the host **waits for the MDP (frame transfer) to be idle**
  (`mdss_dsi_cmd_mdp_busy`, DSIH:2706-2709). In command mode the packet therefore goes out between frame transfers, never in
  the middle of one.
* **DMA sub-batches:** `mdss_samsung_single_transmission_packet` (CMN:2636-2660) sets `last = 0` on long writes and `last = 1`
  on every short write and on the packet before it. `mdss_dsi_cmds2buf_tx` fires one DMA per `last` (DSIH:1706-1757).
  For the normal packet the DMA bursts are therefore:
  `[90] [B0 4D] [B2] [B0 49] [B2] [B0 36] [B2] [B0 67] [B2 elvss] [B0 6D] [B2 caps + 83 gamma] [B0 35] [B2 01]`.
  All `wait` fields are 0.

### A.5 What latches when

Proven from the source:

* `B0 35 / B2 01` is labelled "Gamma Update: Update key" (DTSI:85-86, 308-309, 335-336). It closes **every**
  sequence that touches gamma, AID, ELVSS, ACL or CAPS: the on-command block (DTSI:50-86), the normal packet and the HBM packet.
  Samsung never sends any of those registers without a following update key in the same request.
* mDNIe blocks (`B0 A8 / B9 ...`, `B0 42 / B9 ...`) have no update key (MDNP:9973-9978).
* The DCS display on (`29`) and off (`28`) are plain DCS commands.

Inference (no register documentation in the source):

* `83` and the `B2` global-parameter registers written here (`0x36`, `0x49`, `0x4D`, `0x67`, `0x6D`) are shadowed and committed
  by the update key, most likely at the next internal frame start. AID may apply without the key: DOC:205-206 reports that
  bare `90 00 00 xx` writes changed brightness live.
* Our hardware findings fit a frame-synchronised commit that a later DDI reconfiguration can discard. Settings must be sent
  after display on and with frames running (patches 0026/0027), and settings sent together with the compression change
  "did not persist".

### A.6 Worked example: what stock sends for Android level 86 (111 cd, ACL on, 20 °C) on this tablet

```
39 90 00 00 99                       AID  (bl 86 -> aid_subdivision[86])
15 B0 4D | 39 B2 05                  ACL 32-frame average
15 B0 49 | 39 B2 7F                  ACL start 50 %
15 B0 36 | 39 B2 12                  ACL 15 %
15 B0 67 | 39 B2 21                  ELVSS: smart-ACL, normal temperature, 111 cd (row 19)
15 B0 6D | 39 B2 85                  CAPS on
39 83 c4 d6 d5 c6 c1 da e0 ec 9b 00 00  d7 dc d8 c7 c2 db df f1 96 00 00  c3 d7 d6 c9 c5 db e0 15 89 80 00
15 B0 35 | 39 B2 01                  update key
```

The gamma bytes come from the Python port with this panel's MTP (DOC:204).

---

## B. Tables (from the stock DT node)

### B.1 Level to candela, AID, ELVSS and CAPS

Generated from LIVE by `re-tools/tables.py`. Sources: candela map LIVE:109 (DTSI:1125-1192); AID LIVE:94
(DTSI:350-608); ELVSS LIVE:100-108 (DTSI:723-1119); CAPS LIVE:95-97 (DTSI:617-693). The "gamma base cd" column is
`base_luminance_revA` (SDH:286-352): the luminance at which smart dimming builds the tone curve. AID then pulls it down to
the target. AID values are listed for every `bl_level` in the row's range, from the lowest level to the highest, as the 9-bit
`HH:LL` of `90 HH 00 LL`. ELVSS is shown as normal / lowtemp / lowtemp2 (B.2).

| idx | bl levels | cd | gamma base cd | AID (90 xx 00 yy) over the bl range | ELVSS ACL off N/LT/LT2 | ELVSS ACL on N/LT/LT2 | CAPS |
|---|---|---|---|---|---|---|---|
| 0 | 0 | 2 | 112 | 17f | 19/0f/0a | 19/0f/0a | 81 |
| 1 | 1 | 3 | 112 | 17d | 19/0f/0a | 19/0f/0a | 81 |
| 2 | 2 | 4 | 112 | 17a | 19/0f/0a | 19/0f/0a | 81 |
| 3 | 3 | 5 | 112 | 178 | 1a/10/0b | 1a/10/0b | 81 |
| 4 | 4 | 6 | 112 | 175 | 1a/10/0b | 1a/10/0b | 81 |
| 5 | 5 | 7 | 112 | 172 | 1a/10/0b | 1a/10/0b | 81 |
| 6 | 6 | 8 | 112 | 16f | 1a/10/0b | 1a/10/0b | 81 |
| 7 | 7 | 9 | 112 | 16c | 1a/10/0b | 1a/10/0b | 81 |
| 8 | 8 | 10 | 112 | 169 | 1a/10/0b | 1a/10/0b | 81 |
| 9 | 9 | 11 | 112 | 167 | 1b/11/0c | 1b/11/0c | 81 |
| 10 | 10 | 12 | 112 | 164 | 1b/11/0c | 1b/11/0c | 81 |
| 11 | 11 | 13 | 112 | 161 | 1b/11/0c | 1b/11/0c | 81 |
| 12 | 12 | 14 | 112 | 15e | 1b/11/0c | 1b/11/0c | 81 |
| 13 | 13 | 15 | 112 | 15a | 1b/11/0c | 1b/11/0c | 81 |
| 14 | 14 | 16 | 112 | 158 | 1c/12/0d | 1c/12/0d | 81 |
| 15 | 15 | 17 | 112 | 156 | 1c/12/0d | 1c/12/0d | 81 |
| 16 | 16 | 19 | 112 | 150 | 1c/12/0d | 1c/12/0d | 81 |
| 17 | 17 | 20 | 112 | 14d | 1c/12/0d | 1c/12/0d | 81 |
| 18 | 18 | 21 | 112 | 148 | 1d/13/0e | 1d/13/0e | 81 |
| 19 | 19 | 22 | 112 | 145 | 1d/13/0e | 1d/13/0e | 81 |
| 20 | 20 | 24 | 112 | 13f | 1d/13/0e | 1d/13/0e | 81 |
| 21 | 21 | 25 | 112 | 13c | 1d/13/0e | 1d/13/0e | 81 |
| 22 | 22-23 | 27 | 112 | 139, 136 | 1e/14/0f | 1e/14/0f | 81 |
| 23 | 24-25 | 29 | 112 | 133, 130 | 1e/14/0f | 1e/14/0f | 81 |
| 24 | 26-27 | 30 | 112 | 12e, 12c | 1e/14/0f | 1e/14/0f | 81 |
| 25 | 28-29 | 32 | 112 | 129, 126 | 1f/15/10 | 1f/15/10 | 81 |
| 26 | 30-31 | 34 | 112 | 122, 11f | 1f/15/10 | 1f/15/10 | 81 |
| 27 | 32-33 | 37 | 112 | 11b, 116 | 20/16/11 | 20/16/11 | 81 |
| 28 | 34-35 | 39 | 112 | 113, 10f | 20/16/11 | 20/16/11 | 81 |
| 29 | 36-37 | 41 | 112 | 10c, 109 | 20/16/11 | 20/16/11 | 85 |
| 30 | 38-39 | 44 | 112 | 104, 0ff | 21/17/12 | 21/17/12 | 85 |
| 31 | 40-41 | 47 | 112 | 0fa, 0f5 | 21/17/12 | 21/17/12 | 85 |
| 32 | 42-43 | 50 | 112 | 0f0, 0eb | 21/17/12 | 21/17/12 | 85 |
| 33 | 44-45 | 53 | 112 | 0e6, 0e1 | 21/17/12 | 21/17/12 | 85 |
| 34 | 46-48 | 56 | 112 | 0de, 0da, 0d7 | 21/17/12 | 21/17/12 | 85 |
| 35 | 49-51 | 60 | 112 | 0d2, 0ce, 0c9 | 21/17/12 | 21/17/12 | 85 |
| 36 | 52-54 | 64 | 112 | 0c4, 0c0, 0bb | 21/17/12 | 21/17/12 | 85 |
| 37 | 55-57 | 68 | 112 | 0b6, 0b2, 0ad | 21/17/12 | 21/17/12 | 85 |
| 38 | 58-60 | 72 | 112 | 0a6, 0a0, 099 | 21/17/12 | 21/17/12 | 85 |
| 39 | 61-63 | 77 | 120 | 0a3, 09e, 099 | 21/17/12 | 21/17/12 | 85 |
| 40 | 64-66 | 82 | 127 | 0a3, 09e, 099 | 21/17/12 | 21/17/12 | 85 |
| 41 | 67-69 | 87 | 135 | 0a2, 09d, 099 | 21/17/12 | 21/17/12 | 85 |
| 42 | 70-72 | 93 | 143 | 0a3, 09e, 099 | 21/17/12 | 21/17/12 | 85 |
| 43 | 73-76 | 98 | 152 | 0a2, 09f, 09c, 099 | 21/17/12 | 21/17/12 | 85 |
| 44 | 77-80 | 105 | 162 | 0a5, 0a1, 09d, 099 | 21/17/12 | 21/17/12 | 85 |
| 45 | 81-86 | 111 | 170 | 0a4, 0a1, 09f, 09d, 09b, 099 | 21/17/12 | 21/17/12 | 85 |
| 46 | 87-91 | 119 | 181 | 0a6, 0a2, 09f, 09c, 099 | 21/17/12 | 21/17/12 | 85 |
| 47 | 92-97 | 126 | 192 | 0a4, 0a2, 0a0, 09d, 09b, 099 | 21/17/12 | 21/17/12 | 85 |
| 48 | 98-104 | 134 | 203 | 0a5, 0a3, 0a1, 09f, 09d, 09b, 099 | 21/17/12 | 21/17/12 | 85 |
| 49 | 105-110 | 143 | 216 | 0a5, 0a3, 0a0, 09e, 09b, 099 | 21/17/12 | 21/17/12 | 85 |
| 50 | 111-118 | 152 | 227 | 0a5, 0a3, 0a2, 0a0, 09e, 09c, 09b, 099 | 20/16/11 | 20/16/11 | 85 |
| 51 | 119-125 | 162 | 240 | 0a5, 0a3, 0a1, 09f, 09d, 09b, 099 | 20/16/11 | 20/16/11 | 85 |
| 52 | 126-133 | 172 | 254 | 0a5, 0a3, 0a2, 0a0, 09e, 09c, 09b, 099 | 1f/15/10 | 1f/15/10 | 85 |
| 53 | 134-142 | 183 | 254 | 097, 095, 093, 091, 08e, 08c, 08a, 088, 086 | 1f/15/10 | 1f/15/10 | 85 |
| 54 | 143-150 | 195 | 254 | 083, 081, 07e, 07c, 079, 076, 074, 071 | 1f/15/10 | 1f/15/10 | 85 |
| 55 | 151-160 | 207 | 254 | 06f, 06d, 06b, 069, 067, 064, 062, 060, 05e, 05c | 1f/15/10 | 1f/15/10 | 85 |
| 56 | 161-170 | 220 | 254 | 05a, 057, 055, 053, 051, 04e, 04c, 04a, 047, 045 | 1e/14/0f | 1e/14/0f | 85 |
| 57 | 171-181 | 234 | 254 | 043, 040, 03e, 03c, 039, 037, 034, 032, 030, 02d, 02b | 1e/14/0f | 1e/14/0f | 85 |
| 58 | 182-193 | 249 | 254 | 029, 026, 024, 021, 01f, 01d, 01a, 018, 015, 013, 010, 00e | 1e/14/0f | 1e/14/0f | 85 |
| 59 | 194-205 | 265 | 272 | 023, 021, 01f, 01d, 01b, 019, 017, 016, 014, 012, 010, 00e | 1d/13/0e | 1e/14/0e | 85 |
| 60 | 206-218 | 282 | 288 | 023, 021, 01f, 01e, 01c, 01a, 018, 017, 015, 013, 011, 010, 00e | 1d/13/0e | 1e/14/0e | 85 |
| 61 | 219-230 | 300 | 307 | 023, 021, 01f, 01d, 01b, 019, 017, 015, 014, 012, 010, 00e | 1c/12/0d | 1d/13/0d | 85 |
| 62 | 231-242 | 316 | 321 | 01f, 01e, 01c, 01b, 019, 017, 016, 014, 013, 011, 010, 00e | 1b/11/0c | 1c/12/0c | 85 |
| 63 | 243-253 | 333 | 336 | 01f, 01e, 01c, 01a, 018, 017, 015, 013, 011, 010, 00e | 1a/10/0b | 1c/12/0b | 85 |
| 64 | 254-255 | 360 | 360 | 00e, 00e | 19/0f/0a | 1b/11/0a | 85 |

Observations:

* The AID within a row changes per bl step (aid_subdivision) while the gamma stays that of the row's candela. Rows 53-58
  (183-249 cd, base 254) and 59-64 cover their range almost entirely through AID.
* **The AID only makes sense with the matching gamma.** For <= 72 cd the curve is built at 112 cd and AID about `0x099..0x17F`
  dims it. Using the 360 cd gamma with, for example, AID `0xC9` (bl 51, the 60 cd row) would give roughly
  360 x (60/112), about 190 cd, and the wrong tone curve. This is an inference about AID behaving as a duty ratio. Note too that DOC:205 calls `c9`
  "51 nit"; it is the AID of *bl level* 51, a 60 cd row built on a 112 cd base.
* Smart-ACL ELVSS differs from ACL-off ELVSS only at 265-360 cd. The 360 cd values are N `0x19` (off) or `0x1B` (on);
  lowtemp `0x0F`/`0x11`; lowtemp2 `0x0A`/`0x0A`. **The on-command `B2 0F` (DTSI:73-74) is the lowtemp ACL-off value.**
* The empty comment `/* ELVSS Temp Compensation */` in the on-command list (DTSI:88) sends nothing.

### B.2 ELVSS selection and temperature

* `mdss_elvss` (PNL:689-737): `cd_index` = candela row (CMN:2232-2242). The table is `smart_acl_elvss*` if
  `acl_status || siop_status`, otherwise `elvss*`. The column is chosen by `vdd->temperature`:
  `> 0` normal, `> -20` lowtemp, else lowtemp2 (PNL:708-713, 720-725). Both comparisons are strict.
* Temperature comes from **userspace**: sysfs `temperature` (CMN:6443, store CMN:5108-5137). Each write triggers an
  immediate `set_backlight(bl_level)`, which re-sends the full tuple (CMN:5130-5132). The show callback advertises the
  trip points `"-20, -19, 0, 1, 30, 40"` (CMN:5098-5101). Inference: the framework writes only when a trip point is crossed.
* Default `vdd->temperature = 20` (PNL:594, set at smart-dimming init), so the normal table applies until userspace writes.
* `samsung,elvss_interpolation_temperature` is not in this panel's node, and this panel has no temperature callbacks
  (PNL:995-996).

### B.3 ACL rules

* Normal path: ACL is on when `acl_status || siop_status` (CMN:2498). `acl_status` defaults to **1** (PNL:1015-1016,
  "ACL default 15% ON"). It is changed through sysfs `power_reduce` (CMN:6440, 4803-4842) and SIOP through `siop_enable`
  (CMN:6441, 4863-4904). Both re-send the tuple.
* ACL on: `4D=05` (32-frame average), `49=7F` (50 % start), `36=gradual_acl_val=0x12` (15 %) (DTSI:700-707; PNL:654-656).
  ACL off: `4D=04`, `49=7F`, `36=10` (DTSI:709-716).
* "Gradual ACL" here is only `gradual_acl_val`, fixed at 0x12 (PNL:1017). `gradual_acl_tx_cmds` is not in the DT, so
  `PANEL_GRADUAL_ACL` (CMN:1246-1248) is never used.
* HBM: always `4D=05, 49=99 (60 %), 36=11 (8 %)` (PNL:285-300), independent of `acl_status`.
* The on-command list writes `4D=04` and `36=10` (ACL off) but **never `0x49`** (DTSI:76-80). Until the first brightness
  packet the ACL start point is the DDI reset default.

### B.4 HBM (bl 268..355)

`hbm_candela_map_table` (LIVE:110; DTSI:1194-1203), HBM ELVSS dim offset (`B0 67`) from PNL:210-281:

| bl | cd | auto_brightness | interp. index | `B0 67` value T>0 / -20<T<=0 / T<=-20 |
|---|---|---|---|---|
| 268-279 | 378 | 6 | 0 | 25 / 1B / 17 |
| 280-292 | 395 | 7 | 1 | 23 / 19 / 17 |
| 293-304 | 413 | 8 | 2 | 21 / 17 / 17 |
| 305-317 | 430 | 9 | 3 | 1F / 17 / 17 |
| 318-329 | 448 | 10 | 4 | 1E / 17 / 17 |
| 330-341 | 465 | 11 | 5 | 1C / 17 / 17 |
| 342-354 | 483 | 12 | 6 | 1A / 17 / 17 |
| 355 | 500 | 13 | 7 | 17 / 17 / 17 |

Fixed parts of HBM: AID `0x00E`, `B0 70 = D8[0x81]`, ACL 8 %/60 %/32-frame, CAPS `85`, update key. The HBM gamma is described in C.5.
`auto_brightness_level = 12` (PNL:1008) only selects interpolated HBM.

### B.5 Panel data reads (all HS, each preceded by `15 B0 <offset>`)

The read position is set by `reg_read_pos_tx_cmds` `15 B0 xx` (DTSI:265-267; CMN:1039-1042). Reads use generic read
`24 <reg> <len>`, at most 10 bytes per packet (CMN:1019).

| Data | Register / offset / length | Used by |
|---|---|---|
| Gamma MTP (33 B) | D8 @0x5A,0x62,0x6A,0x72 x8 + 0x7A x1 | PNL:553-573; DTSI:269 |
| White-point x,y (4 B) | D8 @0x7B | mDNIe white trim, PNL:510-521; DTSI:272 |
| Manufacture date (2 B) | D8 @0x7F | PNL:105-109; DTSI:295 |
| HBM ELVSS (1 B) | D8 @0x81 | goes into `hbm_etc` `B0 70` value, PNL:350-356; DTSI:271 |
| HBM reference gamma (33 B) | D4 @0x5B,0x63,0x6B,0x73 x8 + 0x7B x1 | PNL:321-343; DTSI:270 |
| Normal "HBM ELVSS" (1 B) | D2 @0x70 | restored by `hbm_off`, PNL:358-364; DTSI:273 |
| IDs | DA/DB/DC | DTSI:291-293 (this panel: `42 40 16`, DOC:186-187) |

On the first panel-on, `manufacture_read_pre_tx_cmds` is sent in HS before these reads:
`B0 34/B2 64 00, B0 D9/B1 08, B0 51/B1 06, B0 75/B2 28` (DTSI:277-289; CMN:1477-1498). All reads happen in
`mdss_samsung_panel_on_pre`, **before** the on-command list (DSIP:1011-1019 then 1023-1033).

---

## C. Smart dimming (MTP to per-candela `83` gamma)

### C.1 Data layout

* `83` payload per colour (R, G, B; 11 bytes each, 33 total) in **register order**:
  `V11, V23, V35, V51, V87, V151, V203, V255_lo, V3, V255_hi, VT`. `V255_hi` is `0x80` when bit 8 of the 9-bit V255
  value is set (SD:1806-1810). The reference table is `80 80 80 80 80 80 80 00 80 80 00` per colour, i.e. V255 = 0x100, the rest 0x80,
  VT = 0 (DTSI:300-307, 50-68; SDH:71-114; SD:1719-1767).
* The raw MTP (D8, 33 bytes) uses the same register order (`mtp_sorting`, SD:1697-1718, maps it to struct order
  `255hi, 255lo, 203, 151, 87, 51, 35, 23, 11, 3, 1`). The values are **sign-magnitude**: bit 7 means negative, magnitude in
  bits 6:0 (`char_to_int`, SD:86-97). V255 is `+/-V255_lo`, negative if `V255_hi != 0` (SD:99-109, 1713-1716).
* This panel: `33 51 55 43 3a 53 5b 36 14 00 00 | 40 51 57 42 3c 53 5b 3c 0c 00 00 | 38 53 56 47 3d 55 5c 64 82 00 00`
  (DOC:204). Offsets are V3 +20/+12/-2 and V203 +91/+91/+92. They are large, so the DDI does **not** add MTP on its
  own; the host must.

### C.2 Voltage model (SD:204-1013, run once at init, SD:1872-1903)

Fixed-point Q22 (`BIT_SHIFT 22`), `REF_L = 6.8 V`, `REF_H = 1.5 V` (SDH:46-58). All divisions are integer and floor.
`m_x` is the signed MTP offset; the centre values are `0x100` (V255) and `0x80 = 128` (others; **char is unsigned on
arm64**, so this is +128).

```
V0   = REF_L
V255 = REF_L - (REF_L-REF_H) * (129 + 256 + m255) / 640                     (SD:206-244)
VT   = REF_L - REF_L * vt_coef[mVT] / 600,  vt_coef = {0,12,24,...,108,138,...,186}   (SD:330-366)
Vp   = VT - (VT - Vq) * (64 + 128 + mp) / 320    for p = 203,151,87,51,35,23,11, q = next higher point (SD:385-934)
V3   = REF_L - (REF_L - V11) * (64 + 128 + m3) / 320                         (SD:936-983)
```

(V1 is never computed; `RGB_OUTPUT.level_1` stays 0.)

**Gray table** (`generate_gray_scale`, SD:1054-1357): 256 voltages per colour. They are fixed at the inflection points
`{0,1,3,11,23,35,51,87,151,203,255}` (SD:1016) and linearly interpolated in between with floor:
`G[k] = G[low] + (G[up]-G[low]) * (low-k)/(low-up)`. Gray levels 1 and 2 are interpolated between V0 and V3.
The constants are in SD:1018-1052.

### C.3 Per-candela gamma (`gamma_init_revA`, SD:1522-1650)

For each of the 65 candela values (`lux_tab` = DT candela column, PNL:586-587; SDH:217-283):

1. `base = base_luminance_revA[cd]` (SDH:286-352): 112 cd for <= 72 cd, then rising, 254 cd for 172-249 cd, about cd above that.
2. Target luminance for each point P in `{1,3,11,23,35,51,87,151,203,255}`: `L_P = coeff[P] * base`. Here
   `coeff = candela_coeff_2p15` (gamma **2.15**) if `cd < 360`, and `candela_coeff_2p2` (2.2) at 360 cd (SD:1544-1560).
   The tables are exactly `round((i/255)^g * 2^22)` (SDC:566, SDC:302; header formula SDCH:59-71). Only 10 entries of each are used:
   2p15 `28, 298, 4871, 23786, 58660, 131788, 415494, 1359562, 2568710, 4194304`;
   2p2 `21, 239, 4162, 21090, 53115, 121598, 393744, 1324405, 2539585, 4194304`.
3. Map each `L_P` to the nearest gray index on the **reference 360 cd, gamma 2.2 curve** `curve_2p2_360[i] =
   round(360*(i/255)^2.2*2^22)` (SDC:7698; SDCH:253-258). Ties go to the lower index (`searching_function`, SD:1433-1479;
   the `GAMMA_CURVE_2P2` argument is at SD:1574-1575).
4. Add `gradation_offset_revA[row][col]` to the indices for V255..V3 (SDH:354-421; SD:1584-1599). These are large at low
   levels, for example +49 on V3 at 2 cd. An index that ends at 0 becomes 1.
5. Convert target voltages to register values (`Make_hexa`, SD:1483-1494):
   * `V255reg = (REF_L - G[i255]) * 640 / (REF_L-REF_H) - 129` (9 bits) (SD:300-328)
   * `Vp_reg = (VT - G[ip]) * 320 / (VT - G[iq]) - 64`, using the gray voltage at the *upper point's target index*
     (SD:434-462 and siblings)
   * `V3reg = (REF_L - G[i3]) * 320 / (REF_L - G[i11]) - 64` (SD:985-1013)
   * `VTreg = 0` (SD:378-383)
6. Add `rgb_offset_revA[row]` (24 values: R/G/B for 255, 203, 151, 87, 51, 35, 23, 11) to V255 (16-bit) and V203..V11
   (SD:1619-1642; SDH:423-493). The results are truncated to 8 bits.
7. After all rows: **the 360 cd row is replaced by the reference table** (SD:1923-1925). `gamma_command_sorting_post`
   (SD:1779-1816) reorders every row to register order and turns `V255_hi = 1` into `0x80`. For the **360 cd row only** it
   adds the **raw** MTP bytes with `offeset_add` (SD:1769-1777): a sum below 0 becomes 0, **a sum above 255 becomes 0x80**.
   `V255_hi` gets `+0x7F`, so `0x01 + 0x00 + 0x7F = 0x80`.
8. At run time `generate_gamma` (SD:1669-1695) copies the precomputed row whose lux equals the candela. On a miss it falls back to
   `max_lux_table`, the reference table without MTP.

`mtp_offset_substraction` is compiled out (`#if 0`, SD:1358-1432). Everything is computed once at the first panel-on
(PNL:537-602).

### C.4 Quirks a reimplementation must reproduce (or knowingly fix)

* **Unsigned char.** `V203_300CD_R` etc. are `static char` holding 0x80 (SD:50-84). On arm64 that is +128; on a signed-char
  build the whole model changes.
* **The 360 cd row clamps negative MTP to 0x80.** A sign-magnitude negative byte (for example this panel's B V3 `0x82` = -2) is added
  as unsigned: `0x80 + 0x82 > 255` gives `0x80`. The voltage model would give `0x7D` (C.6).
* **`rgb_offset_revA` at 183 cd has B11 = +6** (SDH:481), while its neighbours are -7 (172 cd) and -5 (195 cd). This is likely a sign typo.
  It puts the 183 cd B V11 register at `0xce` against `0xc1`/`0xbd` either side.
* `vt_adjustment` indexes `vt_coefficient[LSB]` directly (SD:343-345). A negative VT offset would read out of bounds.
  This panel's VT MTP is 0.
* `base_luminance_revA` and `rgb_offset_revA` row comments differ slightly from `candela_table`. For example, the rows
  commented 262/285/216 cd are really 265/282/220 cd. The tables are indexed by row (`find_cadela_table`, SD:1510-1520), so only the comments are wrong.

### C.5 HBM gamma (SD:1821-1870; PNL:575-582)

* `hbm_buffer1` = D4 reference (33 B) **+ raw MTP**, added bytewise mod 256 as unsigned char. That is wrong for sign-magnitude
  negatives such as this panel's B V3. The sum is stored into `hbm_gamma_tx_cmds` (PNL:575-582). The comment says
  "Gamma Offset Index 4", which ties it to the on-command `B0 BC / B2 04` "Gamma Offset index setting" (DTSI:47-48).
* For `cd_k` in `{378, 395, 413, 430, 448, 465, 483, 500}` (SDH:212):
  `rate = (cd_k - 360) * 2^22 / 140` and `g = g360 + (gHBM - g360) * rate / 2^22`, in int arithmetic that truncates toward 0. The VT bytes
  (indices 10, 21, 32) are forced to 0. `g360` is the MTP-calibrated 360 cd row. Computing this for our panel needs a D4 read.

### C.6 Validation of the Python port

`re-tools/smartdim.py` is a bit-exact port with explicit u64 wrap, floor divisions, unsigned chars and the C quirks. It
reads the curve tables directly from SDC and the offset tables from SDH.

* Its 360 cd row equals our driver's logged table:
  `b3 d1 d5 c3 ba d3 db 36 94 80 00 c0 d1 d7 c2 bc d3 db 3c 8c 80 00 b8 d3 d6 c7 bd d5 dc 64 80 80 00`
  (private `display-re-20261011/dmesg.txt:881`; OURS:276-291 implements the same formula).
* The voltage model evaluated at 360 cd (before the reference-table overwrite) gives every byte exactly 1 LSB lower
  (floor), except B V3 (`0x7D` against the clamped `0x80`). So the model and "reference + MTP" agree. This confirms that `83` takes
  **absolute** register values and that the host, not the DDI, applies the MTP.
* All 65 rows for this panel are in the appendix.

---

## D. Default state after power-on

**Cold boot (stock Android).**

1. LK shows the logo with its own init. The bootloader code is not in this source; inference: it uses the same on-command list.
2. The kernel inherits it as continuous splash. The stock cmdline is `mdss_mdp.panel=1:dsi:0:...` (STOCKDT:20302) and
   `cont_splash_enabled` comes from `panel_intf_status` (DSI:4754-4759). While splash is active, brightness and mDNIe are
   suppressed (CMN:2688-2691; MDN:178-184; FB:1700-1704 stores `unset_bl_level`).
3. At splash finish, Samsung's MDSS **blanks and powers the panel off** ("Turning off panel to initialize panel init-seq at
   kick-off", INTF:1884-1913).
4. At the next kick-off the full Samsung panel-on runs:
   `on_pre` (first-time reads, B.5) -> on-command list (LP, includes `29` display on after `B1 1D` and a 215 ms wait,
   DTSI:90-93) -> `on_post`: brightness packet at `vdd->bl_level` (HS, CMN:1669-1683) -> mDNIe (HS, CMN:1685-1690).
   After the first frame, `PANEL_DISPLAY_ON` sends nothing because `display_on_tx_cmds` is commented out (DTSI:297; CMN:342-361).
5. `vdd->bl_level` starts at `DEFAULT_BRIGHTNESS = 255` (CMNH:78; CMN:793). Android's first write during splash was stored in
   `vdd->bl_level` (CMN:2677 runs before the splash check), so the first real packet uses that level. FB re-applies its own
   `unset_bl_level` on the first kick-off (FB:1753-1780).
6. **Recovery mode** forces `bl_level = 255` (360 cd) on every `on_post` (CMN:1662-1664). That is still with ACL on, ELVSS `0x1B`.

**Resume.** `mdss_fb_blank_blank` sets the backlight to 0 while the panel is still on (FB:1893-1899), so stock sends the
level-0 tuple (2 cd, AID `0x17F`) and `vdd->bl_level = 0`. On unblank: on-commands -> brightness packet for level 0 (from
`on_post`) -> mDNIe -> `mdss_fb_blank_unblank` immediately re-sends the saved user level (FB:1975-1997) -> frames.

**Do the on-command ACL/ELVSS ever persist?** No, not in normal use. Within the same panel-on, before mDNIe and before any
frame, `on_post` sends a full tuple with ACL on (`acl_status = 1`, PNL:1016) and the normal-temperature smart-ACL ELVSS
(`temperature = 20`, PNL:594). The exceptions are paths where Samsung's brightness code is inactive: a PBA or no-panel boot
(CMN:3765-3796), the splash window, or `blank_state == BLANK` (CMN:1322-1325). The on-command ELVSS `0x0F` and "ACL off" are
therefore cold-start placeholders. At room temperature they are only on screen during the LK logo (inference).

---

## E. mDNIe

* **Default state** (`init_dsi_tcon_mdnie_class`, MDN:1347-1417): `UI_APP`, `AUTO_MODE`, `OUTDOOR_OFF`, bypass disabled,
  accessibility off, no night mode, HDR or colour lens. `NATURAL_MODE_ENABLE` is defined (MDNH:37), so `AUTO_MODE` = 4
  and the table entry is `DSI0_UI_AUTO_MDNIE` (MDNP:10252-10260).
* **When it is sent:** on every panel-on (CMN:1685-1690) and on any mode, scenario or accessibility sysfs change, as HS DCS on DSI0
  (MDN:1411; single-DSI path MDN:146-161). It is only sent if not in splash and the panel is unblanked (MDN:178-184). Priority order: bypass >
  light notification > accessibility > colour lens > HDR > night > HBM-CE (lux >= `enter_hbm_lux` 10000, DTSI:254) > app/mode
  (MDN:205-301).
  * Stock really sends it. The cmdline has `lcd_id2=0xffffff` (STOCKDT:20302), so `mdss_panel_attached(1)` is false (CMN:181-199,
    252-270). Only the DSI0 mDNIe state exists (CMN:759-765), and the single path is taken. Without that argument a DSI1 state
    would exist and the dual path would hit "TODO DUAL PANEL" and send nothing (MDN:127-140).
* **Exact blocks** (MDNP:48-56, 9973-9978; sizes PNL:963-967):
  ```
  15 B0 A8
  39 B9 <55 bytes>    DSI0_UI_AUTO_MDNIE_1  (MDNP:3267-)  ASCR block, "start offset 0x08A8"
  15 B0 42
  39 B9 <102 bytes>   DSI0_UI_AUTO_MDNIE_2  (MDNP:3328-)  mdnie_en, algo enables, LCE/DE/FA/CS, 24 curve points, "start offset 0x0842"
  ```
* **UI_AUTO compared with bypass** (`DSI0_BYPASS_MDNIE`, MDNP:9838-9843, 232-399; diff from `re-tools/mdnie_diff.py`):
  * Block 2 byte "ascr algo lce" is `0x3c` for UI_AUTO and `0x00` for bypass (MDNP:3333 vs 298). `mdnie_en = 1` in both.
  * The "nr fa de cs gamma" enable byte is `0x00` in **both** (MDNP:3346), so there is no detail enhancement, colour saturation or mDNIe gamma.
  * The ASCR main colour matrix (`Cr..Kb`) is **identical** in both (identity). The only other differences are skin-tone and distance
    parameters, which have no effect because `ascr_skin_on = 0`.
  * UI_AUTO's white point (`ascr_Wr/Wg/Wb` at payload offsets 50/52/54, MDNP:39-41) is overwritten at init by
    `mdss_mdnie_read` -> `coordinate_tunning_multi` from the panel's measured CIE x,y (D8 @0x7B). For MOVIE, AUTO and READING it picks
    one of 9 trims in `coordinate_data_1` (PNL:425-459, 461-535; MDN:1419-1441), for example `ff/fc/fc` or `fc/ff/fd`.
  * In short, **UI_AUTO is bypass plus a white-point trim of at most about 1.6 % per channel**. It would look essentially the same as
    bypass, which matches DOC:207-208 ("bypass looks identical to the power-on state"). mDNIe neither causes nor fixes washed colours.

---

## F. Our driver compared with stock, and what explains the symptom

### F.1 Gap table (OURS = current file, patches 0004-0027)

| Area | Stock | Ours | Matters for symptom? |
|---|---|---|---|
| Brightness control | 0..255 normal + 268..355 HBM, 65 candela rows, sysfs and LED backlight | Fixed 360 cd. The backlight device only toggles display on/off (OURS:692-721) | Indirectly: we always run at maximum current |
| `83` gamma | Per candela from MTP (C) | 360 cd row only (OURS:276-303). **Identical** to stock's 360 cd row | No |
| AID `90` | Per bl level | `00 00 0E` (= stock bl 254/255) in init only (OURS:359). **Not re-sent after the fixup** | Possibly, if the compression toggle resets it (unknown) |
| ELVSS `B0 67` | Per cd x ACL x temperature. 360 cd/ACL on/T>0 = `1B` | Since 0023: `1B` (OURS:318-319). Before 0023: on-command `0F` | **Yes (before 0023)** |
| ACL `4D/49/36` | On by default: `05/7F/12` | Since 0023: `05/7F/12`. Before: on-command `04/<unset>/10` | **Yes (before 0023)** |
| CAPS `B0 6D` | `81` for <= 39 cd, `85` for >= 41 cd | `85` in init only (OURS:361-362), not re-sent after the fixup | Only if lost (unknown) |
| Update key | Exactly once, last, in the same request as everything else | Sent after normal conditions, after CAPS and after gamma. Fine | No |
| Atomicity / timing | One HS command list after waiting for frame transfer idle (DSIH:2706-2709). Sent straight after the on-commands, before frames | Individual transfers. Init values in LP, re-sent later in HS steps 600 ms apart after a compression toggle | Yes, indirectly: hardware shows state must be re-sent after the toggle |
| Temperature | Userspace temperature, three tables, default 20 °C | Fixed normal-temperature values | Not at room temperature |
| HBM | bl >= 268: interpolated HBM gamma, `B0 70`, 8 % ACL | None | No |
| mDNIe | UI_AUTO + white trim | None (DDI reset state) | No |
| DDI input setup | On-commands only. First panel-on also sends `B0 D9/B1 08` then `B0 51/B1 06` in HS before the reads (DTSI:277-289) | Compression toggle fixup after frames (0009-0011, 0026) | Out of scope here, but every state written before the toggle is suspect |
| Resume | Level 0 tuple, then the user tuple, before frames | `bl_power` off/on via DCS 28/29 plus normal conditions after display on (OURS:692-721) | OK for 360 cd |

### F.2 What the source proves

1. At T > 0 °C stock never shows content with the on-command ELVSS/ACL. `on_post` replaces them before the first frame
   (CMN:1669-1683; DSIP:1023-1058), and splash handoff forces a full re-init (INTF:1911-1913).
2. On-command `B2 0F` at `B0 67` is the **lowtemp (-20 < T <= 0 °C) ACL-off** value for 360 cd (DTSI:767). Room-temperature 360 cd uses
   `0x19` (ACL off) or `0x1B` (ACL on) (DTSI:725, 927).
3. The on-command list never writes the ACL start (`B0 49`), so it is at the DDI default until a brightness packet arrives (DTSI:76-80 vs 700-716).
4. Stock's default operating point is ACL on at 15 % (PNL:1015-1017). In HBM, ACL is always 8 % (PNL:285-300).
5. Our 360 cd gamma equals stock's (C.6). mDNIe UI_AUTO is identity apart from the white trim (E).
6. Before patch 0023 our driver ran the on-command state (ELVSS `0F`, ACL off) at 360 cd indefinitely. That is a state stock never
   displays content in at room temperature.

### F.3 Ranked explanation of the washed colours and rolling lines (inference)

The symptom is worse with large bright content, absent on a black text console, and fixed together with a large current drop
(-1.47 A to +0.16 A net battery current, DOC:526-528). Gamma and mDNIe are content-independent per-pixel maps; ELVSS headroom
and ACL depend on load. In order of likelihood:

1. **ELVSS `0x0F` instead of `0x1B`, a cold-start value at room temperature.** Codes fall with luminance and with cold (DTSI:724-847;
   HBM PNL:210-281), so a lower code most likely means more negative ELVSS and more voltage across the OLED stack. Ten codes
   below the room-temperature setting drives the panel outside its calibrated operating point, which fits the extra power. Likely mechanism
   for the visible defects: the ELVDD/ELVSS supply sags or current-limits under bright full-screen load, which shows as lifted and washed
   colours and scan-synchronous rolling bands. The source cannot prove which register or rail misbehaves.
2. **ACL off at 360 cd** (with the ACL start at reset default). Stock caps large bright areas by 15 % at > 50 % APL. Without it the
   peak current at full white is the highest the panel can draw, which aggravates item 1. Stock only runs ACL off when userspace clears
   `power_reduce`, and then it uses the matching ACL-off ELVSS table.
3. **State lost across the DDI input fixup.** The colleague's notes (0026, 0027; DOC:529-532) show values written before or together with the
   compression change do not stick. That fits registers that the update key commits at a frame boundary and that a later
   reconfiguration can discard. Our fixup re-sends gamma and normal conditions but **not AID or CAPS**. If those were also reset, brightness
   and drive would be wrong in an unknown way. This is a correctness risk, not a confirmed cause.
4. **Fixed maximum brightness.** Normal stock use is the user's level (for example 111 cd at level 86) with AID dimming. Running at 360 cd
   all the time maximises the current, so any ELVSS or ACL error shows up most. Recovery mode on stock is also 360 cd, but with ACL on and ELVSS `1B`.
5. **mDNIe** has a negligible effect (white trim only).
6. **Gamma** is not a cause; it is identical to stock.

### F.4 Minimum a correct mainline driver must implement

**Rules:**

* Never leave the on-command ELVSS/ACL in effect. After init, after every DDI input reconfiguration (the fixup) and after every display
  on, send the **complete tuple in one burst, update key last**: `90`, `B0 4D/B2`, `B0 49/B2`, `B0 36/B2`, `B0 67/B2`,
  `B0 6D/B2`, `83 ...`, `B0 35/B2 01`. Stock does this in HS. LP also works for these registers, since the on-command list is LP.
* Treat (gamma[cd], AID[bl], ELVSS[cd, ACL, T], CAPS[cd], ACL) as one unit. AID values are only valid with the gamma of their row (B.1).
  Dimming with AID alone on the 360 cd gamma is wrong.
* Default operating point: ACL on (`05/7F/12`), smart-ACL ELVSS, normal-temperature table.

**Minimum viable state set** (gamma computed for this panel; ELVSS is the ACL-on normal-temperature value):

| bl | cd | AID packet | `B0 67/B2` | `B0 6D/B2` | `83` payload (33 B) |
|---|---|---|---|---|---|
| 255 | 360 | `90 00 00 0E` | 1B | 85 | `b3 d1 d5 c3 ba d3 db 36 94 80 00 c0 d1 d7 c2 bc d3 db 3c 8c 80 00 b8 d3 d6 c7 bd d5 dc 64 80 80 00` |
| 193 | 249 | `90 00 00 0E` | 1E | 85 | `b2 d3 d5 c3 be d6 dc 11 9d 80 00 bc d5 d6 c3 bf d6 dc 17 95 80 00 b4 d5 d6 c7 c1 d7 dd 3d 88 80 00` |
| 142 | 183 | `90 00 00 86` | 1F | 85 | `c2 ce d7 c5 be d7 de 10 96 80 00 d1 d3 d9 c4 bf d7 dd 17 91 80 00 ce d2 d7 c8 c1 d9 df 3d 84 80 00` (includes the B11 typo, C.4) |
| 86 | 111 | `90 00 00 99` | 21 | 85 | `c4 d6 d5 c6 c1 da e0 ec 9b 00 00 d7 dc d8 c7 c2 db df f1 96 00 00 c3 d7 d6 c9 c5 db e0 15 89 80 00` |
| 51 | 60 | `90 00 00 C9` | 21 | 85 | `d7 d9 d4 ca c2 db e2 cb c9 00 00 e5 e1 d8 cd c2 dc e3 d0 c9 00 00 d5 da d8 ca c5 dd e4 f2 c2 00 00` |
| 17 | 20 | `90 01 00 4D` | 1C | 81 | `e5 ea dc c8 c4 da e3 cb dd 00 00 ee ec e2 d0 c4 dc e4 d0 e3 00 00 e3 e9 df ca c6 dd e4 f3 df 00 00` |
| 0 | 2 | `90 01 00 7F` | 19 | 81 | `f3 f8 f7 e5 d3 de e4 c6 f9 00 00 f5 f8 fa ec dc e6 e8 d0 f9 00 00 ef f4 f5 e5 d6 e3 e5 f2 fa 00 00` |

Every row is followed by the ACL triple `B0 4D/B2 05, B0 49/B2 7F, B0 36/B2 12` and the update key, in the order of A.2.
These gammas are **specific to this panel's MTP**. A general driver should port C.2-C.4 (integer only; about 300 lines plus the
65-row offset tables and the 256-entry `curve_2p2_360`) and run it at probe from the MTP it already reads (OURS:213-268). It can then
expose all 256 levels with per-level AID from B.1.

**Optional:**

* Lowtemp tables, driven from the battery or charger thermistor (> 0 °C and > -20 °C trip points).
* ACL-off mode with the ACL-off ELVSS table.
* HBM. Needs reads of D4 @0x5B (33 B), D8 @0x81 and D2 @0x70.
* mDNIe UI_AUTO with white trim. Needs D8 @0x7B (4 B); bypass is an acceptable default.

---

## Appendix 1. Smart-dimming output for this panel (`83` payload, register order, MTP from DOC:204)

Produced by `re-tools/smartdim.py samsung-mdss/ss_dsi_smart_dimming_common.c samsung-mdss/ss_dsi_smart_dimming_ANA38401_AMS968HH01.h <33 MTP bytes>`.
The JSON (gamma and gray indices) is in `re-tools/gamma-table.json`.

| cd | 83 payload (R: V11 V23 V35 V51 V87 V151 V203 V255lo V3 V255hi VT, then G, then B) |
|---|---|
| 2 | `f3 f8 f7 e5 d3 de e4 c6 f9 00 00 f5 f8 fa ec dc e6 e8 d0 f9 00 00 ef f4 f5 e5 d6 e3 e5 f2 fa 00 00` |
| 3 | `f3 f9 ef e1 cd de e4 c8 f7 00 00 f8 fb f3 e8 d6 e5 e7 d0 f8 00 00 f2 f7 ef e1 d1 e2 e6 f2 f7 00 00` |
| 4 | `f3 f5 ee d6 ca db e4 ca f9 00 00 f8 f8 f4 dd d2 e1 e6 d0 fa 00 00 f1 f2 ee d7 cf df e6 f3 fa 00 00` |
| 5 | `f3 f5 ec d7 c9 db e3 ca f5 00 00 f8 f8 f2 dd d0 e1 e5 d0 f5 00 00 f1 f3 ec d8 ce df e5 f3 f5 00 00` |
| 6 | `f3 f2 ec d5 c7 dc e3 cb f0 00 00 f6 f6 f2 de cd e1 e5 d0 f0 00 00 f0 f0 eb d7 cb e0 e5 f3 f0 00 00` |
| 7 | `f4 f2 e8 d1 c5 dc e3 cb f3 00 00 f7 f4 ee da cb e0 e5 d0 f3 00 00 f2 ed e7 d4 c9 e0 e5 f3 f4 00 00` |
| 8 | `f1 ec ea cd c5 dd e3 cb f3 00 00 f3 ef f1 d8 ca df e5 d0 f3 00 00 f0 eb ea cf c9 de e5 f3 f3 00 00` |
| 9 | `f1 ee e2 cd c4 dc e4 cb f7 00 00 f3 f1 e9 d7 c9 df e5 d0 f7 00 00 ee ed e4 cf c8 df e5 f3 f7 00 00` |
| 10 | `f0 ea e1 cb c5 dc e3 cb ee 00 00 f2 ed e8 d7 c8 df e4 d0 f0 00 00 ef e9 e3 ce c8 df e4 f3 ef 00 00` |
| 11 | `f0 ea e1 cc c4 dc e3 cb e8 00 00 f2 ed e8 d8 c6 df e4 d0 eb 00 00 ef e9 e3 cf c6 df e4 f3 e9 00 00` |
| 12 | `f0 ea e4 ca c4 dc e3 cb e2 00 00 f2 ec eb d5 c6 df e4 d0 e6 00 00 ef e9 e6 cd c6 df e4 f3 e4 00 00` |
| 13 | `ec ea e3 cb c4 dc e3 cb df 00 00 ee ed eb d4 c6 df e4 d0 e5 00 00 eb e9 e6 ce c6 df e4 f3 e2 00 00` |
| 14 | `ea ea e2 ca c3 db e3 cb e5 00 00 ee ed ea d4 c6 de e4 d0 ea 00 00 e9 e9 e5 cc c7 de e4 f3 e7 00 00` |
| 15 | `e8 ea e1 c8 c2 dc e3 cb e5 00 00 ed ed e8 d1 c6 de e4 d0 e9 00 00 e7 e9 e4 ca c7 de e4 f3 e7 00 00` |
| 16 | `ec e9 dd c8 c2 dc e3 cb de 00 00 f2 ec e4 d1 c6 de e4 d0 e4 00 00 eb e9 e0 ca c7 de e4 f3 e0 00 00` |
| 17 | `ed ea dd c8 c4 dc e3 cb de 00 00 f2 ec e4 d1 c6 de e4 d0 e4 00 00 eb e9 df ca c7 de e4 f3 e0 00 00` |
| 19 | `e7 ea dd c8 c3 dc e3 cb dd 00 00 ee ec e4 d1 c5 de e4 d0 e3 00 00 e4 e9 df cb c7 de e4 f3 e0 00 00` |
| 20 | `e5 ea dc c8 c4 da e3 cb dd 00 00 ee ec e2 d0 c4 dc e4 d0 e3 00 00 e3 e9 df ca c6 dd e4 f3 df 00 00` |
| 21 | `e5 ea dc c8 c4 da e3 cb dd 00 00 ee ec e2 cf c4 dc e4 d0 e3 00 00 e3 e9 df ca c6 dd e4 f3 df 00 00` |
| 22 | `e4 e4 de c8 c5 da e3 cb e3 00 00 ee e7 e2 cf c4 dc e4 d0 e8 00 00 e2 e3 e0 ca c7 dd e4 f3 e5 00 00` |
| 24 | `e4 e8 dd c7 c3 da e3 cb e3 00 00 ee eb e1 ce c2 dc e4 d0 e8 00 00 e2 e7 df c9 c6 dd e4 f3 e5 00 00` |
| 25 | `e4 e7 dd c7 c3 da e3 cb e3 00 00 ed eb e1 ce c2 dc e4 d0 e8 00 00 e2 e7 df c9 c6 dd e4 f3 e5 00 00` |
| 27 | `e4 e1 dd c8 c3 da e3 cb ea 00 00 ed e6 e1 ce c2 dc e4 d0 ee 00 00 e1 e1 df c9 c6 dd e4 f3 eb 00 00` |
| 29 | `e4 e1 dd c9 c3 da e3 cb e2 00 00 ed e6 e1 ce c2 dc e4 d0 e8 00 00 e1 e1 e0 ca c6 dd e4 f3 e4 00 00` |
| 30 | `dd e5 d9 c9 c3 da e3 cb e9 00 00 e8 ea dc ce c2 dc e4 d0 ed 00 00 da e4 dc ca c6 dd e4 f3 eb 00 00` |
| 32 | `dd e5 d9 c9 c3 db e2 cb e9 00 00 e8 e9 dc ce c2 de e3 d0 ed 00 00 d9 e3 dc ca c6 de e3 f3 eb 00 00` |
| 34 | `dc de da c9 c3 db e2 cb f0 00 00 e7 e4 dc ce c2 de e3 d0 f3 00 00 d9 de dc ca c6 de e3 f3 f1 00 00` |
| 37 | `dc de da c9 c3 dc e2 cb f0 00 00 e7 e4 dc ce c2 de e3 d0 f3 00 00 d9 de dd ca c6 de e3 f3 f1 00 00` |
| 39 | `dc de de c5 c3 dc e2 cb e9 00 00 e7 e4 e0 cb c2 de e3 d0 ed 00 00 d9 de e0 c7 c6 de e3 f3 ea 00 00` |
| 41 | `e2 dc da c6 c3 dc e2 cb e1 00 00 ed e3 dc cb c2 de e3 d0 e7 00 00 de dc dc c8 c6 de e3 f3 e3 00 00` |
| 44 | `db dc d9 c7 c4 da e2 cc e8 00 00 e7 e3 dc cb c4 dc e3 d0 ed 00 00 d7 dc dc c8 c7 dd e3 f3 ea 00 00` |
| 47 | `da dc d9 c8 c2 db e2 cc dc 00 00 e7 e3 dc cd c2 dc e3 d0 df 00 00 d7 dc dc c9 c5 dd e3 f3 db 00 00` |
| 50 | `da dc d9 c8 c2 db e2 cc dc 00 00 e6 e3 dc cd c2 dc e3 d0 df 00 00 d6 dc dc c9 c5 dd e3 f3 db 00 00` |
| 53 | `d2 e0 d4 c9 c2 db e2 cc e3 00 00 e0 e6 d8 cd c2 dc e3 d0 e5 00 00 d0 e0 d9 ca c5 dd e3 f3 e1 00 00` |
| 56 | `d2 e0 d4 c9 c2 db e2 cc d6 00 00 e0 e6 d8 cd c2 dc e3 d0 d7 00 00 d0 e0 d9 ca c5 dd e3 f3 d2 00 00` |
| 60 | `d7 d9 d4 ca c2 db e2 cb c9 00 00 e5 e1 d8 cd c2 dc e3 d0 c9 00 00 d5 da d8 ca c5 dd e4 f2 c2 00 00` |
| 64 | `d7 d9 d7 c6 c2 db e2 cb c9 00 00 e5 e1 db c9 c2 dc e3 d0 c9 00 00 d5 da db c7 c5 dd e4 f2 c2 00 00` |
| 68 | `d0 d9 d7 c6 c4 db e1 cb d0 00 00 e2 e2 dc c9 c3 dc e2 d0 ce 00 00 cd da da c7 c6 dd e3 f2 c8 00 00` |
| 72 | `d0 d9 d8 c6 c4 db e1 cb c3 00 00 e2 e2 dc c9 c3 dc e2 d0 c0 00 00 ce da db c7 c7 dd e2 f2 b8 00 00` |
| 77 | `d0 d9 d6 c7 c2 da e2 d1 c3 00 00 e2 e2 d9 c9 c2 dc e2 d5 c0 00 00 ce db d8 c7 c6 dc e3 f9 b8 00 00` |
| 82 | `d1 d4 d4 c7 c1 db e1 d5 c3 00 00 e2 de d9 ca c1 dc e2 d9 c0 00 00 ce d6 d7 c9 c4 dd e3 fc b8 00 00` |
| 87 | `ca d7 d7 c7 c1 db e0 da c3 00 00 dc df db c9 c2 dc e0 dd c0 00 00 c7 d9 d9 c8 c5 dd e1 01 b8 80 00` |
| 93 | `cb d6 d4 c7 c2 da e1 de c3 00 00 dc df d8 c8 c2 db e1 e3 c0 00 00 c8 d8 d6 c8 c6 db e2 06 b8 80 00` |
| 98 | `ca d3 d6 c8 c0 db df e2 b6 00 00 dc db d9 c9 c0 dc e0 e7 b2 00 00 c8 d5 d8 c9 c3 dd e1 0a a9 80 00` |
| 105 | `cc d5 d5 c7 c1 d9 df e7 af 00 00 dc dc da c8 c2 da df ec ad 00 00 ca d6 d9 ca c5 db e1 10 a3 80 00` |
| 111 | `c4 d6 d5 c6 c1 da e0 ec 9b 00 00 d7 dc d8 c7 c2 db df f1 96 00 00 c3 d7 d6 c9 c5 db e0 15 89 80 00` |
| 119 | `c7 d7 d6 c6 c0 d9 e0 f2 96 00 00 d7 dd d9 c6 c1 da df f7 91 00 00 c6 da d7 c8 c3 db e0 1b 84 80 00` |
| 126 | `c6 d4 d7 c5 c0 d9 de f7 96 00 00 d7 da da c5 c1 da de fc 91 00 00 c6 d7 d8 c7 c3 db e0 21 84 80 00` |
| 134 | `c6 d4 d4 c5 bf d9 de fc 96 00 00 d7 da d7 c6 c0 da de 02 91 80 00 c6 d6 d6 c8 c2 da e0 26 84 80 00` |
| 143 | `c0 d6 d5 c5 bf d7 df 02 a3 80 00 d2 db d9 c5 c1 d8 de 07 9f 80 00 c0 d8 d7 c8 c3 d9 df 2c 94 80 00` |
| 152 | `c1 d1 d7 c5 bf d8 dd 07 a3 80 00 d2 d7 da c5 c0 d9 dd 0c 9f 80 00 c0 d5 d8 c8 c2 da df 31 94 80 00` |
| 162 | `c0 d2 d5 c5 bf d7 dd 0c a3 80 00 d2 d6 d7 c5 c0 d8 dd 11 9f 80 00 c0 d5 d5 c9 c2 d9 df 37 94 80 00` |
| 172 | `c1 ce d7 c5 be d7 de 10 96 80 00 d2 d4 d9 c4 bf d7 dd 17 91 80 00 c1 d2 d7 c8 c1 d9 df 3d 84 80 00` |
| 183 | `c2 ce d7 c5 be d7 de 10 96 80 00 d1 d3 d9 c4 bf d7 dd 17 91 80 00 ce d2 d7 c8 c1 d9 df 3d 84 80 00` |
| 195 | `bb d3 d6 c4 bc d7 dd 11 9b 80 00 cb d6 d7 c4 bf d7 dd 17 96 80 00 bd d5 d7 c7 c0 d9 de 3d 89 80 00` |
| 207 | `bb d3 d6 c4 bc d7 dd 11 9b 80 00 ca d6 d7 c4 bf d7 dd 17 96 80 00 be d5 d7 c7 c0 d9 de 3d 89 80 00` |
| 220 | `ba cf d6 c4 be d6 dd 11 a1 80 00 c9 d1 d7 c4 bf d6 dd 17 9a 80 00 bd d0 d7 c7 c1 d8 de 3d 8e 80 00` |
| 234 | `b9 d0 d6 c5 bc d6 dd 11 93 80 00 c9 d1 d7 c5 be d6 dd 17 8b 80 00 bd d1 d7 c9 c0 d8 de 3d 7d 80 00` |
| 249 | `b2 d3 d5 c3 be d6 dc 11 9d 80 00 bc d5 d6 c3 bf d6 dc 17 95 80 00 b4 d5 d6 c7 c1 d7 dd 3d 88 80 00` |
| 265 | `bd d0 d4 c5 be d4 dc 17 93 80 00 c8 d1 d5 c4 bf d5 dc 1d 8b 80 00 c1 d2 d5 c8 c1 d6 dd 43 7d 80 00` |
| 282 | `b7 d2 d2 c7 bd d5 dc 1d 93 80 00 c4 d3 d4 c6 be d5 dc 23 8b 80 00 bc d4 d4 ca c0 d6 dd 49 7d 80 00` |
| 300 | `b7 d2 d2 c4 bc d5 db 24 93 80 00 c4 d3 d4 c3 be d5 db 2a 8b 80 00 bc d4 d4 c7 bf d6 dc 51 7d 80 00` |
| 316 | `b2 d0 d7 c3 bc d4 dc 29 93 80 00 bf d0 d9 c2 be d4 dc 2f 8b 80 00 b7 d2 d8 c7 bf d6 dd 56 7d 80 00` |
| 333 | `af d4 d4 c4 bb d3 dc 2e 93 80 00 bc d4 d6 c3 bd d3 dc 34 8b 80 00 b4 d6 d5 c8 be d5 dd 5b 7d 80 00` |
| 360 | `b3 d1 d5 c3 ba d3 db 36 94 80 00 c0 d1 d7 c2 bc d3 db 3c 8c 80 00 b8 d3 d6 c7 bd d5 dc 64 80 80 00` |

## Appendix 2. Tools (in `re-tools/`)

* `dtparse.py`: decodes the compiled DT node, including cell-encoded byte arrays, into DSI packets.
* `dtsiparse.py`: compares the live node with the dtsi. Result: 94/94 valued properties equal; boolean sets equal.
* `tables.py`: produces table B.1 from the live node (`table-b.md`).
* `smartdim.py`: bit-exact port of Samsung smart dimming. `smartdim_check.py` evaluates the model at 360 cd.
* `mdnie_diff.py`: field-level diff of mDNIe blocks.
