# AMS968HH01 / ANA38401 command transport: downstream MDSS compared with mainline msm DSI/DPU

> **Corrections from on-device checks (2026-10-11,
> [`../panel-experiments-20261011.json`](../panel-experiments-20261011.json)):**
> package 25 with `0026`/`0027` booted recovery fully black, so the statement below that separating the
> normal conditions into a later step "fixed it" is wrong: it is not a verified fix. The B1/B2 readback
> commands proposed in section F (E2, E3) do not work; `B1`/`B2` are write banks and replies repeat the
> previous read. See the read method in [../panel-ams968hh01.md](../panel-ams968hh01.md), section 4.
> LP DCS reads do answer on a settled, static panel.

> **File references.** `samsung-mdss/`, `samsung-extra/`, `fetched-mdss-fb/` and `re/dl/` hold files
> from Samsung's kernel, [awesometic/android_kernel_samsung_msm8996 @ f48aec90](https://github.com/awesometic/android_kernel_samsung_msm8996/tree/f48aec90fcebf4615fdee4a8abac7339930db856)
> (`drivers/video/msm/mdss/` and `drivers/video/msm/mdss/samsung/ANA38401_AMS968HH01/`).
> `stock-live-panel-node.dts` is lines 3276-3700 of the private stock DT backup
> (`private/backups/20261010T094140Z/live.dts`). `OURS` / `ours-20261011.c` is our driver as on the tablet
> on 2026-10-11 (patches up to `0027`), saved next to this report. Analysis scripts are kept outside
> the repository except [`tools/panel/smartdim.py`](../../tools/panel/smartdim.py).
> Summary and conclusions: [../panel-ams968hh01.md](../panel-ams968hh01.md).

Source analysis only. No hardware was touched. Every claim below is labelled:

- **[P] proven from source**: read in the cited code.
- **[H] hardware observation**: from the repo's records (`docs/hardware-sm-t825.md`, patch messages). I did not reproduce these.
- **[I] inference**: a hypothesis. Each one has a decisive experiment in section F.

## Path abbreviations

| Tag | Path |
|---|---|
| `DS/` | `samsung-mdss/` (downstream, commit f48aec90) |
| `DL/` | `re/dl/`: extra files fetched from the same commit (`mdss_dsi_cmd.c`, `mdss_dsi.h`, `mdss_dsi_cmd.h`, `mdss_panel.h`, `mdss_mdp.h`, `msm_mdss_io_8974.c`, `mdss-dsi.txt`, `mdss-dsi-panel.txt`) |
| `CTL` | `work/mdss_mdp_ctl-downstream.c` |
| `ML/` | `work/linux-v6.19.5-msm8996/` |
| `P` | `ML/drivers/gpu/drm/panel/panel-samsung-ams968hh01.c` (work tree with patches 0004–0027 applied) |
| `DTS` | `kernel/msm8996-samsung-gts3llte-display.dts` |
| `HW` | `docs/hardware-sm-t825.md` |

**Register offsets.** Downstream `MIPI_OUTP(ctrl_base + X)` uses absolute offsets from the controller base (DSI0 `0x00994000`, DSI1 `0x00996000`). Mainline `REG_DSI_*` values are 4 lower because the 6G `io_offset` is added (`ML/drivers/gpu/drm/msm/dsi/dsi_host.c:76,1982`). Mapping:

| Register | Downstream offset | Mainline `REG_DSI_*` |
|---|---|---|
| CTRL | 0x004 | 0x000 |
| CMD_DMA_CTRL | 0x03c | 0x038 |
| TRIG_CTRL | 0x084 | 0x080 |
| LANE_CTRL | 0x0ac | 0x0a8 |
| HS_TIMER_CTRL | 0x0bc | 0x0b8 |
| EOT_PACKET_CTRL | 0x0cc | 0x0c8 |
| CMD_MODE_MDP_CTRL2 | 0x1b8 | 0x1b4 |
| NULL_INSERTION | 0x2b4 | (unused in mainline) |

---

## Summary of the main findings

