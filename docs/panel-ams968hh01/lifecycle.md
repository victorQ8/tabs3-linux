# AMS968HH01 / ANA38401 on the stock SM-T825 kernel: power-on, first frame, sleep and wake

> **File references.** `samsung-mdss/`, `samsung-extra/`, `fetched-mdss-fb/` and `re/dl/` hold files
> from Samsung's kernel, [awesometic/android_kernel_samsung_msm8996 @ f48aec90](https://github.com/awesometic/android_kernel_samsung_msm8996/tree/f48aec90fcebf4615fdee4a8abac7339930db856)
> (`drivers/video/msm/mdss/` and `drivers/video/msm/mdss/samsung/ANA38401_AMS968HH01/`).
> `stock-live-panel-node.dts` is lines 3276-3700 of the private stock DT backup
> (`private/backups/20261010T094140Z/live.dts`). `OURS` / `ours-20261011.c` is our driver as on the tablet
> on 2026-10-11 (patches up to `0027`), saved next to this report. Analysis scripts are kept outside
> the repository except [`tools/panel/smartdim.py`](../../tools/panel/smartdim.py).
> Summary and conclusions: [../panel-ams968hh01.md](../panel-ams968hh01.md).

This is a reconstruction from Samsung's GPL MDSS sources (commit `f48aec90`, `awesometic/android_kernel_samsung_msm8996`). The aim is to explain the three symptoms seen on our mainline driver. It is based only on reading source. No tablet or USB device was touched.

## 0. Sources, abbreviations, and how to read the tags

