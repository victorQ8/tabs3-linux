# Upstream drafts

Patches from `kernel/patches/` prepared for mainline, rebased on `v7.3-rc7`
(`base-commit` in each file) and **not sent**. They were written with AI
assistance (`Assisted-by:` tags), so under
`Documentation/process/coding-assistants.rst` only the owner can certify the
Developer's Certificate of Origin: review each patch, then add your own
`Signed-off-by:` (a known identity) before sending. The AI does not send
anything.

Checked here: each applies to `v7.3-rc7`; an arm64 `defconfig` build of the
touched drivers with `W=1` shows no warnings; `checkpatch.pl --strict`
reports only the missing `Signed-off-by` (and, for the DPU patch, an unknown
commit ID because the local clone is shallow; `daf9a92daeb8` exists in
mainline). Runtime tests were on the 6.19.5 tablet kernel; see each patch's
notes.

| Directory | Patch | Tree | Ready? |
|---|---|---|---|
| `drm-msm-shared-vm` | drm/msm: keep shared global-VM mappings until the last user (local 0014) | drm/msm | yes, after sign-off |
| `drm-msm-dpu-msm8996-split-ctl` | drm/msm/dpu: enable split display on the MSM8996 CTL_0 and CTL_1 (CTL half of 0004) | drm/msm | yes, after sign-off |
| `input-tc305k` | dt-bindings + Input: tm2-touchkey - add Coreriver TC305K (0015) | input | after the physical key test and `dt_binding_check` |
| `asoc-apq8096-s16` | ASoC: qcom: apq8096: fix back-end sample format to S16_LE (0016) | ASoC | yes, after sign-off |
| `asoc-q6asm-capture-stop` | ASoC: qcom: q6asm-dai: pause and flush capture on stop (0018) | ASoC | no: a partial fix while repeated recordings still fail |

Before sending:

- `drm-msm-shared-vm`: confirm the Codex model for its second `Assisted-by:`
  line (Codex wrote the final-reference half). Reviewers may ask about the
  uninterruptible `dma_resv_wait_timeout()` on the last reference.
  `Cc: stable` covers 6.17+, where the regression started. My reading of
  `Documentation/process/threat-model.rst` is that this is a regular bug, not
  a vulnerability: on a2xx-a5xx every GPU context already shares one address
  space, so no isolation boundary is crossed. Please confirm that judgement.
- `input-tc305k`: run `make dt_binding_check
  DT_SCHEMA_FILES=input/cypress,tm2-touchkey.yaml` (needs `dtschema`).
- All: rerun `scripts/checkpatch.pl --strict` after signing off.

Recipients, from `scripts/get_maintainer.pl`:

- drm/msm (both): Rob Clark <robin.clark@oss.qualcomm.com>, Dmitry Baryshkov
  <lumag@kernel.org>, Abhinav Kumar <abhinav.kumar@linux.dev>, Jessica Zhang
  <jesszhan0024@gmail.com>, Sean Paul <sean@poorly.run>, Marijn Suijten
  <marijn.suijten@somainline.org>, David Airlie <airlied@gmail.com>, Simona
  Vetter <simona@ffwll.ch>; the shared-VM fix also Antonino Maniscalco
  <antomani103@gmail.com>. Lists: linux-arm-msm@vger.kernel.org,
  dri-devel@lists.freedesktop.org, freedreno@lists.freedesktop.org,
  linux-kernel@vger.kernel.org.
- input: Dmitry Torokhov <dmitry.torokhov@gmail.com>, linux-input@vger.kernel.org,
  linux-kernel@vger.kernel.org; the binding also Rob Herring <robh@kernel.org>,
  Krzysztof Kozlowski <krzk+dt@kernel.org>, Conor Dooley <conor+dt@kernel.org>,
  Stephan Gerhold <stephan@gerhold.net>, devicetree@vger.kernel.org.
- ASoC (both): Srinivas Kandagatla <srini@kernel.org>, Liam Girdwood
  <lgirdwood@gmail.com>, Mark Brown <broonie@kernel.org>, Jaroslav Kysela
  <perex@perex.cz>, Takashi Iwai <tiwai@suse.com>, linux-sound@vger.kernel.org,
  linux-arm-msm@vger.kernel.org, linux-kernel@vger.kernel.org.

Rerun `get_maintainer.pl` on the signed patches before sending; lists change.

Not proposed yet: 0005 (a new MIPI DSI mode flag needs discussion), 0006 (the
panel driver itself is not upstream; it needs a binding), 0007 and 0008
(bring-up workarounds: an out-of-binding DT property and a PHY table
selected by a new compatible), and 0009-0013 (new SM5705 drivers that need
bindings and probably an MFD core). 0017 is a backport and already upstream.