1. **[P] Downstream never broadcasts DCS for this panel.** The panel has `qcom,dcs-cmd-by-left`, and `qcom,cmd-sync-wait-broadcast` is commented out. Every command and every read goes unicast on DSI0 only. Mainline with our DT does the same: there is no `qcom,sync-dual-dsi`, and every panel transfer uses `ctx->dsi[0]`. Commands are therefore not mis-targeted.
2. **[P] In downstream, "LP" and "HS" differ only in `CMD_DMA_CTRL` bit 26** on the controller that sends. LP is the resting state, set in `mdss_dsi_op_mode_config`. A request flagged HS clears the bit for that request only. The clock lane is forced HS the whole time (`qcom,mdss-dsi-force-clock-lane-hs`). Mainline does exactly the same per message: same bit, same host, clock forced HS. I found no register-level difference in the LP transmit path, and the PHY lane strength and TA timings also match.
3. **[P] Downstream link state per command set:**
   - Only the qcom on-command list (and the DCS tear-on) is LP.
   - The off-command is HS.
   - All `samsung,*` command sets, the brightness packet and mDNIe are HS (Samsung's parser defaults to HS).
   - Downstream **read requests are LP** (`CMD_REQ_RX|CMD_REQ_COMMIT` with no HS flag), and the B0 offset write before each read is HS.

   So the comment in patch 0007 ("as downstream rx commands default to [HS]") is wrong for the read packet itself.
4. **[P] Every LP packet downstream is sent before the first frame.** The LP on-cmds and tear-on go out inside the first kickoff, at `MDSS_EVENT_UNBLANK`, before `CTL_START`. Everything sent at runtime is HS. Downstream has no software synchronisation with frames for burst-mode controllers like msm8996, and its TRIG_CTRL lacks `BLOCK_DMA_WITHIN_FRAME`. Mainline sets `BLOCK_DMA_WITHIN_FRAME`, has no software lock against DPU kickoff, and serialises transfers only per message.
5. **[P] Downstream makes each command set atomic; mainline does not make a B0+data pair atomic.**
   - Downstream holds `ctrl->cmd_mutex` across a whole command set, so a B0 offset write and its B1/B2 data write cannot be split by another DCS sender.
   - In our driver, the fixup worker, the backlight `bl_power` path, debugfs and enable/disable all send B0/data pairs. They are not mutually excluded, and they also save and restore `dsi->mode_flags` without a common lock.
6. **[H]+[P] The "LP writes don't take effect" conclusion is confounded.**
   - From patch 0005 until 0025, every B1/B2 data write in the fixup was forced to LP. That fixup is what restored dual-link and correct colours (HW:189-196).
   - The failures attributed to LP (package 23) and to HS (package 24) both had the normal-conditions writes in the same fixup step as the compression change. Only separating them (0026) fixed it (HW:524-531).
   - Ordering relative to the compression/dual-link re-latch explains all the data. LP vs HS does not need to be the cause. Section F lists A/B tests to settle it.
7. **[H] The 5 s of garbling is our timer** (`fixup_delay_ms = 5000`, patch 0015). The real gap is that the DDI does not latch dual-link from the init sequence as it does on stock. Nothing in the downstream MDP explains this: no DSC/FBC, no pingpong split, no partial update, and the split-display programming is equivalent.

   The biggest structural difference I found is the clock lanes during the DDI reset and TCON_RDY:
   - Stock keeps both links in LP11 through reset and TCON_RDY, then forces the HS clocks.
   - Mainline starts the continuous HS clock on both links in `pre_enable`, before panel `prepare` releases the reset.
8. **[P] TE handling matches stock, and autorefresh is off in both stacks.** The vsync source, tear-check, start_pos and rd_ptr are equivalent, and autorefresh is not enabled by default on either side. A command-mode panel refreshes static content from its own GRAM. The rolling lines on static bright content are therefore not caused by TE or autorefresh. The proven fix was the drive conditions (ACL/ELVSS).

---

## A. Downstream transmission

### A1. Controller set-up relevant to commands

- **Command-mode init**, `mdss_dsi_host_init` (`DS/mdss_dsi_host.c:324-471`):
  - DSI_CTRL = `BIT(8)` CLK_EN | `BIT(2)` CMD_MODE_EN | lanes, then `BIT(0)` ENABLE (`:394-409,461-462`).
  - TRIG_CTRL (0x084) = `te_sel<<31 | mdp_trigger<<4 | dma_trigger | stream<<8` (`:411-419`). This panel has `te-pin-select=1`, `mdp-trigger="none"`, `dma-trigger="trigger_sw"` (stock node `DS/stock-live-panel-node.dts:34,49,50`; values in `DL/mdss_dsi.h:209-213`). That gives TRIG_CTRL = `0x80000004`, without bit 12 `BLOCK_DMA_WITHIN_FRAME`.
  - EOT_PACKET_CTRL = RX_EOT_IGNORE | TX_EOT_APPEND (`:431-437`; node `:60-61`).
  - HS_TIMER_CTRL = `0x3fd08` (`:442`).
  - DMA FIFO watermark 0x50 = 0x30 (`:468`).
  - LANE_CTRL is reset to 0 at controller set-up (`:458-459`), so the clock is not forced HS at this point.
- **Mode configuration**, `mdss_dsi_op_mode_config` (`:1045-1088`):
  - `CMD_DMA_CTRL (0x03c) = BIT(28)` FROM_FRAME_BUFFER `| BIT(26)` **LOW_POWER** (`:1079`).
  - `BIT(31)` BROADCAST_EN is added only if `cmd_sync_wait_broadcast` (`:1080-1081`).
  - It is called per controller at `MDSS_EVENT_LINK_READY` (`DS/mdss_dsi.c:3014-3022`).
- **Burst mode**, `mdss_dsi_set_burst_mode` (`:1271-1295`), called from `mode_setup` (`:1409`). It sets CMD_MODE_MDP_CTRL2 bit 16 on DSI rev ≥ 1.3. msm8996 is rev 1.4 (`DL/mdss_dsi.h:57`), so `burst_mode_enabled = true`.
- **NULL packet insertion**: 0x2b4 = `vc<<1 | 1` (`:1400-1407`), enabled by `qcom,null-insertion-enabled` on both controllers (node `:233,258`; parsed `DS/mdss_dsi.c:4419-4420`). Mainline never programs it.
- **Clock lane and DDI reset**, `mdss_dsi_on` (`DS/mdss_dsi.c:1525-1746`):
  1. With `lp11_init` + `samsung,dsi-lp11-init`, LANE_CTRL is written to `0x1F<<16`, which forces stop state (LP11) on the clock and all data lanes (`:1651-1663`).
  2. For the right controller only, the LP11 regulators run (`:1665-1678`): `ssreg-panelrst` releases reset with a 75 ms pre-on sleep (node `:135-145`), then `ssreg-tconrdy` polls TCON_RDY for up to 1 s (`DS/ss_regulator_common.c:276-296`).
  3. LANE_CTRL is restored (`:1690-1693`).
  4. Only then is `BIT(28)` (CLKLN_HS_FORCE_REQUEST) forced on **both** controllers (`:1700-1729`).

  The DDI therefore leaves reset and raises TCON_RDY with both clock lanes in LP11, and the HS clocks start afterwards.
- **TCON clock kept on**: `samsung,tcon-clk-on-support` (node `:70`) stops the MDP from gating DSI clocks after each frame (`DS/mdss_mdp_intf_cmd.c:1225-1231`; `DS/mdss_dsi.c:1936-1941,1971`).
- **Clock-lane recovery is off**: the `cmd_clk_ln_recovery` start/stop helpers (`DS/mdss_dsi_host.c:657-762`) are disabled because `qcom,dsi-clk-ln-recovery` is absent (`DS/mdss_dsi.c:3840-3842`).

### A2. What "dsi_lp_mode" and "dsi_hs_mode" do

- **Parsing**, `mdss_dsi_parse_dcs_cmds` (`DS/mdss_dsi_panel.c:1273-1420`):
  - The Samsung build defaults `link_state = DSI_HS_MODE` (`:1397-1400`).
  - If a `-state` key is given: `"dsi_hs_mode"` gives HS, anything else gives LP (`:1405-1411`).
  - On-cmds use key `qcom,mdss-dsi-on-command-state` (`:2757-2758`); off-cmds use `qcom,mdss-dsi-off-command-state` (`:3106`).
  - Every `samsung,*` set goes through `parse_dt_data` with `link_key = NULL` (`DS/ss_dsi_panel_common.c:3220-3260`, call at `:3253-3255`), so it is always HS.
- **Send helper**, `mdss_dsi_panel_cmds_send` (`DS/mdss_dsi_panel.c:194-237`): adds `CMD_REQ_LP_MODE` or `CMD_REQ_HS_MODE` from `link_state` (`:224-227`) and queues the whole set as one `dcs_cmd_req`.
- **Commit**, `mdss_dsi_cmdlist_commit` (`DS/mdss_dsi_host.c:2673-2845`):
  - Only the HS flag has an effect: `mdss_dsi_set_tx_power_mode(0)` clears `0x03c` bit 26 before the transfer and `(1)` sets it again afterwards (`:2798-2807`; helper `:473-494`).
  - `CMD_REQ_LP_MODE` is a no-op because LP is the resting state.
  - It touches only the `ctrl` that sends, never the other controller.
- **Effect on the link:**
  - LP means the DMA packet goes out in escape mode (LPDT) on data lane 0 while the clock lane stays HS.
  - HS means the packet goes out as an HS burst.
  - DSI_CTRL is not changed for command-mode panels: `__mdss_dsi_cmd_mode_config` only adds CMD_MODE_EN when video mode is on (`:1776-1795`).
- **Reads**:
  - `mdss_samsung_panel_cmd_read` (`DS/mdss_dsi_panel.c:3204-3231`) and `mdss_dsi_panel_cmd_read` (`:145-171`) build a request with `CMD_REQ_RX|CMD_REQ_COMMIT` only. The read request, its BTA and the internal Max-Return-Packet-Size packet (`DS/mdss_dsi_host.c:1946-1984`, cached via `cur_max_pkt_size` `:1951,1980`) therefore go **LP**. The HS `link_state` of the `*_rx_cmds` sets is never consulted for reads.
  - The offset write before each read chunk (`PANEL_REG_READ_POS`, `samsung_nv_read`, `DS/ss_dsi_panel_common.c:1042`) goes through `mdss_samsung_send_cmd` and is **HS**.
  - Response: the RDBK registers are cleared (`:1997`), and the byte count is read from 0x1d4[31:16] (`:2263`).

### A3. Packetisation

- **One DMA per packet.** `mdss_dsi_cmds2buf_tx` (`DS/mdss_dsi_host.c:1706-1761`) accumulates descriptors and triggers one DMA when `dchdr->last` is set (`:1733`), then honours `dchdr->wait` (`:1752-1753`). Every on-command entry has `last=1`, so each packet is its own DMA.
- **DMA trigger**: `mdss_dsi_cmd_dma_tx` (`:2110-2241`) programs DMA address/length (0x048/0x04c), triggers 0x090 (`:2163-2169`), and waits for `CMD_DMA_DONE` (`:2179`).
- **Brightness packet, "single transmission"** (`DS/ss_dsi_panel_common.c:2636-2660`): long writes get `last=0` and short writes get `last=1`, which also forces `last=1` on the previous packet. In practice each `15 B0 xx` / `39 B2 yy` pair is still two DMAs; only consecutive long writes share one.
- **`hbm_off_tx`** has `last=0` on both packets, so B0 and B2 go out in a single DMA.

### A4. Synchronisation with command-mode frames

- **Locking: whole command sets are atomic.**
  - `mdss_dsi_cmdlist_put` holds `ctrl->cmd_mutex` from queueing through commit (`DL/mdss_dsi_cmd.c:753-806`), so a whole command set (28 on-cmds, the brightness packet, mDNIe) cannot interleave with another DCS sender.
  - The Samsung layer adds `vdd_lock` and `vdd_blank_unblank_lock` (`DS/ss_dsi_panel_common.c:1302-1362`) and `LP_STOP_MODE_LOCK` (`DS/mdss_dsi_panel.c:215`).
  - One exception: in `samsung_nv_read` the offset write (`:1042`) and the read (`:1044-1046`) are separate lock sections.
- **mdp_busy:** set by `mdss_dsi_cmd_mdp_start` (`DS/mdss_dsi_host.c:2489-2499`) at MDP kickoff (`:2822-2836`), cleared in the ISR on `CMD_MDP_DONE` (`:3307-3322`). `mdss_dsi_cmd_mdp_busy` (`:2547-2581`) waits for it.
- **DCS sends from threads (`from_mdp=0`):**
  - They wait for MDP idle only when burst mode is **disabled** (`:2706-2709`). msm8996 has burst enabled, so there is **no wait**.
  - The burst-mode replacement is `mdss_dsi_delay_cmd` (`:2630-2671`). It calls `MDP_INTF_CALLBACK_DSI_WAIT` (`:2791-2795`), which leads to `mdss_mdp_cmd_intf_callback` (`DS/mdss_mdp_intf_cmd.c:1037-1095`). That callback returns immediately unless pingpong split is in use (`:1059-1060`).
  - This panel is dual-LM dual-display, not pingpong split: there is no `qcom,split-mode = "pingpong-split"` (`DS/mdss_dsi_panel.c:1856-1879`; `CTL:4132-4190`). So there is no delay either.
  - With TRIG_CTRL bit 12 clear, the hardware is free to put a DMA between packets of a frame transfer.
- **MDP kickoff path**, `mdss_mdp_cmd_kickoff` (`DS/mdss_mdp_intf_cmd.c:2731-2875`):
  1. On the first kickoff it runs `mdss_mdp_cmd_panel_on` (`:2766-2773`): `LINK_READY`, `UNBLANK`, `PANEL_ON` (`:2168-2182`), then tear-check enable (`:2185`).
  2. `MDSS_EVENT_DSI_CMDLIST_KOFF` (`:2817-2818`) runs `mdss_dsi_cmdlist_commit(from_mdp=1)`. This waits for the previous frame's MDP-done, sends any queued non-COMMIT requests, and sets `mdp_busy`. It takes `cmd_mutex` only if a request is pending (`DS/mdss_dsi_host.c:2683-2697`).
  3. `CTL_START` (`:2684-2729`, `:2856`).
- **[P] Consequence.** The LP on-cmds and the LP tear-on (`DS/mdss_dsi.c:1915-1919`; `DL/mdss_dsi_cmd.c:688-704`) are sent during the first kickoff, before its `CTL_START`, while no frame has ever been on the wire. Samsung's `on_post` sends the brightness packet and mDNIe in HS in the same window (`DS/ss_dsi_panel_common.c:1674-1688`). The first frame follows immediately.
- **[P] Reads happen before frames:**
  - Panel ID, date, HBM, mDNIe coordinates and MTP are read in `mdss_samsung_panel_on_pre` (`DS/ss_dsi_panel_common.c:1427-1617`). It is called before the on-cmds (`DS/mdss_dsi_panel.c:1010-1019,1033`), in the same pre-frame window.
  - ESD uses the IRQ GPIO (`reg_read_irq`, node `:62-64`), so there are no runtime status reads.

### A5. Split-DSI broadcast and master selection

- **Generic downstream mechanism (not used by this panel):**
  - `qcom,cmd-sync-wait-broadcast` sets `cmd_sync_wait_broadcast`. The trigger controller is the one with `pdest == DISPLAY_2`, i.e. DSI1/right (`DS/mdss_dsi.c:4473-4479`).
  - With broadcast, both controllers get `BROADCAST_EN` (`DS/mdss_dsi_host.c:1080-1081`). The non-trigger controller's `cmds_tx` returns 0 ("let cmd_trigger do it", `:1824-1827`). The trigger controller programs the *other* controller's DMA address and length and triggers it first, then itself, and waits only on its own DMA-done (`:2142-2169`).
  - Reads under broadcast: the non-trigger controller skips (`:1912-1916`). The read DMA is triggered on both links, but `RDBK` is read only from the trigger controller (`:2026`).
  - `CMD_REQ_UNICAST` sets `do_unicast` (`:2588-2593`); the DMA is fired without waiting (`:2171-2176`).
- **This panel:**
  - `qcom,dcs-cmd-by-left` is present (`DS/dsi_panel_ANA38401_AMS968HH01_qxga_octa_cmd.dtsi:101`; node `:11`; parsed `DS/mdss_dsi_panel.c:2327`). `qcom,cmd-sync-wait-broadcast` is commented out (dtsi `:102-103`) and absent from the stock node.
  - Every send and read path returns early when `ctrl->ndx != DSI_CTRL_LEFT`: `DS/mdss_dsi_panel.c:152-155, 180, 199-202, 252-268, 960-963, 1015, 1054, 1108, 1167, 3211-3214`; tear on/off `DL/mdss_dsi_cmd.c:694,712`.
  - **All DCS traffic, reads included, is unicast on DSI0. DSI1 never transmits a command.**
  - Samsung's `CMD_REQ_BROADCAST` (ESD recovery only, `DS/ss_dsi_panel_common.c:1232-1238`; `DL/mdss_dsi_cmd.c:780-785,797-802`) is unused because the panel defines no `esd_recovery_*` sets.
- **Master:** the clock master is DSI0/left (`DL/mdss_dsi.h:395-398`). The PLL comes from DSI0, and the HS force for both links is applied when DSI1 comes up (`DS/mdss_dsi.c:1702-1717`). The MDP split-display master CTL drives both interfaces through the SW-trigger mux (`CTL:3841-3902`).

---

## B. Command sets: state and packet types

Decoded from both the dtsi and the tablet's stock node (scripts in `re/tools/`). The two are byte-identical for every set listed. "Effective" means what `mdss_dsi_cmdlist_commit` actually transmits.

| Set | dtsi line / node line | `-state` property | Effective mode | Packets (dtype × count) | When / notes |
|---|---|---|---|---|---|
| `qcom,mdss-dsi-on-command` | 29 / 9 | `dsi_lp_mode` (dtsi 187, node 53) | **LP** | 0x15 ×12 (all `B0 off`), 0x39 ×15 (B1/B2 data, `44 05 F6`, `83` 34 B gamma, `90 00 00 0E` AID), 0x05 ×1 (`29`). All `last=1`. 215 ms after `B0 D0/B1 1D` (UPLL) | `UNBLANK` inside first kickoff, before first frame (`DS/mdss_dsi.c:3024-3027` → `DS/mdss_dsi_panel.c:1033`) |
| `qcom,mdss-dsi-off-command` | 96 / 10 | `dsi_hs_mode` (188 / 54) | **HS** | 0x05 `28`, wait 100 ms | `MDSS_EVENT_BLANK` (`DS/mdss_dsi.c:3040-3045`) |
| DCS tear on (code) | — | — | **LP** (COMMIT only) | 0x15 `35 00` | `DS/mdss_dsi.c:1915-1919` after on-cmds |
| `samsung,display_off_tx` | 298 / 89 | none → Samsung default | HS | 0x05 `28`, wait 50 | LPM/ALPM paths |
| `samsung,manufacture_read_pre_tx` | 277 / 84 | none | **HS** | 0x15 ×4 + 0x39 ×4: `B0 34/B2 64 00`, `B0 D9/B1 08`, `B0 51/B1 06`, `B0 75/B2 28` (**D9 before 51**) | First boot only, in `on_pre` before on-cmds (`DS/ss_dsi_panel_common.c:1490-1497`) |
| `manufacture_id0/1/2_rx` | 291-293 / 85-87 | none | read request **LP** (offset write `15 B0 00` HS) | 0x06 `DA`/`DB`/`DC`, size 1 | `on_pre` |
| `smart_dimming_mtp_rx`, `hbm_rx`, `hbm2_rx`, `mdnie_read_rx`, `elvss_rx`, `manufacture_date_rx`, `mtp_read_sysfs_rx` | 269-274, 295 / 78-83, 88 | none | request **LP**; `15 B0 off` **HS** before each ≤10-byte chunk | 0x24 generic read 2-param `[Dx, len]` + (size, offset) trailer; e.g. `D8 08` @5A, the panel code walks 62/6A/72/7A (`DS/ss_dsi_panel_ANA38401_AMS968HH01.c:552-572`) | `on_pre`, before frames |
| `samsung,packet_size_tx` | 261 / 76 | none | (never sent) | 0x37 `21 00` | only selected in `cmds_select` (`:1142`), no sender |
| `samsung,reg_read_pos_tx` | 265 / 77 | none | HS | 0x15 `B0 xx` | before every read chunk |
| `samsung,gamma_tx` | 300 / 90 | none | HS | 0x39 `83` (34 B), 0x15 `B0 35`, 0x39 `B2 01` | brightness packet |
| `hbm_gamma_tx` / `hbm_etc_tx` | 312 / 321 ; 91 / 92 | none | HS | 0x39 `83`; 0x39 ×8 + 0x15 ×7 (AID, B0/B2 pairs at 67, 70, 4D, 49, 36, 6D, 35) | HBM |
| `hbm_off_tx` | 339 / 93 | none | HS, **one DMA** (`last=0` on both) | 0x15 `B0 70`, 0x39 `B2 xx` | HBM exit |
| `aid_subdivision_tx` | 350 / 94 | none | HS | 0x39 ×256 `90 xx xx xx` | brightness packet |
| `pre_caps_setting_tx` / `caps_setting_tx` | 617 / 621 ; 95 / 96 | none | HS | 0x15 `B0 6D`; 0x39 `B2 81/85` | brightness packet |
| `acl_on_tx` / `acl_off_tx` | 700 / 709 ; 98 / 99 | none | HS | 3 × (0x15 `B0 4D/49/36`, 0x39 `B2 …`) | brightness packet |
| `elvss_pre_tx` + `elvss`/`smart_acl_elvss` (+ lowtemp, lowtemp2) | 723-1008 / 100-107 | none | HS | 0x15 `B0 67`; 39 × 0x39 `B2 xx` tables | brightness packet |
| Brightness packet (assembled) | `DS/ss_dsi_panel_common.c:2448-2634` | `link_state = HS` (`:734-736`) | **HS** | AID, ACL, ELVSS, CAPS, gamma + key, as above | `on_post` right after on-cmds (`:1674-1681`), and on every level change |
| mDNIe tune | `DS/ss_dsi_mdnie_ANA38401_AMS968HH01.h:48-56, 9839-9842` | `link_state = HS` (`DS/ss_dsi_mdnie_lite_common.c:1410-1411`) | **HS** | 0x15 `B0 A8`, 0x39 `B9 …` (long), 0x15 `B0 42`, 0x39 `B9 …` | `on_post` (`:1684-1688`) |
| 2A/2B col/page | `DS/mdss_dsi_panel.c:597-640` | flag `CMD_REQ_HS_MODE` (`:626-631`) | HS | 0x39 ×2 (packed) | Only in `mdss_dsi_reset_write_ptr` after a ping-pong timeout (`DS/mdss_dsi.c:2872-2925`; `CTL:5380-5398`) |

**Mainline equivalents:**
- [P] Packet types match stock:
  - `mipi_dsi_dcs_write_seq_multi(ctx, 0xb0, x)` sends 0x15.
  - The register helper sends 0x39 (`P:177-201`).
  - `83` and `90` are 0x39, tear scanline is 0x39, display on/off is 0x05, tear on is 0x15.
  - The MTP read uses 0x24 `[D8, len]` (`P:213-238`), and the ID read uses 0x06.
- [P] Modes differ from stock in two places:
  - Our `disable()` sends display-off in **LP** (`P:548-561`, mode_flags has LPM). Stock off-cmds are HS.
  - Our diagnostic and MTP reads are HS (`P:155-156,221,251`). Stock read requests are LP.

---

## C. Mainline transport

### C1. Host programming

`dsi_ctrl_enable` (`ML/drivers/gpu/drm/msm/dsi/dsi_host.c:775-905`) is called from `msm_dsi_host_power_on` (`:2430-2490`) for **both** hosts in `dsi_mgr_bridge_pre_enable` → `dsi_mgr_power_on` (`dsi_manager.c:230-264, 284-335`). Because the panel sets `prepare_prev_first` (`P:805`), this happens **before** the panel's `prepare()`.

| Item | Mainline | Downstream |
|---|---|---|
| CMD_DMA_CTRL | FROM_FRAME_BUFFER \| LOW_POWER (`:833-835`); BROADCAST_EN never set anywhere in `drivers/gpu/drm/msm` | same, BIT28\|BIT26 |
| TRIG_CTRL | TE \| MDP_TRIGGER(NONE) \| DMA_TRIGGER(SW) \| STREAM \| **BLOCK_DMA_WITHIN_FRAME** (`:837-846`; msm8996 is 6G v1.4.1, `dsi_cfg.c:305`) = `0x80001004` | `0x80000004` |
| Burst | CMD_MODE_MDP_CTRL2.BURST_MODE (`:820-825`) | same |
| EOT | TX_EOT_APPEND only (`:857-861`) | also RX_EOT_IGNORE |
| HS_TIMER_CTRL / NULL insertion | not programmed | `0x3fd08` / enabled |
| LANE_CTRL | CLKLN_HS_FORCE_REQUEST set at power-on, unless `MIPI_DSI_CLOCK_NON_CONTINUOUS` (`:878-886`) → HS clock on both links before the DDI reset is released | LP11 through reset and TCON_RDY, then HS (A1) |

- [P] The 14nm PHY lane settings match the stock platform values: STRENGTH_CTRL_0/1 = `ff/06` (clock `ff/00`), CFG2/CFG3 = `10/0f` (clock `10/8f`), VREG `1d` (`ML/drivers/gpu/drm/msm/dsi/phy/dsi_phy_14nm.c:969-981`; node `:234-236`).
- [P] TA_GO/SURE/GET = 3/0/4 (`ML/drivers/gpu/drm/msm/dsi/phy/dsi_phy.c:247-249`), which equals the `03 04` bytes of `timings-phy-v2`.

### C2. How `MIPI_DSI_MSG_USE_LPM` is honoured (dual DSI)

- **Where the flag comes from:**
  - `mipi_dsi_device_transfer` ORs `USE_LPM` into the message when `dsi->mode_flags & MIPI_DSI_MODE_LPM` (`ML/drivers/gpu/drm/drm_mipi_dsi.c:448-460`).
  - Both panel devices are created with `MODE_LPM` (`P:812`).
  - The register helper and debugfs call `host->ops->transfer` directly and set the flag themselves (`P:184`; `P:605-608` for the `lp` prefix).
- **Per message, on one host:**
  - `dsi_host_transfer` (`:1708-1722`) takes that host's `cmd_mutex` and calls `msm_dsi_manager_cmd_xfer(id)` (`dsi_manager.c:495-539`).
  - `msm_dsi_host_xfer_prepare` (`:2103-2143`): when the message is not LPM, it clears LOW_POWER (`:2132-2133`), then ORs CMD_MODE_EN|ENABLE into DSI_CTRL (already set).
  - `xfer_restore` (`:2145-2159`) sets LOW_POWER back and rewrites the saved DSI_CTRL.
  - **[P]** Only that host's registers change. DSI1 is not touched.
- **Which host:**
  - The DT has `qcom,dual-dsi-mode` on both hosts and `qcom,master-dsi` on dsi0, but **no** `qcom,sync-dual-dsi` (`DTS:66-72,123-128`). So `IS_SYNC_NEEDED()` is false (`dsi_manager.c:47-66`).
  - Messages on `ctx->dsi[0]` therefore go to DSI0 only. Every panel send uses `ctx->dsi[0]`: `P:148,215,246,391,449,522,551,586,695`.
  - **[P]** This is the same unicast-left behaviour as stock. No broadcast is used.
- **Trap (not active today):**
  - If `qcom,sync-dual-dsi` is ever added, messages on the DSI0 device are **silently dropped**: the function returns `tx_len` without sending (`dsi_manager.c:512-513`), and only DSI1's device triggers both hosts (`:541-556`).
  - "Sync" there is a software sequence (DSI0 commit, then DSI1 commit, `:550-553`), not hardware `BROADCAST_EN`.
- **Packet format and DMA:**
  - `dsi_cmd_dma_add` (`:1284-1325`) builds one packet per message with last-packet, long and BTA flags.
  - `dsi_cmd_dma_tx` (`:1401-1430`) writes base/len/trigger (`msm_dsi_host_cmd_xfer_commit`, `:2306-2316`) and waits 200 ms for DMA-done.
- **Reads** (`msm_dsi_host_cmd_rx`, `:2168-2300`): set-max-return-size and then the read, each as its own DMA in the same LP/HS state, with RDBK cleared in between. The RDBK byte count is not checked.

### C3. Commands while DPU streams; locking against kickoff

- **[P] Software:** there is no synchronisation. The `xfer_prepare` comment says so: "TODO: make sure dsi_cmd_mdp is idle … we can set DSI_TRIG_CTRL.BLOCK_DMA_WITHIN_FRAME … S/W wait is not needed" (`:2110-2113`). The DPU command-mode kickoff (`ML/drivers/gpu/drm/msm/disp/dpu1/dpu_encoder_phys_cmd.c:575-608`, trigger `:700-704`) never takes `msm_host->cmd_mutex`.
- **[P] Hardware:** `BLOCK_DMA_WITHIN_FRAME` holds a DMA triggered during an MDP frame until that frame ends. It does not stop a new TE-triggered frame from starting between two DMAs.
- **[I] Reads:**
  - After the frame, DSI0 sends the request and performs BTA, then waits for the DDI's LP response.
  - DSI1 is unaffected and can start the next frame on the next TE, while DSI0 is still in BTA or its frame is delayed.
  - The links lose lock-step for that frame. That plausibly explains "a read while both links stream stalled command DMA" (HW:186; patch 0009).
  - Downstream sidesteps this: it reads only before the first frame (A4).
- **[I] Long LP packets:** an LP packet transmitted at an idle point can delay DSI0's next frame start relative to DSI1. For example, the 34-byte `83` gamma write takes roughly 30-40 µs in LPDT. That is the same kind of skew, though shorter.

### C4. What our patches change in the transport

| Patch | Effect |
|---|---|
| 0004 | DPU split-display capability on CTL0/1 (`dpu_1_7_msm8996.h`). Equivalent to downstream `SPLIT_DISPLAY_EN` with the SW-trigger mux (`ML/drivers/gpu/drm/msm/disp/dpu1/dpu_hw_top.c:25-61` vs `CTL:3841-3902`). |
| 0005 | Register writes (`B1`/`B2`) as 0x39 through a raw `transfer()`, **always with `USE_LPM`**, ignoring `mode_flags`. In fixup and wake paths that cleared LPM, the B0 offset was HS but the data write was LP (mixed-mode pairs) until 0025. |
| 0007 | Diagnostic reads clear LPM, so max-return-size and the reads go HS (`P:146-171`). |
| 0008 / 0012 | debugfs `cmd`: one raw packet per `write()` on DSI0. HS by default; the `lp` prefix sets `USE_LPM`. Up to 256 bytes. Serialised only by `ctx->cmd_lock` (`P:583-650`), which no other sender takes. |
| 0009–0011, 0015, 0026 | Fixup: clears LPM on `dsi[0]`, then runs steps: (0) display on; (1) `B0 D9/B1 00`; (2) `B0 D9/B1 08`, `B0 51/B1 06`, gamma; (3) normal conditions. Starts after 5000 ms with 600 ms gaps (`P:55-63, 447-518, 537`). |
| 0013 / 0014 | HS MTP reads (B0 offset, then 0x24 `[D8,len]`), priming ID read, double-read verification (`P:213-263`). |
| 0019 / 0023 / 0027 | `bl_power` path: display on, then normal conditions, with LPM cleared, under `bl_lock` (`P:692-721`). |
| 0025 | The register helper honours `mode_flags` (`P:184`). Init and enable are now all LP; fixup and wake are all HS. |

### C5. Can an LP long write be dropped, reordered or mis-targeted?

- **Mis-targeted**
  - [P] No in the current DT; everything goes to DSI0.
  - [P] Yes if `qcom,sync-dual-dsi` were added (C2 trap).
  - [P] B0 hijack: a `B0 xx` offset write is "targeted" by whatever data write the DDI receives next. See the next item.
- **Interleaved between B0 and the B1/B2 data write.** Two mechanisms:
  1. **[P] Concurrency.** Each message takes `msm_host->cmd_mutex` only for itself, so the pair is not atomic. Possible concurrent senders:
     - fixup worker (`P:504-511`, no lock),
     - `bl_update_status` (`bl_lock`),
     - debugfs (`cmd_lock`),
     - enable/disable (DRM commit),
     - the recovery's `tabs3-recovery` screen daemon writing `bl_power` (`initramfs/tabs3-recovery:259-266`).

     A wake (bl_power 0) during the first ~7 s can interleave `B0 4D` from one thread with `B1 00` from the fixup. That writes a compression or ACL value into the wrong register. The fixup, `bl_update_status`, `report()` and `read_mtp` also save and restore `dsi->mode_flags` without a shared lock (`P:150-168,217-235,247-254,451-478,703-714`), so under concurrency a packet's LP/HS mode is not deterministic. Downstream excludes all of this with `cmd_mutex` per command set.
  2. **[P] Frames.** A DPU kickoff can put a whole frame (`2C`/`3C` memory writes) between the B0 DMA and the data DMA. Downstream has the same exposure in burst mode, and worse, because it can even insert mid-frame. **[I]** Whether the ANA38401 keeps its global-parameter offset across a memory write is unknown; see E5.
- **Dropped**
  - [P] DMA timeout, -ETIMEDOUT after 200 ms (`:1418-1427`): `mipi_dsi_multi_context` then skips the rest of that context (`accum_err`), and `fixup_step` aborts the remaining steps (`P:478-489, 504-511`).
  - [P] `transfer` before a mode is set returns -EINVAL (`:1715-1716`).
  - [P] Neither path is silent in our configuration; both log.
- **Reordered within one thread:** no. The DMA engine executes triggers in order.
- **Mixed-mode pairs (historical):** before 0025, fixup and wake pairs were HS offset plus LP data (C4). Init pairs were LP/LP.

---

## D. Compression / dual-link quirk

**[P] Nothing in the downstream MDP/DSI side explains a "toggle while frames flow" need:**
- No compression on the host side. There is no `qcom,compression-mode` in the dtsi or stock node; `compression_mode` is used only for DSC/FBC (`CTL:4006-4030, 4122-4127`).
- `B1[D9]` ("Anapass compression mode") is an ordinary DDI register in the on-command list.
- No pingpong split: dual-LM dual-display with `lm_widths[0] = 1024` (`DS/mdss_dsi_panel.c:1856-1880`; `CTL:4171-4190`).
- No partial update (dtsi `207-209` commented). The col/page address is sent only in ping-pong-timeout recovery.
- No autorefresh (E).
- Split-display, stream-size and DCS-insert programming are equivalent:
  - Word count 3073, `2C`/`3C`: `DS/mdss_dsi_host.c:1376-1418` vs `ML/drivers/gpu/drm/msm/dsi/dsi_host.c:1060-1082`.
  - Split pipe: `CTL:3853-3884` vs `dpu_hw_top.c:37-60`.
- The first kickoff does nothing DDI-specific beyond running `panel_on` (`DS/mdss_mdp_intf_cmd.c:2766-2773`): "the panel is turned on only when we send the first frame".

**[P] So downstream does not "avoid" the toggle with code. The stock DDI latches dual-link from its plain init.** The differences are environmental:

| # | Stock | Mainline (ours) | Assessment |
|---|---|---|---|
| D1 | Both clock lanes in **LP11** through reset release and TCON_RDY. HS clocks are forced on both links afterwards (`DS/mdss_dsi.c:1651-1729`; `DS/mdss_dsi_host.c:458-459`). | Continuous HS clock running on **both** links before `prepare()` releases reset (`dsi_host.c:878-886` via `dsi_manager.c:311-325`, `P:405-413`). | **[I] Top candidate.** The DDI may detect or lock its input links (or select its UPLL source) when the clock lane enters HS. In mainline that never happens after reset. The compression-mode change looks like the DDI's other "re-init input" trigger. The TCON is clocked from the DSI HS clock (HW:183, patch 0006). |
| D2 | LP on-cmds, then display on (in the list), brightness and mDNIe (HS), tear-on (LP), then the **first frame immediately** (same kickoff). | Init in `prepare()`; display on (LP) + 50 ms + tear on (LP) in `enable()`. The first frame can come seconds later (HW:225-233). Fixup at +5 s. | [I] Contributes. The DDI may apply a pending input configuration only at the first frame boundary after it is written, and only while some window is open. |
| D3 | LP packets accepted (the stock on-cmds work; LP reads work at `on_pre`). | LP reads get BTA with no data (HW:185). LP display-on before frames can leave it dark (patch 0010). | [I] Either LP reception is broken in the post-reset state under mainline's clocking (D1), or the DDI ignores commands in that state. Readback (E2) decides. |
| D4 | First boot: HS `manufacture_read_pre` writes `D9=08` **before** `51=06`, then the LP on-cmds write `51` and then `D9` again. | `51`, then `D9`, once, LP. | [I] Weak: wake on stock has only the on-cmds, and that works. Cheap to test (E10). |
| D5 | NULL insertion on both links, RX_EOT_IGNORE, HS timer `0x3fd08`, no BLOCK_DMA_WITHIN_FRAME. | none of these, BLOCK_DMA set. | [I] Low for the latch. NULL insertion affects how the links idle between line packets, so it is worth one A/B (E12). |

**Related [H] items that point at D1/D3 rather than at the register list:**
- A full re-init (DPMS off/on, or a VDD cycle) leaves the panel **dark** even with the fixup (`todo.md:22-24`; patch 0018/0019). Only the boot path, where the bootloader had already run the panel, recovers.
- If the fixup ran before any frame, the DDI stopped producing TE (HW:228-233).

---

## E. TE and refresh

| | Downstream | Mainline DPU (msm8996, DPU 1.7) |
|---|---|---|
| TE source | Panel TE pin to GPIO10 `mdp_vsync` (node `:241,266`). `MDP_VSYNC_SEL` left at reset (GPIO0). | Same pin (`DTS:148-160`). `MDP_VSYNC_SEL` = GPIO_0 for both PPs (`dpu_kms.c:555-575`, `dpu_encoder.c:755-800`, `dpu_hw_top.c:161-185`). |
| DSI TE select | TRIG_CTRL bit 31 (`te_sel=1`) | `DSI_TRIG_CTRL_TE` always (`dsi_host.c:839`) |
| Panel commands | `44 05 F6` (scanline 1526) in on-cmds, LP; `35 00` after on-cmds, LP | Same, both LP (`P:348`, `P:528`) |
| Tear check | Per PP, both CTLs (`DS/mdss_mdp_intf_cmd.c:186-251, 253-336`): `BIT19 \| BIT20(hw_vsync) \| vclks_line`, sync_cfg_height `0xfff0`, init 1536, start 1536, rd_ptr 1537, thresholds 4/4, refx100 6000 (`DS/mdss_dsi_panel.c:1916-1938`). Enabled at `panel_on` (`:2185`). | Per phys/PP (`dpu_encoder_phys_cmd.c:336-415`; `dpu_hw_pingpong.c:78-106`): `BIT19 \| BIT20 \| vsync_count`, vsync_count = 19.2 MHz / (1554 × 60), **sync_cfg_height = 2 × vtotal = 3108**, init/start 1536, rd_ptr 1537, thresholds 4/4. External TE is reconnected after every kickoff (`:691-698`). |
| Autorefresh | Off. Cleared at tear-check set-up if left by splash (`:350-381`); enabled only by the sysfs `mdss_mdp_cmd_set_autorefresh_mode` (`:2217`). | Never enabled. Force-disabled before each kickoff (`dpu_encoder_phys_cmd.c:610-635`; `dpu_hw_pingpong.c:217-258`). |
| Clock gating between frames | Disabled for this TCON (`tcon-clk-on-support`) | DSI stays runtime-active while the bridge is enabled (`dsi_manager.c:303-309,331`) |

**[P] Conclusion.** TE and autorefresh behaviour is equivalent. A command-mode panel scans static content from its own GRAM with no host traffic, so missing autorefresh cannot produce rolling lines on static content.

The only TE difference is the fallback when TE is missing: about 2 frames (mainline) vs 0xfff0 lines (downstream). That matters only when TE stops (the HW:228-233 case).

The timing check is also fine. TE at panel line 1526 resets the PP counter to 1536, and writes start there. At 893 Mbps a line write takes about 6.9 µs against a panel line read of about 10.7 µs, so the write stays ahead of the read and nothing tears.

**[H] Cause of the rolling lines.** They and the washed colours went away when ACL-on and the smart-ACL ELVSS (`1B`) were applied over HS on a settled panel. Battery current fell from about −1.47 A to +0.16 A (HW:509-531). Stock never shows the cold-start drive state (`ACL off`, `ELVSS 0F` from the on-cmds): it sends the brightness packet in HS immediately after the on-cmds and before the first frame (`DS/ss_dsi_panel_common.c:1674-1681`).

---

## F. Gap list, explanations and decisive experiments

The experiments use the existing debugfs (`/sys/kernel/debug/ams968hh01/cmd`; `lp` prefix = LP; reads as `<type> <params…> <len>`) and module parameters.

To force continuous frames, run `work/panel-refresh-test` (30 Hz). For a static screen with no frames, stop fbcon cursor blinking (`echo 0 > /sys/class/graphics/fbcon/cursor_blink`) and keep userspace from drawing.

Read-only register checks with `devmem` (busybox):

| Register | DSI0 | DSI1 | Expected |
|---|---|---|---|
| CMD_DMA_CTRL | `0x0099403c` | `0x0099603c` | `0x14000000` when idle |
| TRIG_CTRL | `0x00994084` | | `0x80001004` |
| LANE_CTRL | `0x009940ac` | `0x009960ac` | bit 28 set |

### (1) "LP writes do not take effect"

**Proven / observed:**
- [P] The mainline and downstream LP transmit paths are register-identical (A2, C1).
- [H] The working compression/dual-DSI fixup in packages up to 24 sent its `B1` data **in LP** (forced by 0005). Note that each data write still followed an HS `B0` offset write. So LP data writes do land on a running panel.
- [H] Normal conditions in the same step as the compression change failed both in LP (package 23) and in HS (package 24). A separate later step works (0026).
- [H] LP reads return BTA with no data (HW:185), while stock reads are LP (A2). There is a mainline/DDI-state LP problem at least for reads.

**Likely explanations, ranked:**
1. **[I] Ordering.** The compression/dual-link re-latch at the next frame boundary resets or discards the B2 drive registers (ACL/ELVSS) and any pending update-key latch. Settings sent before it (init) or with it (same step) are lost. This explains 0023, 0024, 0026 and 0027 without involving LP.
2. **[I] DDI state before the first HS traffic or frames.** LP packets may be ignored (or LP reads unanswered) while the DDI runs in the clocking state produced by D1. That would make the whole init sequence ineffective, consistent with "init alone stays single-link", "LP display on stays dark" and the DPMS-dark case.
3. **[P]/[I] B0 hijack by concurrent senders** (C5). This one is real code-wise and timing-dependent; it affects wake during the fixup window.
4. **[I] A frame between the B0 and data DMAs** resets the global-parameter offset.

**Experiments:**
- **E1 (LP vs HS A/B on a settled panel)** — after boot plus fixup, with frames stopped:
  - `echo "lp 39 90 00 00 c9" > cmd`: AID 51 nit; a visible dim means an LP long write landed.
  - Restore with `echo "39 90 00 00 0e" > cmd`.
  - Repeat with `lp 05 28` / `05 29` (display off/on).
  - Then repeat with frames streaming (`panel-refresh-test`).
- **E2 (did the LP init land?)** — boot with `panel_samsung_ams968hh01.fixup=0`, wait (single-link state), then read back over HS:
  - `echo "15 b0 51" > cmd; echo "24 b1 01 1" > cmd; cat cmd`
  - Likewise `b0 d9` / `b1`, and `b0 4d`, `b0 36`, `b0 67` / `b2`.
  - If B1/B2 do not answer the generic read, try `06 b1 1`.
  - Then run `echo 1 > fixup` and read the same registers again.
  - **Values present before the fixup** mean LP init landed and the problem is the latch (go to the 5 s section). **Reset defaults** mean the LP init was lost (hypothesis 2).
- **E3 (does the compression toggle reset the drive registers?)** — on a correct, settled panel, run the toggle by hand in HS:
  1. `15 b0 d9` / `39 b1 00`
  2. wait about 1 s with frames
  3. `15 b0 d9` / `39 b1 08` / `15 b0 51` / `39 b1 06`

  Then check whether the washed colours and rolling lines return, and read back `B2[4D]`, `B2[67]`. A yes confirms hypothesis 1.
- **E4 (LP read with and without streaming)** — `lp 06 da 1` vs `06 da 1` on a static screen, then while `panel-refresh-test` runs. If LP reads answer on a static, settled panel, the LP read failure is state- or frame-related and not about LP itself.
- **E5 (does a frame clear B0?)** — `15 b0 36`, then force at least one frame (write a pixel to `/dev/fb0`), then `39 b2 12`. Read back `B2[36]` and `B2[00]`.
- **E-race** — during the first 8 s after enable, toggle `bl_power` 4 → 0 repeatedly. Wrong colours or geometry afterwards confirm the B0 hijack. Fix: one driver mutex around every B0-plus-data sequence and around the `mode_flags` save/restore, shared by fixup, `bl_update_status`, debugfs, enable and disable.

### (2) The first ~5 s are garbled

**Proven / observed:**
- [P] The 5 s comes from `fixup_delay_ms = 5000` (`P:59,537`, patch 0015). The fixup steps that follow take another 3 × 600 ms.
- [H] Until the compression register changes while frames flow, the DDI decodes link 0 as compressed single-link (HW:187-196).
- [P] Downstream has no compensating code (D).

**Likely explanations, ranked:**
1. **[I] Clock-lane state across reset and TCON_RDY** (D1).
2. **[I] The LP init is not applied in that state** (hypothesis 2 above; E2 decides).
3. **[I] No frame immediately after init and display-on** (D2).
4. **[I] Init ordering** (D4).

**Experiments:**
- **E6** — send the init in HS: clear `MIPI_DSI_MODE_LPM` around `ams968hh01_init()` and `write_gamma()`, for example with a new `init_hs` parameter. Boot with `fixup=0`. If dual-link appears, the init was being lost in LP.
- **E7** — in the garbled state (`fixup=0`), toggle DSI1's clock-lane HS force with devmem: clear bit 28 of `0x009960ac`, wait about 50 ms, set it again. Repeat for DSI0 (`0x009940ac`). If the DDI then switches to dual-link without a compression write, D1 is confirmed.
  - Expect a transient blank. This is not persistent.
- **E8 (fix candidate for D1)** — in `prepare()`, keep both clock lanes out of HS until TCON_RDY:
  - Either: a small DSI host hook that clears CLKLN_HS_FORCE_REQUEST on both hosts before reset release and sets it after TCON_RDY.
  - Or as a quick test: devmem from an initramfs hook between modprobe and enable is not practical, so use the hook.
  - Compare against `fixup=0`.
- **E9** — readback as in E2, immediately after init and again after the first frame, to see when `51`/`D9` take effect.
- **E10** — add the stock first-boot pre-sequence in HS before the init (`B0 34/B2 64 00`, `B0 D9/B1 08`, `B0 51/B1 06`, `B0 75/B2 28`), with `fixup=0`.
- **E11 (independent of root cause)** — start the fixup after N rd_ptr/vblank events (real frame traffic) instead of a fixed 5 s, as `todo.md:17-19` suggests. This removes the dependency on fbcon timing.
- **E12 (low priority)** — enable NULL insertion on both hosts: devmem `0x0099[46]2b4 = 0x1` before enable. Separately, set HS_TIMER_CTRL `0x3fd08` and EOT `0x11` (`0x0099[46]0cc`). Check whether any of these change the latch.

### (3) Rolling horizontal lines on static bright content

**Proven / observed:**
- [H] They disappear when ACL-on plus smart-ACL ELVSS are applied over HS after the compression latch, and current drops sharply (HW:509-531).
- [P] Stock applies these drive conditions (the brightness packet, HS) before the first frame, on every panel-on (A4, B).
- [P] TE and autorefresh match stock and cannot cause artefacts on static content (E).

**Explanation:**
- [I] The cold-start on-command values (`ACL off`, `ELVSS 0F`) at 360 nit with bright content overload the AMOLED supply or emission drive, producing banding or rolling. This is panel-internal.
- [I] When the lines persist after the fixup, the drive values were reset by the compression re-latch (F1, hypothesis 1) or hijacked (C5).

**Experiments:**
- **E13** — on a settled bad panel, send ACL alone (`15 b0 4d`/`39 b2 05`, `15 b0 49`/`39 b2 7f`, `15 b0 36`/`39 b2 12`, `15 b0 35`/`39 b2 01`) and ELVSS alone (`15 b0 67`/`39 b2 1b` + key). Note which one removes the lines and the current draw.
- **E14** — confirm that the lines are DDI-internal: stop all frames (static), then check whether the lines still roll. Also check that the DPU frame counter and vblank count do not advance (`/sys/kernel/debug/dri/*/`).
- **E15** — confirm TE is alive: count TE / rd_ptr IRQs (`/proc/interrupts`, mdss) over 1 s while static. It should read about 60/s whenever vblank IRQs are enabled; failing that, use `dpu` debugfs `vsync` info.

### Further recommendations

1. **[P] Single sequence lock.** Make every multi-packet register sequence atomic in the driver, mirroring downstream's `cmd_mutex` per command set (C5).
2. **Reads only when frames are stopped.** Issue reads only when no frames can start, or in `prepare()` before the first frame as stock does. Never issue them on a streaming dual link (C3).
3. **Match stock modes where stock is explicit:**
   - display-off in HS (stock `off-command-state = dsi_hs_mode`);
   - drive conditions in HS immediately after display-on;
   - reads: stock uses LP requests, which only works if hypothesis 2 is fixed.
4. **Write-pointer reset.** Consider a downstream-style write-pointer reset (`2A 0000-07FF`, `2B 0000-05FF`, HS) after any DPU kickoff timeout (`DS/mdss_dsi.c:2872-2925`).
