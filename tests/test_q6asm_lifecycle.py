"""Execute the real q6asm response/trigger code with a simulated APR transport.

Run scripts/prepare-lte-kernel.py first. Both old and fixed control flows are
compiled; the old code must reproduce the two regressions. This does not
simulate DSP firmware, scheduling, DMA, or prove hardware stream recovery.
"""
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'work' / json.loads((ROOT / 'config/sources.json').read_text())['kernel']['directory']
Q6 = Path('sound/soc/qcom/qdsp6')
PATCHES = [ROOT / 'kernel/patches' / name for name in (
    '0047-asoc-qcom-q6asm-dai-flush-after-successful-capture-pause.patch',
    '0046-asoc-qcom-q6asm-drop-responses-for-closed-data-streams.patch')]


def function(source, name):
    start = source.index(name)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def code(tree):
    asm = (tree / Q6 / 'q6asm.c').read_text()
    dai = (tree / Q6 / 'q6asm-dai.c').read_text()
    callback = function(asm, 'static int32_t q6asm_stream_callback(')
    block = callback[callback.index('case APR_BASIC_RSP_RESULT:'):
                     callback.index('case ASM_DATA_EVENT_WRITE_DONE_V2:')]
    return '\n'.join((
        'static int response(struct audio_client *ac, struct apr_resp_pkt *data) {\n'
        'struct aprv2_ibasic_rsp_result_t *result = data->payload;\n'
        'struct apr_hdr *hdr = &data->hdr; uint32_t client_event = 0; int ret = 0;\n'
        'switch (hdr->opcode) {\n' + block + '\n}\ndone: return ret;\n}',
        function(asm, 'static int __q6asm_cmd('),
        function(asm, 'int q6asm_cmd_nowait('),
        function(dai, 'static int q6asm_dai_trigger(')))


HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
struct apr_hdr { uint32_t opcode, token, pkt_size; };
struct apr_pkt { struct apr_hdr hdr; };
struct apr_resp_pkt { struct apr_hdr hdr; void *payload; };
struct aprv2_ibasic_rsp_result_t { uint32_t opcode, status; };
struct audio_client {
    void *adev, *dev, *priv;
    struct aprv2_ibasic_rsp_result_t result;
    int cmd_wait;
    void (*cb)(uint32_t, uint32_t, void *, void *);
};
struct q6asm_dai_rtd { struct audio_client *audio_client; uint32_t stream_id; };
struct snd_pcm_runtime { void *private_data; };
struct snd_pcm_substream { struct snd_pcm_runtime *runtime; int stream; };
struct snd_soc_component { int unused; };
static unsigned callbacks, errors, sent, opcodes[4];
static int pause_result, flush_result;
#define APR_HDR_SIZE 20
#define dev_err(...) ((void)++errors)
#define wake_up(wait) (++*(wait))
static void event(uint32_t kind, uint32_t token, void *payload, void *priv) {
    ++callbacks;
}
static void q6asm_add_hdr(struct audio_client *ac, struct apr_hdr *hdr,
                         unsigned size, bool sync, uint32_t stream) {
    *hdr = (struct apr_hdr){.pkt_size = size};
}
static int apr_send_pkt(void *adev, struct apr_pkt *pkt) {
    assert(sent < 4); opcodes[sent++] = pkt->hdr.opcode;
    if (pkt->hdr.opcode == ASM_SESSION_CMD_PAUSE) return pause_result;
    if (pkt->hdr.opcode == ASM_STREAM_CMD_FLUSH) return flush_result;
    return pkt->hdr.pkt_size;
}
static int q6asm_ac_send_cmd_sync(struct audio_client *ac, struct apr_pkt *pkt) { return 0; }
static void q6asm_reset_buf_state(struct audio_client *ac) {}
static int q6asm_run_nowait(struct audio_client *ac, uint32_t stream,
                            int a, int b, int c) { return APR_HDR_SIZE; }