| Tag | Path |
|---|---|
| `SM/` | `samsung-mdss/` (the inputs provided) |
| `SX/` | `samsung-extra/`: `mdss_fb.c`, `mdss_mdp_overlay.c`, `mdss_mdp_ctl.c`, `mdss_dsi_cmd.c` and `mdss_io_util.c`, fetched from the same commit (`drivers/video/msm/mdss/`) |
| `dtsi` | `SM/dsi_panel_ANA38401_AMS968HH01_qxga_octa_cmd.dtsi` (global variant) |
| `live-node` | `SM/stock-live-panel-node.dts` (the panel node from the tablet's real DT) |
| `LIVE` | `private/backups/20261010T094140Z/live.dts` (the complete stock live DT, read only for the board's `ss_regulator` node and pinctrl) |
| `ML/` | `work/linux-v6.19.5-msm8996/drivers/gpu/drm/msm/dsi/` (the mainline host we run on) |
| `OURS` | `ours-20261011.c` |

Here `` is ``.

- **[P]** means the source shows it directly (a file:line is given).
- **[I]** means it is inferred: plausible and consistent with the source, but not shown by it.

**Which DT the tablet actually uses [P].** I decoded the `qcom,mdss-dsi-on-command` u32 blob in `live-node:9` byte by byte with `re-scripts/decode_on.py`. The result is identical to the global `dtsi:29-94`: 28 packets, the 215 ms wait on `B1 1D`, and `29` last. The clock rate is `0x353d2680` = 893.2 MHz (`live-node:52`). The USA variant (`SM/..._usa.dtsi`) differs in two ways:

- It adds `B0 56 / B1 4C` ("Porch Setting: Htotal 3224", `usa.dtsi:33-34`).
- It uses 895.4 MHz (`usa.dtsi:85`).

**That variant does not apply to this tablet.**

---

## 1. Key findings (summary)

1. **Display-on is part of the on-command list and is not deferred [P].**
   - `29h` is the last packet of `qcom,mdss-dsi-on-command` (`dtsi:93`). It follows `B0 D0 / B1 1D` ("UPLL_F = 35") and its 215 ms wait (`dtsi:90-91`).
   - Samsung's deferred-display-on mechanism exists. `wait_disp_on` is set in `on_post` and fires on the first `MDSS_SAMSUNG_EVENT_FRAME_UPDATE` (`SM/ss_dsi_panel_common.c:1701`, `:342-361`). For this panel it is deliberately empty: `samsung,display_on_tx_cmds_revA` is commented out (`dtsi:297`), and `live-node` has no such property. The frame-update hook therefore sends nothing (`ss_dsi_panel_common.c:1349-1353`).
2. **Normal drive conditions follow display-on but come before the first frame [P].**
   - The on-command list deliberately leaves the panel in a cold-start state: ACL off (`dtsi:76-80`) and ELVSS `0x0F` (`dtsi:73-74`). `0x0F` is the 360 cd entry of the low-temperature table (`dtsi:767`), not the normal one.
   - Immediately after the list, `mdss_samsung_panel_on_post()` sends the full brightness block in HS mode (`ss_dsi_panel_common.c:1669-1683`, `:734-736`): AID, ACL on at 15%, smart-ACL ELVSS (`0x1B` at 360 cd), CAPS, and MTP gamma with the update key. It then sends mDNIe in HS (`:1685-1690`), and then `35h` tear-on in LP (`SM/mdss_dsi.c:1916-1919`).
   - Only after that is the first frame kicked off (`SM/mdss_mdp_intf_cmd.c:2772-2773` then `:2855-2856`).
   - The brightness block is sent again after the first commit (`SX/mdss_fb.c:3791-3792`, `:1753-1781`).
3. **Samsung has no dual-link or compression workaround [P].**
   - `B0 51 / B1 06` (dual DSI) and `B0 D9 / B1 08` (compression) are written once per power-on, in LP, inside the on-command list (`dtsi:36-40`). No C code touches them, and nothing toggles them later.
   - On the very first power-on after boot only, `manufacture_read_pre_tx_cmds` also writes them, in HS and in the opposite order (D9 then 51), before the ID reads (`dtsi:277-289`; `ss_dsi_panel_common.c:1477-1498`, with `manufacture_id_dsi = PBA_ID` initially at `:750`).
   - All DCS traffic goes to DSI0 only (`qcom,dcs-cmd-by-left`, `dtsi:101`). Sync/broadcast is disabled (`dtsi:102-103`).
4. **The stock link and reset order differs from ours in one concrete way [P].**
   - Stock brings both DSI PHYs up and forces every lane, clock lane included, into LP-11 stop state (`LANE_CTRL = 0x1F<<16`). It holds that through the 75 ms pre-reset sleep, the reset release (GPIO143 high) and the TCON_RDY poll (GPIO45, up to 1 s). Only then does it force the clock lane into continuous HS on both links (`SM/mdss_dsi.c:1652-1731`).
   - Mainline msm forces continuous HS in `msm_dsi_host_power_on()` (`ML/dsi_host.c:878-886`). It does that in the bridge `pre_enable` (`ML/dsi_manager.c:284-326`), which runs before our panel `prepare()` because of `prepare_prev_first` (`OURS:805`).
   - So the ANA38401 comes out of reset with HS clocks already running on both links.
   - **[I]** This is the most concrete source-backed candidate for symptom 1 (the DDI latching single-link/compressed input until the compression register is changed).
5. **Stock never wakes this panel with 28h/29h [P].**
   - LPM/ALPM is not enabled: there is no `samsung,panel-lpm-enable`, so `mdss_samsung_panel_lpm_ctrl` returns early (`ss_dsi_panel_common.c:5457-5460`). `display_off_tx_cmds` is only used by that LPM path (`:5480`).
   - Every screen-off is a full power-down: brightness to 0, then `28h` (HS, 100 ms), then reset low (+5 ms), then VDD (GPIO46) off (+25 ms).
   - Every wake is a cold start, with the full on-command list, the HS drive block, mDNIe, and a first frame within one TE.
   - An ESD interrupt (GPIO121, falling edge) is armed after `on_post` and triggers a full re-init (`ss_dsi_panel_common.c:1703-1707`, `:2117-2162`).
   - Our backlight-based 28h/29h sleep therefore operates outside anything Samsung validated.
6. **Symptom 2 is explained by the source [P + I].**
   - **[P]** Stock never shows content with the on-command list's cold-start ACL/ELVSS. They are replaced in HS after `29h` and before the first frame, and on every brightness change. ACL is on by default (`ss_dsi_panel_ANA38401_AMS968HH01.c:1015-1017`).
   - **[I]** With ACL off and low-temperature ELVSS, large bright areas overload the OLED supply, which matches our -1.47 A → +0.16 A battery current change. The LP-versus-HS difference is probably secondary: the cold-start values are themselves written in LP. What matters is that the normal values are written after display-on and after the compression change, which is the stock order.

---

## 2. (A) Complete power-on sequence

### 2.1 Pins and supplies [P]

| Signal | Stock source | Value |
|---|---|---|
| Panel VDD (3.3 V) | `ssreg-vdd`, a fixed regulator on **GPIO46**, active high, `regulator-boot-on` | `LIVE:20251-20258` |
| Panel reset | `ssreg-panelrst` on **GPIO143** (flags 0x02 = init high); `panel-rst-seq = <1 0>`, so it just drives high with no low pulse | `LIVE:20238-20243`; `SM/ss_regulator_common.c:208-247` |
| TCON_RDY | `ssreg-tconrdy` on **GPIO45** (input). `enable()` polls it every 1 ms up to `MAX_WAITTIME_TCONRDY` = 1000 ms and only logs on timeout | `LIVE:20245-20249`; `ss_regulator_common.c:141,276-296` |
| ESD | `samsung,esd-irq-gpio1 = <&tlmm 121 0>`, `irq-trigger1 = "falling"`, mode `reg_read_irq` | `live-node:111`; `dtsi:221-223`; `ss_dsi_panel_common.c:3804-3885` |
| TE | `qcom,platform-te-gpio = <&tlmm 10>` | `LIVE:3516` |
| DSI host | `vdda` = L2 1.25 V, `vcca` = L28 0.925 V. `oled-vdda` (L19 2.2 V) and `vddio` (L14 1.8 V) are listed on the controller nodes but **not** in any `qcom,*-supply-entries`, so the display driver never switches them | `live-node:193-219,228-229` |

The panel's `qcom,mdss-dsi-reset-sequence` is commented out with "use fake_regulators in board dtsi" (`dtsi:203-206`). Since `rst_gpio` is invalid, `mdss_dsi_panel_reset()` is a no-op (`SM/mdss_dsi_panel.c:449-453`). The reset is entirely the `ssreg-panelrst` "regulator".

### 2.2 Supply-entry timings [P] (`live-node:115-157`)

| List | Entry | pre-on | post-on | post-off |
|---|---|---|---|---|
| `qcom,panel-supply-entries` (switched at panel power on/off) | ssreg-vdd | - | **10 ms** | **25 ms** |
| `qcom,panel-supply-entries-lp11` (switched in the LP-11 block) | ssreg-panelrst | **75 ms** | 0 | **5 ms** |
| | ssreg-tconrdy | - | 0 | - |

Two details of `msm_dss_enable_vreg()` (`SX/mdss_io_util.c:260-311`) matter here:

- Pre- and post-on sleeps happen only if `!regulator_is_enabled()` (`:273-288`). `is_enabled` for panelrst is the GPIO143 level, and for tconrdy it is the GPIO45 level (`ss_regulator_common.c:249-266,304-316`).
- Off sleeps always happen (`:297-310`).

Unused DT values: `samsung,mdss-power-on-reset-delay-us = 70000` and `samsung,mdss-power-off-delay-us = 10000` (`dtsi:251-252`). The first is parsed and never used (`ss_dsi_panel_common.c:3907-3908`). The second is not parsed at all. The real delays are the ones in the table above.

### 2.3 Call chain from unblank to first frame (command mode, split DSI)

In command mode the panel is **not** turned on at unblank. It is turned on by the first kickoff:

> "the panel is turned on only when we send the first frame and not during cmd start. This is to ensure that no artifacts are seen on the panel." (`SM/mdss_mdp_intf_cmd.c:2767-2773`)

Interface events go to DSI0 (master) first and then to `pdata->next` (DSI1) (`SX/mdss_mdp_ctl.c:3971-3976`).

| # | Step | Detail | Citation |
|---|---|---|---|
| 0 | `fb` unblank | `mdp.on_fnc` (command-mode CTL start, no panel I/O). The user brightness is pushed while `allow_bl_update` is briefly true, but `mdss_samsung_send_cmd()` drops it while `blank_state == BLANK`. `vdd->bl_level` is still recorded, at `ss_dsi_panel_common.c:2677`. Then `allow_bl_update = false`: "blocks the backlight update between unblank and first kickoff" | `SX/mdss_fb.c:1974-1997`; `ss_dsi_panel_common.c:1322-1325` |
| 1 | First commit → `mdss_mdp_cmd_kickoff` → `mdss_mdp_cmd_panel_on` | Sends `LINK_READY`, `UNBLANK`, `PANEL_ON`, then enables tear-check | `mdss_mdp_intf_cmd.c:2772-2773,2166-2187` |
| 2 | `LINK_READY`, DSI0 → `mdss_dsi_on` | ESD IRQ line enabled (the handler ignores it until step 6) | `mdss_dsi.c:3014-3022,1566-1567` |
| 2a | | `panel_power_ctrl(ON)` → ssreg-vdd on, **+10 ms** if it was off. `lp11_init` is set, so no reset here | `mdss_dsi.c:1582,342-389` |
| 2b | | Clock source, core clock, PHY software reset and init, controller setup, link clocks on, DSI software reset | `mdss_dsi.c:1604-1646` |
| 2c | | `samsung_lp11_init`: `LANE_CTRL(0xAC) = 0x1F<<16`, which forces TX-stop (LP-11) on DLN0-3 (bits 16-19) and the clock lane (bit 20, see `SM/mdss_dsi_host.c:640-647`). Then **1 ms** (`init_delay`) | `mdss_dsi.c:1653-1663` |
| 2d | | DSI0 is not the right controller, so no LP-11 regulators and no reset. The pinctrl is set to active. `LANE_CTRL` is restored, then **1 ms**. No HS clock yet | `mdss_dsi.c:1665-1698,1703-1724` |
| 2e | | `op_mode_config(CMD)` sets the default DMA mode to **LP** (`BIT(26)`) | `mdss_dsi.c:3021-3022`; `mdss_dsi_host.c:1079` |
| 3 | `LINK_READY`, DSI1 → `mdss_dsi_on` | Same 2a-2c on DSI1 (VDD is already on, so no sleep). DSI1 lanes forced LP-11, **1 ms** | as above |
| 3a | | Split, `samsung_lp11_init` and right controller, so the LP-11 regulators are enabled twice "for balance of use_count". The first call sleeps **75 ms** (pre-on), drives **GPIO143 high** (reset released) and polls **TCON_RDY (GPIO45) up to 1 s**. The second call has no sleeps | `mdss_dsi.c:1665-1677`; `ss_regulator_common.c:208-230,276-296` |
| 3b | | `LANE_CTRL` restored, **1 ms**, then **`CLKLN_HS_FORCE_REQUEST` (bit 28) set on DSI0 and DSI1**. This is the first moment the continuous HS clock reaches the TCON (`qcom,mdss-dsi-force-clock-lane-hs`, `dtsi:149`) | `mdss_dsi.c:1690-1718` |
| 4 | `UNBLANK` (on-commands are LP, so it runs here) → `mdss_dsi_unblank` → `ctrl->on` = `mdss_dsi_panel_on` | DSI1 returns at `dcs_cmd_by_left`, so only DSI0 sends | `mdss_dsi.c:3024-3028,1903-1914`; `mdss_dsi_panel.c:960-963` |
| 4a | | `blank_state = READY_TO_UNBLANK`, then `mdss_samsung_panel_on_pre` (§2.5) | `mdss_dsi_panel.c:966,1011-1019` |
| 4b | | **On-command list, LP, DSI0 only** (§2.4). Each packet is its own DMA (`last = 1`). `wait` is in ms, applied after the packet (`mdss_dsi_host.c:1733-1753`): 215 ms after `B1 1D`, then `29h` | `mdss_dsi_panel.c:1023-1033,223-227` |
| 4c | | `blank_state = UNBLANK`, then `mdss_samsung_panel_on_post` (§2.6): **HS brightness block, HS mDNIe**, `wait_disp_on = 1`, ESD armed | `mdss_dsi_panel.c:1048-1058`; `ss_dsi_panel_common.c:1619-1712` |
| 4d | | **`35 00` tear-on** (DCS short write with 1 parameter, no HS flag, so LP), DSI0 only | `mdss_dsi.c:1916-1919`; `SX/mdss_dsi_cmd.c:679-704` |
| 5 | `PANEL_ON` | Nothing for LP on-commands; `esd_rdy = true` | `mdss_dsi.c:3033-3039` |
| 6 | Tear-check enable; kickoff | ESD-recovery event (no recovery commands defined for this panel), `CMDLIST_KOFF`, then `__mdss_mdp_kickoff`. **The first frame goes out on both links at the next TE**, about one TE (≤ 16.7 ms) after step 4d | `mdss_mdp_intf_cmd.c:2185,2803-2818,2855-2856` |
| 7 | After the commit | `mdss_fb_update_backlight()`: if a level is pending, `set_backlight` sends the **brightness block again (HS)** and `allow_bl_update = true` | `SX/mdss_fb.c:3791-3792,1753-1781` |
| 8 | After the commit | `MDSS_SAMSUNG_EVENT_FRAME_UPDATE` → `wait_disp_on` → `PANEL_DISPLAY_ON` → `display_on_tx_cmds` is empty, so it logs "no panel_cmds" | `SX/mdss_mdp_overlay.c:3055-3057`; `ss_dsi_panel_common.c:342-361,1121-1123,1349-1353` |

**[P]** From VDD on to the first command takes about 10 ms + 1 ms + 1 ms + (DSI1 init) + 1 ms + 75 ms + t(TCON_RDY) + 1 ms, so roughly 90 ms plus the TCON_RDY time.

**[P]** `samsung,tcon-clk-on-support` (`dtsi:249`) does three things:

- It skips the extra DSI clock-off at the end of unblank (`mdss_dsi.c:1938-1941`).
- It skips the clock-on in blank (`:1970-1973`).
- Most importantly, it skips `mdss_mdp_resource_control(PP_DONE)` after every frame (`mdss_mdp_intf_cmd.c:1224-1231`).

**[I]** The link, and with it the HS clock that feeds the TCON, is therefore never gated between frames. Mainline msm also keeps link clocks on from `pre_enable` to `post_disable`, so this matches what we have.

### 2.4 On-command list, decoded [P] (`dtsi:29-94`, LP via `dtsi:187`; identical to `live-node:9`)

The header format is `dtype last vc ack wait dlen(16-bit)`.

Data types:

| dtype | Meaning |
|---|---|
| `15` | DCS short write, 1 parameter |
| `39` | DCS long write |
| `05` | DCS short write, no parameter |
| `06` | DCS read |
| `24` | Generic read, 2 parameters |
| `37` | Set maximum return packet size |

`B0 nn` is the "Global Para" offset. Samsung's comments use the decimal index, so `B0 51` = "81st". It selects the offset for the next `B1` or `B2` long write, and also for reads (`reg_read_pos`, `dtsi:265-267`). `B1` and `B2` are two register banks written at that offset.

All packets are sent on DSI0 only, in LP.

| # | dtsi | Header | Payload | Samsung's comment and meaning | Wait after |
|---|---|---|---|---|---|
| 0 | 30 | 15 01 00 00 00 0002 | `B0 34` | Global Para (index 52) | 0 |
| 1 | 31 | 39 01 00 00 00 0003 | `B2 64 00` | "check fail off". Writes B2[0x34]=0x64 and B2[0x35]=0x00. Note 0x35 is also the gamma update-key offset | 0 |
| 2 | 33 | 15 … 0002 | `B0 75` | Global Para 117th | 0 |
| 3 | 34 | 39 … 0002 | `B2 28` | INTR setting | 0 |
| 4 | 36 | 15 … 0002 | `B0 51` | Global Para 81st | 0 |
| 5 | 37 | 39 … 0002 | `B1 06` | **dual DSI setting** | 0 |
| 6 | 39 | 15 … 0002 | `B0 D9` | Global Para 217th | 0 |
| 7 | 40 | 39 … 0002 | `B1 08` | **Anapass compression mode setting** | 0 |
| 8 | 42 | 15 … 0002 | `B0 7F` | Global Para 127th | 0 |
| 9 | 43 | 39 … 0002 | `B2 15` | TSP_HTE / TSP_VTE (touch sync) | 0 |
| 10 | 45 | 39 … 0003 | `44 05 F6` | DCS set_tear_scanline = 1526 | 0 |
| 11 | 47 | 15 … 0002 | `B0 BC` | Global Para 188th "??" | 0 |
| 12 | 48 | 39 … 0002 | `B2 04` | Gamma offset index = 4 "??". The HBM gamma is built "for Gamma Offset Index 4" (`ss_dsi_panel_ANA38401_AMS968HH01.c:577-582`) | 0 |
| 13 | 50-68 | 39 … 0022 | `83` + 33 bytes, 3 × `80 80 80 80 80 80 80 00 80 80 00` | Brightness condition set: reference gamma, without MTP | 0 |
| 14 | 71 | 39 … 0004 | `90 00 00 0E` | AID for 360 nit, the same as `aid_subdivision[255]` (`dtsi:607`) | 0 |
| 15 | 73 | 15 … 0002 | `B0 67` | Global Para 103rd | 0 |
| 16 | 74 | 39 … 0002 | `B2 0F` | "360 nit ELVSS". **This is the low-temperature table value** (`dtsi:767`). Normal is `19` with ACL off (`dtsi:725`) and `1B` with ACL on (`dtsi:927`) | 0 |
| 17 | 76 | 15 … 0002 | `B0 4D` | Global Para 77th | 0 |
| 18 | 77 | 39 … 0002 | `B2 04` | 16-frame average (ACL-off style) | 0 |
| 19 | 79 | 15 … 0002 | `B0 36` | Global Para 54th | 0 |
| 20 | 80 | 39 … 0002 | `B2 10` | **ACL off** | 0 |
| 21 | 82 | 15 … 0002 | `B0 6D` | Global Para 109th | 0 |
| 22 | 83 | 39 … 0002 | `B2 85` | CAPS on | 0 |
| 23 | 85 | 15 … 0002 | `B0 35` | Global Para 53rd | 0 |
| 24 | 86 | 39 … 0002 | `B2 01` | Gamma update key | 0 |
| - | 88 | - | - | "/* ELVSS Temp Compensation */": a comment with no packet | - |
| 25 | 90 | 15 … 0002 | `B0 D0` | Global Para 208th | 0 |
| 26 | 91 | 39 01 00 00 **D7** 0002 | `B1 1D` | "UPLL_F = 35 then delay 215ms" | **215 ms** |
| 27 | 93 | 05 01 00 00 00 0002 | `29 00` | **display on**. The comment says "then 50ms delay??" but the wait is 0 | 0 |

There is no `11h` (sleep out) and no `10h` (sleep in) anywhere in this panel's life cycle [P]. Our driver doesn't send them either.

### 2.5 Before the on-commands: `mdss_samsung_panel_on_pre` [P] (`ss_dsi_panel_common.c:1427-1617`)

The reads happen **before** the on-command list, right after reset and TCON_RDY with the HS clock on. Except for the DDI-ID attempt, they are done **once per boot**, guarded by the `*_loaded` flags.

1. **First power-on only** (`manufacture_id_dsi[0] = PBA_ID` from `:750`, so `== PBA_ID` at `:1477`):
   - `manufacture_read_pre_tx_cmds` is sent with `CMD_REQ_COMMIT`. Samsung's link state defaults to HS (`mdss_dsi_panel.c:1397-1399`) (`:1493-1498`): `B0 34 / B2 64 00`, **`B0 D9 / B1 08`, `B0 51 / B1 06`**, `B0 75 / B2 28` (`dtsi:277-289`).
   - Then three DCS reads `06 DA`, `06 DB`, `06 DC`, 1 byte each (`dtsi:291-293`). Each is preceded by `15 B0 00` (`reg_read_pos`, `dtsi:265-267`; `ss_dsi_panel_common.c:1039-1045`).
   - The ID becomes `0x424016`, so later wakes skip all of this. The panel revision is always 'A' (`ss_dsi_panel_ANA38401_AMS968HH01.c:80-85`).
2. Manufacture date: `24 D8 02`, 2 bytes at offset `0x7F` (`dtsi:295`; `ss_dsi_panel_ANA38401_AMS968HH01.c:93-132`).
3. DDI ID: there is no `ddi_id_rx_cmds`, so the attempt runs on **every** power-on but does nothing (`ANA38401.c:146-161`).
4. HBM MTP:
   - `24 D4 08` at 0x5B, 0x63, 0x6B, 0x73 (8 bytes each) and 0x7B (1 byte).
   - `24 D8 01` at 0x81, which goes into the HBM ELVSS.
   - `24 D2 01` at 0x70, which goes into the HBM-off ELVSS.
   - The function mutates `read_startoffset` in place (`ANA38401.c:310-366`).
5. mDNIe white point: `24 D8 04` at 0x7B. Coordinate tuning picks the tune index (`ANA38401.c:499-535`).
6. Smart-dimming MTP: `24 D8 08` at 0x5A, 0x62, 0x6A, 0x72 and `24 D8 01` at 0x7A, 33 bytes in all (`dtsi:269`; `ANA38401.c:537-602`). It also adds the MTP to the HBM table ("for Gamma Offset Index 4") and sets `temperature = 20` (`:594`).
7. Panel hook: `mdss_panel_attach_set(true)` only (`ANA38401.c:36-50`).

**[P]** Read requests use `CMD_REQ_RX|CMD_REQ_COMMIT` with no HS flag (`mdss_dsi_panel.c:3204-3232`), so they go out in the controller's default DMA mode, which `op_mode_config` sets to LP (`mdss_dsi_host.c:1079`). The `B0 nn` position writes before each read are HS (`reg_read_pos_tx` parsed with the HS default, `mdss_dsi_panel.c:1397-1399`).

**[I]** Our finding that "the DDI answers reads only in HS" is therefore about the mainline host's LP-read path, not a stock requirement. Treat the comment at `OURS:75-77` as unproven.

### 2.6 After the on-commands: `mdss_samsung_panel_on_post` [P] (`ss_dsi_panel_common.c:1619-1712`)

1. CABC and TFT hooks: none for this OLED. The panel's `on_post` hook is empty (`ANA38401.c:52-62`).
2. Recovery boot: `bl_level = DEFAULT_BRIGHTNESS` (255) (`:1662-1664`; `ss_dsi_panel_common.h:78`).
3. **`mdss_samsung_brightness_dcs(ctrl, vdd->bl_level)`** (`:1669-1683`). This builds the "single transmission" packet (`:2662-2740`, `:2448-2634`, `:2636-2660`). It is sent by `mdss_samsung_send_cmd(PANEL_BRIGHT_CTRL)` on DSI0 in **HS** (`:734-736`; `mdss_dsi_panel.c:226-227`). Order and content at bl 255 (360 cd), with ACL on (default `acl_status = 1`, `gradual_acl_val = 0x12`, `ANA38401.c:1015-1017`) and temperature 20 °C:

   | # | Packet | Source |
   |---|---|---|
   | 1 | `39 90 00 00 0E` (AID) | `aid_subdivision[bl]`, `dtsi:607`; `ANA38401.c:617-621` |
   | 2-7 | `15 B0 4D` `39 B2 05` (32-frame average) `15 B0 49` `39 B2 7F` (start 50%) `15 B0 36` `39 B2 12` (**ACL 15%**) | `dtsi:700-707`; cmds[5] is overwritten by `gradual_acl_val` at `ANA38401.c:654-656` |
   | 8-9 | `15 B0 67` `39 B2 1B` (**smart-ACL ELVSS**, 360 cd) | `dtsi:723,927`; map `dtsi:1117`; `ANA38401.c:702-713` |
   | 10-11 | `15 B0 6D` `39 B2 85` (CAPS) | `dtsi:617-623,692`; `ANA38401.c:739-784` |
   | 12-14 | `39 83 <33-byte smart-dimming gamma>` `15 B0 35` `39 B2 01` (update key) | `dtsi:300-310`; `ANA38401.c:786-812` |

   The ELVSS table selection is `acl_status || siop_status` → smart-ACL tables, otherwise the normal tables. Each has three temperature bands: > 0, > -20, ≤ -20 (`ANA38401.c:702-726`). Levels above 255 (up to 355) use the HBM path (`dtsi:321-342,1194-1203`; `ANA38401.c:166-308`).
4. **mDNIe** (`:1685-1690`) → `update_dsi_tcon_mdnie_register()` (`SM/ss_dsi_mdnie_lite_common.c:168-…`). It is sent only when `blank_state == UNBLANK` (`:178-184`). The default is UI_APP / AUTO_MODE / outdoor off (`:1378-1380`), giving `DSI0_UI_AUTO_MDNIE` in **HS** (`:1411`): `15 B0 A8`, `39 B9 …(56)`, `15 B0 42`, `39 B9 01 …(103)` with `mdnie_en = 1` (`SM/ss_dsi_mdnie_ANA38401_AMS968HH01.h:48-56,3267,3328-3330,9973-9978`; sizes at `ANA38401.c:963-967`).
5. `wait_disp_on = true` (`:1701`). For this panel it is a no-op (§1.1).
6. ESD: `esd_irq_enable(true)` and `is_enabled_esd_recovery = true` (`:1703-1707`). From here on, a falling edge on GPIO121 schedules `check_status`. `mdss_samsung_esd_check_status` returns 0, which means "dead", so a full blank/unblank follows (`:2010-2026,2117-2162`).

Then `35 00` tear-on in LP (§2.3 step 4d), then the first frame.

### 2.7 Where are display-on and the first frame? [P]

- `29h` is sent **inside** the LP on-command list, 215 ms after `UPLL_F`, **before** any frame.
- Between `29h` and the first frame are: the HS brightness block, HS mDNIe, LP `35h`, `PANEL_ON`, tear-check enable, and then the kickoff at the next TE.
- Samsung's frame-deferred display-on (`display_on_tx_cmds`, which would be `05 … 32 … 29 00`, i.e. 29h + 50 ms, `dtsi:297`) is **commented out** for this panel. The `FRAME_UPDATE` hook therefore sends nothing.
- `panic_on_pptimeout = true` is set for this panel: "Enable panic on first pingpong timeout" (`ANA38401.c:1012-1013`; used at `mdss_mdp_intf_cmd.c:2012-2018`). On stock, **a missing TE after power-on is treated as fatal**. The DDI is expected to produce TE from the first kickoff.

### 2.8 LP/HS summary [P]

| Traffic | Mode | Link | Where |
|---|---|---|---|
| On-command list | LP | DSI0 | `dtsi:187`; `mdss_dsi_panel.c:223-225` |
| `manufacture_read_pre` and read positions (`B0 nn`) | HS (Samsung default) | DSI0 | `mdss_dsi_panel.c:1397-1399` |
| Read requests | Default DMA mode = LP | DSI0 | `mdss_dsi_panel.c:3204-3232`; `mdss_dsi_host.c:1079` |
| Brightness/ACL/ELVSS/CAPS/gamma (every change) | **HS** | DSI0 | `ss_dsi_panel_common.c:734-736` |
| mDNIe | **HS** | DSI0 | `ss_dsi_mdnie_lite_common.c:1411` |
| `35h` tear-on / `34h` tear-off | LP (no flag) | DSI0 | `SX/mdss_dsi_cmd.c:679-686,697-700` |
| Off command `28h` | **HS** | DSI0 | `dtsi:96-98,188` |
| Pixel data | HS | both | MDP |

---

## 3. (B) Dual-link and compression handling

**[P]**

- **Commands go to DSI0 only.** This is enforced by `qcom,dcs-cmd-by-left` (`dtsi:101`; parsed at `mdss_dsi_panel.c:2327-2328`) in four places:
  - `mdss_dsi_panel_cmds_send` returns for DSI1 (`mdss_dsi_panel.c:199-202`).
  - `mdss_dsi_panel_on` and `off` skip DSI1 (`:960-963,1167-1170`).
  - Samsung reads are left-only (`:3211-3214`).
  - Tear on/off are left-only (`SX/mdss_dsi_cmd.c:694-695`).
- **There is no broadcast and no sync-wait.** `qcom,cmd-sync-wait-broadcast` and `-trigger` are commented out (`dtsi:102-103`), so the `mdss_dsi_cmds_tx` broadcast path (`mdss_dsi_host.c:1813-1829`) is not taken. Samsung's broadcast-flagged commands (ESD recovery 1/2, `ss_dsi_panel_common.c:1232-1239`) are not defined for this panel. Mainline is the same: no `qcom,sync-dual-dsi` in our DTS, so `msm_dsi_manager_cmd_xfer` does not sync (`ML/dsi_manager.c:501-550`).
- **The `split_dsi` reset choreography is specific to dual links** (`dtsi:250`; `mdss_dsi.c:1665-1677,1703-1718`):
  - The LP-11 regulators (reset release and TCON_RDY wait) are enabled only from the **right** controller's `mdss_dsi_on`, i.e. after **both** PHYs and controllers are initialised.
  - DSI1's lanes are forced to TX-stop during the reset. DSI0's lanes are idle at LP-11.
  - The same call then forces the HS clock on **both** links ("Force HS for DSI 0 (left master ctrl)" … "Force HS for DSI 1").
- **Compression and dual-DSI registers:**
  - Written once per power-on, LP, in on-command order **51 (dual) → D9 (compression)**, before `UPLL_F`, the 215 ms wait and `29h` (`dtsi:36-40`).
  - On the first power-on after boot only, they are also written earlier in HS, in order **D9 → 51**, inside `manufacture_read_pre` before the ID reads (`dtsi:281-285`).
  - Samsung's comment: "Some panel needs to update register at init time to read ID & MTP. Such as, dual-dsi-control or sleep-out so on." (`ss_dsi_panel_common.c:1484-1487`).
  - That pre-write is **not** repeated on later wakes, and stock wakes work. **So for stock, the on-command list alone, delivered under stock link conditions, is enough for the DDI to come up dual-link.**
- No C code anywhere touches `0x51`, `0xD9` or `0xD0` (grep of `ss_dsi_panel_ANA38401_AMS968HH01.c` and the smart-dimming files). There is no toggle, no frame-synchronised re-write, and no "first frame" flag.
- **Host-level differences that touch both links** (stock vs mainline):

  | Item | Stock | Mainline |
  |---|---|---|
  | NULL-packet insertion | Programmed when `qcom,null-insertion-enabled` (`live-node:233,258`): `0x2b4 = (vc<<1)\|1`, word count 0 (`mdss_dsi_host.c:1400-1407`) | Never programmed |
  | Burst mode (`CMD_MODE_MDP_CTRL2` bit 16) | Enabled (`mdss_dsi_host.c:1271-1293,1409`) | Enabled (`ML/dsi_host.c:819-829`) |
  | PHY timings | Explicit (`dtsi:20-27`; `t-clk-pre` 0x30 / `t-clk-post` 0x0D, `dtsi:179-180`) | Computed by mainline |

  **[I]** The NULL-insertion and PHY-timing differences could affect how the DDI aligns the two links. Unproven.

---

## 4. (C) Off, sleep and resume

### 4.1 Stock screen-off sequence [P] (`FB_BLANK_POWERDOWN`)

| # | Step | Citation |
|---|---|---|
| 1 | `mdss_fb`: stop the display thread; **`set_backlight(0)`** → `mdss_dsi_panel_bl_ctrl(0)` → `mdss_samsung_brightness_dcs(0)`. This sends the full brightness block for bl 0 = 2 cd in **HS** (`90 01 00 7F`, ACL 15%, `B2 19`, `B2 81`, 2-cd gamma + key). The user level is saved in `unset_bl_level` | `SX/mdss_fb.c:1890-1898`; `mdss_dsi_panel.c:854-886,246-273`; `dtsi:352,965,622` |
| 2 | `mdss_mdp_cmd_stop(OFF)`: **wait for the last frame's ping-pong**, stop the interface, **disable tear-check** | `mdss_mdp_intf_cmd.c:3078-3089,3154-3168,2964-2966` |
| 3 | `BLANK` (the off command is HS, so it runs here) → `mdss_dsi_blank`: `op_mode_config(CMD)`, **`05 34 00` tear-off (LP)**, then `mdss_dsi_panel_off` | `mdss_dsi.c:3040-3045,1994-2032` |
| 3a | `blank_state = BLANK`; `off_pre` (ESD IRQ disabled, `is_enabled_esd_recovery = false`) | `mdss_dsi_panel.c:1173-1174`; `ss_dsi_panel_common.c:1714-1749` |
| 3b | **`05 28 00` display off, HS, wait 0x64 = 100 ms** | `dtsi:96-98,188`; `mdss_dsi_panel.c:1178-1179` |
| 3c | `off_post`: mDNIe trans-dimming flag, `gradual_pre_acl_on = UNSTABLE`. The panel hook is empty | `ss_dsi_panel_common.c:1751-1776`; `ANA38401.c:814-826` |
| 4 | `PANEL_OFF`, DSI0 then DSI1 → `mdss_dsi_off`: controller off, **PHY off**, clocks off, then `panel_power_ctrl(OFF)` | `mdss_dsi.c:3046-3054,1348-1422` |
| 4a | `mdss_dsi_panel_power_off`: LP-11 regulators off. The second (DSI1) call drives **GPIO143 low (reset asserted)**, **+5 ms** each call. Pinctrl goes to sleep (pull-downs). Then **ssreg-vdd off**: GPIO46 low on the second call, **+25 ms** | `mdss_dsi.c:283-340`; `SX/mdss_io_util.c:297-310`; `ss_regulator_common.c:232-247`; `LIVE:15063-15077` |

So **the panel is unpowered while the screen is off.** Stock never keeps the DDI in a "display off but powered" state for this panel.

### 4.2 LPM/ALPM [P]

There is none:

- No `samsung,panel-lpm-enable` in the dtsi or `live-node`. Low-power-mode control returns "LPM(ALPM/HLPM) is not supported" (`ss_dsi_panel_common.c:5294-5297,5457-5460`).
- `display_off_tx_cmds` (`28h` + 50 ms, `dtsi:298`) is referenced only from that LPM path (`:5480`).
- `qcom,ulps-enabled` and `suspend-ulps` are commented out (`dtsi:218-219`).

### 4.3 Resume path [P]

A wake is **identical to a cold power-on**:

1. `fb` unblank records the user level (§2.3 step 0).
2. The first commit runs `LINK_READY` (VDD on +10 ms, LP-11 forced, 75 ms, reset high, TCON_RDY, HS clock), then `UNBLANK`:
   - **`on_pre`**: no reads, since everything is already loaded except the no-op DDI-ID attempt.
   - **The full on-command list** (LP, with compression/dual, cold-start ACL/ELVSS, `UPLL_F` + 215 ms, `29h`).
   - **`on_post`**: the HS brightness block for the saved user level, HS mDNIe (`mdnie_lcd_on_notifiy` forces light-notification off), ESD re-armed.
   - **`35h`.**
3. The **first frame**.
4. After the commit, the **brightness block again** (`mdss_fb_update_backlight`).

State restored after wake:

- AID, ACL (15% unless the user disabled it via sysfs, `ss_dsi_panel_common.c:4803-4842`), ELVSS for the current temperature band, CAPS, smart-dimming gamma + update key.
- mDNIe mode.
- HBM state, if `bl_level ≥ 268`: `hbm_gamma` + `hbm_etc` (`:2384-2446`; `ANA38401.c:166-308`).
- Color-weakness and cover control when they are used (`:1666-1667,1697-1699`).

At first boot, `cont_splash` is decided at run time from the bootloader's interface state (`mdss_dsi.c:4754-4759`). Then `mdss_mdp_cmd_reconfigure_splash_done` sends `BLANK` and then `PANEL_OFF` ("Turning off panel to initialize panel init-seq at kick-off", `mdss_mdp_intf_cmd.c:1884-1914`). **So even the first kernel frame comes from a full power-cycle and cold start.**

### 4.4 What our wake paths lack

**DPMS path** (`disable` → `unprepare` → `prepare` → `enable`) compared with stock:

| Stock wake step | Ours (`OURS` lines) | Gap |
|---|---|---|
| VDD cut for the whole sleep (+25 ms) | `keep_vdd = 1` keeps VDD on and only holds reset (`376-385`); with `keep_vdd = 0`, 10 ms off | Different power state of the DDI going into reset [P] |
| LP-11 (clock lane too) through 75 ms, reset release and TCON_RDY; HS clock forced afterwards | Host pre_enable has already forced the HS clock (`ML/dsi_host.c:878-886`), then `msleep(75)`, reset, TCON_RDY (`405-413`) | HS clock present at reset release [P]; effect unknown [I] |
| On-command list → `29h` directly after the 215 ms | `29h` moved to `enable()` (`525-526`), after the gamma write and the bridge enable | Not contiguous [P] |
| HS drive block (AID/ACL/ELVSS/CAPS/gamma + key) right after `29h`, before the first frame | ACL/ELVSS written in **LP before `29h`** inside init (`360`); in HS only in fixup step 3, about 5 s + 1.8 s later (`470-476`, `55-65`) | Order and mode [P] |
| HS mDNIe | none | Colour only [P] |
| `35h` right after the drive block | `35h` after `29h` + 50 ms (`527-528`) | Minor |
| First frame within one TE | Whenever DRM commits; the docs record 0.9-3.5 s at boot | [P] for the code; the timing is empirical |
| Brightness block re-sent after the first frame | none | [P] |
| No compression toggle | Delayed fixup toggles D9 00 → 08 and 51 06 (`447-511`) | We do extra work stock doesn't need [P] |
| ESD IRQ (GPIO121) armed; full re-init on a falling edge | Not monitored. GPIO121 is even reserved in our DTS (`gpio-reserved-ranges <53 70>` covers 53-122) | [P] |
| Off: brightness → 2 cd, wait for the last frame, `34h`, `28h` **HS** + 100 ms, reset +5 ms, VDD +25 ms | `28h` **LP** + 100 ms (`557-558`), reset +5 ms, VDD kept, no `34h` | [P] |

**Backlight path** (`28h`/`29h`, `OURS:692-721`):

- Stock has no equivalent (§4.2) [P].
- After `28h` our pipeline keeps sending frames into the DDI. On `29h` the DDI immediately shows whatever it last received, often a bright frame. Patch 0027 then sends ACL/ELVSS, after `29h`.
- In stock, `29h` always happens right after reset, when no pixel data has been sent yet. **[I]** The DDI's frame memory is most likely black at that point, and ACL/ELVSS (and gamma) are applied **before the first real pixel data**.

---

## 5. (D) Panel-specific code in `ss_dsi_panel_ANA38401_AMS968HH01.c` [P]

| Function | Lines | Notes |
|---|---|---|
| `mdss_panel_on_pre` | 36-50 | Only `mdss_panel_attach_set(true)` |
| `mdss_panel_on_post`, `samsung_panel_off_post` | 52-62, 814-826 | Empty |
| `mdss_panel_revision` | 64-91 | PBA_ID → detach. **Forces `aid_subdivision_enable = true`**, i.e. a 256-entry AID table indexed by raw `bl_level` (`:617-621`; `dtsi:350-608`). Revision is always A |
| `mdss_manufacture_date_read` | 93-132 | Reads 2 bytes (`D8` at 0x7F) but decodes `date[0..3]`, so `date[2..3]` are uninitialised stack bytes. Cosmetic |
| `mdss_ddi_id_read` | 134-164 | No rx command in the DT. Runs every power-on, no I/O |
| `mdss_hbm_gamma` / `mdss_hbm_etc` | 166-308 | HBM ELVSS dim offset per auto-brightness level (6..13) and temperature band. HBM ACL: 8% (`0x11`) with 60% start (`0x99`), or off for the gallery (`gradual_acl_val == 0`) |
| `mdss_hbm_read` | 310-366 | HBM MTP read with in-place offset mutation. `D8@0x81` → HBM ELVSS, `D2@0x70` → HBM-off ELVSS |
| `mdss_cell_id_read` | 382-415 | No command; returns true "so that system does not keep checking repeatedly" |
| mDNIe coordinate tuning | 417-535 | x/y from `D8@0x7B` select Tune_1..9. `mdnie_x/y` are then zeroed for sysfs |
| `mdss_samart_dimming_init` | 537-602 | MTP read; HBM table += MTP ("for Gamma Offset Index 4"); `temperature = 20` |
| `mdss_aid` | 605-642 | Subdivision: `cmds[bl_level]` |
| `mdss_acl_on` / `off` | 644-672 | ACL on overrides `cmds[5].payload[1] = gradual_acl_val` (0x12 = 15%) |
| `mdss_pre_elvss` / `mdss_elvss` | 674-737 | `B0 67`, then the smart-ACL or normal table by `acl_status`/`siop`, three temperature bands |
| `mdss_pre_caps_setting` / `mdss_caps_setting` | 739-784 | `B0 6D`, then `B2 81` (≤ 39 cd) or `B2 85` |
| `mdss_gamma` | 786-812 | Smart-dimming gamma into `gamma_tx_cmds` (83 + update key) |
| `dsi_update_mdnie_data` | 828-957 | Tables only |
| `mdss_panel_init` | 959-1018 | mDNIe tune sizes 2/56/2/103; `auto_brightness_level = 12`; **`panic_on_pptimeout = true`**; **`acl_status = 1`, `gradual_acl_val = 0x12` ("ACL default 15% ON")** |

In the dtsi:

- The comments with "??" are on Gamma Offset `B0 BC / B2 04` and on "display on then 50ms delay??".
- The "ELVSS Temp Compensation" block is an empty placeholder (`dtsi:88`).
- The `hbm2` comment says offset 0x7B, but the data says 0x81 (`dtsi:271`).
- `hbm_off_tx_cmds` uses `last = 0` on both packets (`dtsi:339-342`).

There are **no** dual-link, compression or first-frame workarounds, and no delays other than those in the DT.

---

## 6. (E) Gap table and symptom mapping

| # | Samsung step [P] | Ours (`OURS`) | Same? | Symptoms |
|---|---|---|---|---|
| 1 | VDD GPIO46 on, +10 ms; off +25 ms; cut on every sleep | On at prepare +10 ms (`393-399`); kept on during sleep (`376-385`) | Partly | 3 |
| 2 | All lanes forced LP-11 (clock lane not HS) ≥ 1 ms + 75 ms, then reset GPIO143 high, then TCON_RDY ≤ 1 s, then 1 ms, then HS clock on both links | HS clock already forced by `msm_dsi_host_power_on` before `prepare` (`prepare_prev_first`, `805`); 75 ms; reset; TCON_RDY ≤ 1 s; 1-2 ms | **No** | 1, 3 |
| 3 | First boot only: HS `manufacture_read_pre` (D9 → 51), ID/date/HBM/mDNIe/MTP reads, all **before** the on-commands | ID ×2 + MTP ×≥2 HS reads **after** the on-commands, before `29h` (`420-432`); skipped on later prepares | **No** | 1 (I), 3 (I) |
| 4 | On-command list exactly as in §2.4, LP, DSI0 | Same packets, same types, LP (`325-368`), **except** `normal_conditions()` replaces stock #17-#20 and adds `B0 49 7F`, `B0 67 1B`, `B0 35 01` before UPLL (`360`); `29h` not in the list | Partly | 2 |
| 5 | `29h` immediately after the 215 ms `UPLL_F` wait | `29h` in `enable()` (LP) after the gamma write (LP) and the bridge enable (`525`) | **No** | 1, 3 |
| 6 | **HS** drive block right after `29h` (AID, ACL 15%, ELVSS 1B, CAPS 85, MTP gamma + key) | ACL/ELVSS in **LP before `29h`**; MTP gamma in LP after init; HS only in fixup step 3 (≥ 6.8 s) or on backlight wake | **No** | **2** |
| 7 | HS mDNIe UI_AUTO | None | No | Colour only |
| 8 | `35h` (LP) before the first frame | `35h` after `29h` + 50 ms | ≈ | - |
| 9 | First frame within about one TE of `35h` | Depends on the DRM client (seconds at boot); fixup after 5 s | **No** | 1, 3 |
| 10 | Brightness block re-sent after the first commit | None | No | 2 (I) |
| 11 | No compression or dual-link re-write | D9 00 → 08 + 51 06 + gamma, then normal conditions | Extra | - |
| 12 | ESD GPIO121 falling → full re-init | Not monitored (GPIO121 reserved in DTS) | **No** | 3 (I) |
| 13 | Brightness control through the full block on every change | Fixed 360 nit; backlight device is on/off only | No | - |
| 14 | Off: bl → 2 cd (HS), wait for the last frame, `34h`, `28h` HS + 100 ms, reset +5 ms, VDD +25 ms | `28h` LP + 100 ms, reset +5 ms, VDD kept | Partly | 3 |
| 15 | No 28h/29h screen-off path | Backlight `bl_power` 28h/29h + normal conditions (HS) | Not in stock | 3 |
| 16 | NULL insertion on (0x2b4), explicit PHY timings | Mainline: none, and computed timings | Different host | 1 (I) |
| 17 | DCS only on DSI0; no broadcast | Same (`dsi[0]` only; no `qcom,sync-dual-dsi`) | Yes | - |
| 18 | B1/B2 as 0x39 long writes, B0 as 0x15 | Same (`177-206`) | Yes | - |
| 19 | 893.2 Mbps continuous clock | `stock_clock` mode (`130-143`) | Yes | - |

### Symptom 1: garbled or stretched frames for about 5 s until the compression toggle

**Proven by the source:**

- Stock sets 51 then D9 once, in LP, in the on-command list. It never touches them again, on any wake.
- Stock wakes, which are cold starts without the first-boot `manufacture_read_pre`, show no garbling. So the on-command list is enough when the stock conditions hold.
- Those conditions differ from ours in three ways:
  - Row 2: HS clock already running at reset release and during the TCON_RDY wait.
  - Rows 3, 5 and 9: our HS reads between `UPLL_F` and `29h`; `29h` not directly after the UPLL wait; no HS drive traffic and no first frame promptly after `29h`.
  - Row 16: host link configuration.
- Samsung's `panic_on_pptimeout` shows that stock never expects TE to stop.

**Inference, ranked:**

1. **Row 2.** The ANA38401 probably samples or initialises its dual-link and compression input path at reset exit or TCON-ready while its D-PHY receivers see LP-11 on all lanes. With HS already on both clock lanes it ends up single-link/compressed, until a D9 change re-runs that configuration.
2. **Rows 3, 5 and 9.** The configuration may be applied by the `29h` → first-frame transition, which stock makes within milliseconds and we make with HS reads and LP writes in between, then a gap of seconds.
3. **Row 16.** NULL insertion or PHY timing affecting link alignment.

**Cheapest discriminating tests:**

- **(a)** Hold the DSI hosts' clock lane in LP-11 until after TCON_RDY. This needs a small msm host change: start with `MIPI_DSI_CLOCK_NON_CONTINUOUS` behaviour, then set `CLKLN_HS_FORCE_REQUEST` from the panel after TCON_RDY. Run with `fixup=0`.
- **(b)** Move the MTP and ID reads to before the on-commands (stock order) or drop them, then send `29h` straight after the 215 ms wait and the HS drive block right after it, and push a frame immediately (`fixup=0`).

### Symptom 2: washed-out colours and rolling lines on bright content

**Proven by the source:**

- The on-command list leaves ACL off (`B2 10`, 16-frame average) and ELVSS `0x0F`, the low-temperature 360 cd value.
- Stock overrides both in **HS**, **after `29h` and before the first pixel data**, with ACL 15% and smart-ACL ELVSS `0x1B` (default `acl_status = 1`, temperature 20 °C). It re-sends them after the first frame and on every brightness change.
- Stock never shows normal content with the cold-start values. Even "ACL off" for the gallery uses ELVSS `0x19`, not `0x0F` (`dtsi:725`).
- The on-command list itself writes these registers in LP, so the source does **not** show the DDI ignoring LP register writes.

**Inference:**

- With ACL off, high-APL content draws far more panel current. The -1.47 A → +0.16 A net battery change seen when the stock values were applied points that way.
- The OLED supply probably sags, which gives washed colours and rolling lines. A mostly-black console draws little current, so it is unaffected.
- Our LP writes failing is better explained by **order** than by LP mode. They were sent before `29h` and before the D9/51 re-latch, and our own tests (0026/0027) show both events discard or override them.
- Patch 0025 also showed the helper was forcing LP even when HS was requested.
- **Recommended:** reproduce the stock order. Send the full brightness block (AID, ACL, ELVSS, CAPS, MTP gamma, update key) in HS right after every `29h`, and again after the first frame and after any compression change.

### Symptom 3: wake is dark, or a bright frame flashes once and goes black

**Proven by the source:**

- Stock has no 28h/29h sleep for this panel.
- Every stock wake is: VDD power-cycle → LP-11 reset → on-command list (with `29h`) → HS drive block + mDNIe → `35h` → first frame within one TE → drive block again.
- An ESD falling edge on GPIO121 forces a full re-init.
- Stock never shows real pixel data before ACL/ELVSS are in place, and it lowers brightness to 2 cd before every screen-off.

**Inference:**

- **DPMS path.** Our re-init differs from stock in rows 1, 2, 5, 6, 9 and 14. Specifically:
  - Nothing in HS reaches the DDI after `29h` until frames flow.
  - The MTP reads, which on first boot are the only HS traffic before `29h`, are skipped on re-prepare.
  - Our only recovery is the 5-s fixup, which needs frames. 0015 already showed that fixup writes without frames make the DDI stop producing TE.
  - Any of these can leave the DDI dark. Rows 2, 5 and 6 are the stock-faithful candidates to try first.
- **Backlight path.** "One bright flash, then black" fits a protection trip:
  - After `29h` the DDI shows a stale bright frame at once, before the drive conditions written after `29h` take effect. They are gated by the update key and probably by the next frame.
  - The resulting current step could trip the OLED supply's short or overcurrent protection.
  - The DDI's error output is the line stock watches as ESD (GPIO121, falling) and answers with a full re-init.
  - **Check:** unreserve GPIO121, watch its level and edges, and read DCS `0A`, `0E`, `0F` and TCON_RDY after a failed wake.
  - **Mitigation in stock order:** a black frame (or minimum AID) before `29h`, then `29h`, then the HS drive block, then content after one or two frames. Alternatively, drop the 28h/29h path and do stock-style full power cycles once the cold start works without the fixup.

---

## 7. Suggested next experiments (in order; not done here)

1. **Stock-faithful prepare/enable with `fixup=0`:**
   - VDD on (+10 ms).
   - Clock lane kept LP-11 until after TCON_RDY (msm host tweak), then force HS and wait 1 ms.
   - On-command list in LP, exactly as in §2.4 (the cold-start values may stay), with `29h` immediately after the 215 ms.
   - HS drive block for 360 nit (§2.6), then HS mDNIe (optional), then `35h`.
   - Kick a frame at once (put this in `enable()` right before the first flush).
   - Re-send the HS drive block after the first frame.
   - MTP read: before the on-command list (stock `on_pre` order), or cached once.
2. If (1) still garbles, A/B rows 3 and 16: no reads at all, then the NULL-insertion register.
3. **Off:**
   - 2-cd drive block (optional).
   - Stop frames.
   - `34h`.
   - `28h` **HS** + 100 ms.
   - Reset low + 5 ms.
   - VDD off + 25 ms (`keep_vdd=0`).
   - Wake = full step 1.
4. **ESD/protection diagnosis for symptom 3:** unreserve GPIO121, log its edges, and read `0A`/`0E`/`0F` after the flash-to-black.

---

## Appendix A: other decoded command lists [P]

| List | dtsi | Packets | Mode / wait |
|---|---|---|---|
| Off command | 96-98 | `05 28 00` | HS (`dtsi:188`), **100 ms** |
| `display_off_tx` (LPM only, unused) | 298 | `05 28 00` | HS default, 50 ms |
| `display_on_tx` (commented out) | 297 | `05 29 00` | would be 50 ms |
| Tear on / off | `SX/mdss_dsi_cmd.c:679-686` | `15 35 00` / `05 34 00` | LP |
| `packet_size_tx` | 261-263 | `37 21 00` (max return 33) | HS default |
| `reg_read_pos_tx` | 265-267 | `15 B0 <pos>` (pos patched per chunk, ≤ 10 bytes per read, `ss_dsi_panel_common.c:1019,1035-1045`) | HS default |
| `manufacture_read_pre_tx` | 277-289 | `B0 34 / B2 64 00`, `B0 D9 / B1 08`, `B0 51 / B1 06`, `B0 75 / B2 28` | HS default, first power-on only |
| ID reads | 291-293 | `06 DA`, `06 DB`, `06 DC` (1 byte each) | Read default mode |
| ACL on | 700-707 | `B0 4D / B2 05`, `B0 49 / B2 7F`, `B0 36 / B2 12` (cmds[5] ← `gradual_acl_val`) | HS (brightness) |
| ACL off | 709-716 | `B0 4D / B2 04`, `B0 49 / B2 7F`, `B0 36 / B2 10` | HS |
| ELVSS normal / low-temp / low-temp2 (ACL off) at 360 cd | 724-847 | `B2 19` / `B2 0F` / `B2 0A` (after `B0 67`) | HS |
| ELVSS smart-ACL normal / low-temp / low-temp2 at 360 cd | 926-1048 | `B2 1B` / `B2 11` / `B2 0A` | HS |
| CAPS | 617-693 | `B0 6D`, then `B2 81` (2-39 cd) or `B2 85` (41-360 cd) | HS |
| AID | 350-608 | 256 entries `90 0x 00 yy`; bl 0 = `90 01 00 7F` … bl 255 = `90 00 00 0E` | HS |
| HBM etc. | 321-337 | AID `0E`; `B0 67 / B2 17` (patched dim offset); `B0 70 / B2 00` (← `D8@0x81`); ACL `B2 05` / `99` / `11` (patched); CAPS 85; key | HS |
| HBM off | 339-342 | `B0 70 / B2 <D2@0x70>`, `last = 0` | HS |
| Candela map | 1125-1192 | bl 254-255 → idx 64 → 360 cd; bl 0 → 2 cd | - |

## Appendix B: mainline references used

| Reference | What it shows |
|---|---|
| `ML/dsi_host.c:878-886` | `dsi_ctrl_enable()` sets `DSI_LANE_CTRL_CLKLN_HS_FORCE_REQUEST` unless `MIPI_DSI_CLOCK_NON_CONTINUOUS` |
| `ML/dsi_host.c:2432-2476` | Called from `msm_dsi_host_power_on()` |
| `ML/dsi_manager.c:230-263, 284-326` | `dsi_mgr_bridge_pre_enable` powers on **both** bonded hosts and then enables them, before the panel's `prepare` (`prepare_prev_first`) |
| `ML/dsi_manager.c:501-550` | Command transfer syncs to both links only with `qcom,sync-dual-dsi` (absent) |
| `ML/dsi_host.c:819-829` | Burst mode set; no NULL-insertion programming |
| `ML/registers/display/dsi.xml` (`LANE_CTRL`, 0xa8 + 6G shift 4 = downstream 0xAC) | Bit 28 `CLKLN_HS_FORCE_REQUEST`. Downstream bits 16-20 are per-lane force-TX-stop (`SM/mdss_dsi_host.c:640-647`) |