'''

CHECKS = r'''
static void deliver(struct audio_client *ac, uint32_t opcode, uint32_t status) {
    struct aprv2_ibasic_rsp_result_t payload = {opcode, status};
    struct apr_resp_pkt pkt = {{.opcode = APR_BASIC_RSP_RESULT}, &payload};
    assert(response(ac, &pkt) == 0);
}
static void responses(void) {
    const uint32_t late[] = {ASM_DATA_CMD_READ_V2, ASM_DATA_CMD_WRITE_V2, ASM_DATA_CMD_EOS};
    const uint32_t controls[] = {ASM_STREAM_CMD_CLOSE, ASM_SESSION_CMD_PAUSE,
        ASM_STREAM_CMD_FLUSH, ASM_STREAM_CMD_OPEN_READ_V3, ASM_STREAM_CMD_OPEN_WRITE_V3};
    for (unsigned s = 0; s < 2; s++) {
        for (unsigned i = 0; i < sizeof(late)/sizeof(*late); i++) {
            struct audio_client ac = {.cb = event}; callbacks = errors = 0;
            deliver(&ac, ASM_STREAM_CMD_CLOSE, 0);
            deliver(&ac, late[i], s);
            /* Before the waiting thread runs, the old callback overwrites
             * CLOSE_DONE and the wait condition becomes false again. */
            assert(ac.result.opcode == (FIXED ? ASM_STREAM_CMD_CLOSE : late[i]));
            assert(ac.cmd_wait == (FIXED ? 1 : 2));
            if (FIXED) assert(callbacks == 1 && errors == 0 && ac.result.status == 0);
            ac = (struct audio_client){.cb = event}; callbacks = errors = 0;
            deliver(&ac, late[i], s);
            if (FIXED) assert(ac.cmd_wait == 0 && ac.result.opcode == 0 && callbacks == 0);
            deliver(&ac, ASM_STREAM_CMD_CLOSE, 0);
            assert(ac.result.opcode == ASM_STREAM_CMD_CLOSE);
        }
        for (unsigned i = 0; i < sizeof(controls)/sizeof(*controls); i++) {
            struct audio_client ac = {.cb = event};
            deliver(&ac, controls[i], s);
            assert(ac.result.opcode == controls[i] && ac.result.status == s);
            assert(ac.cmd_wait == 1); /* Real control/error replies still wake. */
        }
    }
}
static void capture_stop(void) {
    struct audio_client ac = {0};
    struct q6asm_dai_rtd prtd = {&ac, 1};
    struct snd_pcm_runtime runtime = {&prtd};
    struct snd_pcm_substream sub = {&runtime, SNDRV_PCM_STREAM_CAPTURE};
    const int success[] = {0, APR_HDR_SIZE};
    for (unsigned i = 0; i < 2; i++) {
        sent = 0; pause_result = success[i]; flush_result = APR_HDR_SIZE;
        assert(q6asm_dai_trigger(NULL, &sub, SNDRV_PCM_TRIGGER_STOP) >= 0);
        assert(opcodes[0] == ASM_SESSION_CMD_PAUSE);
        assert(sent == ((FIXED || success[i] == 0) ? 2 : 1));
        if (sent == 2) assert(opcodes[1] == ASM_STREAM_CMD_FLUSH);
    }
    sent = 0; pause_result = -EAGAIN;
    assert(q6asm_dai_trigger(NULL, &sub, SNDRV_PCM_TRIGGER_STOP) == -EAGAIN);
    assert(sent == 1); /* Never flush after a failed pause. */
    sent = 0; pause_result = 0; flush_result = -EIO;
    assert(q6asm_dai_trigger(NULL, &sub, SNDRV_PCM_TRIGGER_STOP) == -EIO);
    assert(sent == 2);
    if (FIXED) {
        sent = 0; pause_result = APR_HDR_SIZE;
        assert(q6asm_dai_trigger(NULL, &sub, SNDRV_PCM_TRIGGER_STOP) == -EIO);
        assert(sent == 2);
    }
    sent = 0; sub.stream = SNDRV_PCM_STREAM_PLAYBACK;
    assert(q6asm_dai_trigger(NULL, &sub, SNDRV_PCM_TRIGGER_STOP) >= 0);
    assert(sent == 1 && opcodes[0] == ASM_DATA_CMD_EOS);
    sent = 0;
    assert(q6asm_dai_trigger(NULL, &sub, -123) == -EINVAL && sent == 0);
}
int main(void) { responses(); capture_stop(); return 0; }
'''


class AudioLifecycleTests(unittest.TestCase):
    def test_late_responses_and_capture_flush(self):
        if not (SRC / Q6 / 'q6asm.c').exists():
            self.skipTest('Run scripts/prepare-lte-kernel.py to test kernel code')
        constants = {}
        # ALSA stream directions are enum members, while the commands are macros.
        stream_enum = re.search(r'SNDRV_PCM_STREAM_PLAYBACK\s*=\s*(\d+),\s*'
                                r'SNDRV_PCM_STREAM_CAPTURE,',
                                (SRC / 'include/uapi/sound/asound.h').read_text())
        self.assertIsNotNone(stream_enum)
        constants['SNDRV_PCM_STREAM_PLAYBACK'] = int(stream_enum[1])
        constants['SNDRV_PCM_STREAM_CAPTURE'] = int(stream_enum[1]) + 1
        for path in (Q6 / 'q6asm.c', Q6 / 'q6asm.h',
                     Path('include/linux/soc/qcom/apr.h'),
                     Path('include/uapi/sound/asound.h'), Path('include/sound/pcm.h')):
            constants.update(re.findall(r'^#define\s+(\w+)\s+(0x[0-9a-fA-F]+|\d+)\b',
                                       (SRC / path).read_text(), re.M))
        with tempfile.TemporaryDirectory() as tmp:
            tree = Path(tmp)
            (tree / Q6).mkdir(parents=True)
            for name in ('q6asm.c', 'q6asm-dai.c'):
                shutil.copyfile(SRC / Q6 / name, tree / Q6 / name)
            for fixed in (True, False):
                with self.subTest(fixed=fixed):
                    if not fixed:
                        for patch in PATCHES:
                            subprocess.run(['patch', '--quiet', '--reverse', '--fuzz=0',
                                            '-p1', '-i', str(patch)], cwd=tree, check=True)
                    body = HARNESS + code(tree) + CHECKS
                    names = set(re.findall(r'\b(?:ASM_|CMD_|SNDRV_|APR_BASIC_)\w+', body))
                    definitions = '\n'.join(f'#define {name} {constants[name]}' for name in sorted(names))
                    source, binary = tree / 'test.c', tree / 'test'
                    source.write_text(definitions + '\n' + body)
                    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    '-Wno-unused-parameter', f'-DFIXED={int(fixed)}',
                                    str(source), '-o', str(binary)], check=True)
                    subprocess.run([str(binary)], timeout=5, check=True)


if __name__ == '__main__':
    unittest.main()
