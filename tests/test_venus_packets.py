"""Compile the actual Venus packetizer and verify HFI version dispatch.

Kernel allocation/hash helpers are small host substitutes. Packet structures,
constants and serialization code are taken from the prepared kernel tree.
This checks bytes and dispatch, not firmware acceptance or video quality.
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
VENUS = Path('drivers/media/platform/qcom/venus')
PATCH = ROOT / 'kernel/patches/0048-media-venus-enable-8x8-transform-packets-on-hfi-v3.patch'
EOS_PATCH = ROOT / 'kernel/patches/0049-media-venus-accept-empty-encoder-eos-on-hfi-v3.patch'

PREFIX = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#define ENOTSUPP 524 /* Linux internal errno, not part of userspace errno.h. */
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t s32;
typedef int irqreturn_t;
struct device;
#define __counted_by(x)
#define struct_size(p, member, n) (sizeof(*(p)) + sizeof((p)->member[0]) * (n))
#define struct_size_t(t, member, n) (sizeof(t) + sizeof(((t *)0)->member[0]) * (n))
#define lower_32_bits(x) ((u32)(x))
#define upper_32_bits(x) ((u32)((u64)(x) >> 32))
#define hash32_ptr(p) ((u32)(uintptr_t)(p))
'''

CHECK = r'''
int main(void) {
    const enum hfi_version versions[] = {HFI_VERSION_1XX, HFI_VERSION_3XX,
                                        HFI_VERSION_4XX, HFI_VERSION_6XX};
    union { uint64_t align; unsigned char bytes[512]; } storage;
    struct hfi_session_set_property_pkt *pkt = (void *)storage.bytes;
    void *cookie = (void *)(uintptr_t)0x1234;
    for (unsigned v = 0; v < 4; v++) {
        pkt_set_version(versions[v]);
        for (u32 enabled = 0; enabled <= 1; enabled++) {
            struct hfi_h264_8x8_transform control = {.enable_type = enabled};
            memset(&storage, 0xa5, sizeof(storage));
            int ret = pkt_session_set_property(pkt, cookie,
                HFI_PROPERTY_PARAM_VENC_H264_TRANSFORM_8X8, &control);
            bool supported = v >= 2 || (FIXED && v == 1);
            assert(ret == (supported ? 0 : -EINVAL));
            if (supported) {
                assert(pkt->shdr.hdr.pkt_type == HFI_CMD_SESSION_SET_PROPERTY);
                assert(pkt->shdr.session_id == 0x1234 && pkt->num_properties == 1);
                assert(pkt->shdr.hdr.size == sizeof(*pkt) + sizeof(u32) + sizeof(control));
                assert(pkt->data[0] == HFI_PROPERTY_PARAM_VENC_H264_TRANSFORM_8X8);
                assert(pkt->data[1] == enabled);
                for (unsigned i = pkt->shdr.hdr.size; i < sizeof(storage); i++)
                    assert(storage.bytes[i] == 0xa5);
            }
            assert(pkt_session_set_property(NULL, cookie,
                HFI_PROPERTY_PARAM_VENC_H264_TRANSFORM_8X8, &control) == -EINVAL);
            assert(pkt_session_set_property(pkt, NULL,
                HFI_PROPERTY_PARAM_VENC_H264_TRANSFORM_8X8, &control) == -EINVAL);
            assert(pkt_session_set_property(pkt, cookie,
                HFI_PROPERTY_PARAM_VENC_H264_TRANSFORM_8X8, NULL) == -EINVAL);
            assert(pkt_session_set_property(pkt, cookie, 0xffffffff, &control) == -EINVAL);
        }
    }
    return 0;
}
'''


class VenusPacketTests(unittest.TestCase):
    def test_encoder_eos_address_and_packet_validation(self):
        if not (SRC / VENUS / 'hfi_cmds.c').exists():
            self.skipTest('Run scripts/prepare-lte-kernel.py to test kernel code')
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            shutil.copytree(SRC / VENUS, tmp / VENUS)
            for fixed in (True, False):
                with self.subTest(fixed=fixed):
                    if not fixed:
                        subprocess.run(['patch', '--quiet', '--reverse', '--fuzz=0', '-p1',
                                        '-i', str(EOS_PATCH)], cwd=tmp, check=True)
                    headers = '\n'.join((tmp / VENUS / f).read_text()
                                        for f in ('hfi_helper.h', 'hfi.h', 'hfi_cmds.h', 'hfi_cmds.c'))
                    body = re.sub(r'^#include[^\n]*\n', '', headers, flags=re.M)
                    venc = (tmp / VENUS / 'venc.c').read_text()
                    start = venc.index('\t\tfdata.buffer_type = HFI_BUFFER_INPUT;', venc.index('venc_encoder_cmd('))
                    stop = venc.index('\n\t\tret = hfi_session_process_buf', start)
                    make_eos = '''
struct mock_core { enum hfi_version version; };
struct mock_inst { struct mock_core *core; };
#define IS_V3(core) ((core)->version == HFI_VERSION_3XX)
static struct hfi_frame_data eos(struct mock_inst *inst) {
    struct hfi_frame_data fdata = {0};
''' + venc[start:stop] + '\nreturn fdata;\n}\n'
                    check = r'''
int main(void) {
    const enum hfi_version versions[]={HFI_VERSION_1XX,HFI_VERSION_3XX,HFI_VERSION_4XX,HFI_VERSION_6XX};
    struct hfi_session_empty_buffer_uncompressed_plane0_pkt pkt;
    void *cookie=(void *)(uintptr_t)0x1234;
    for(unsigned n=0;n<4;n++) {
        struct mock_core core={versions[n]}; struct mock_inst inst={&core};
        struct hfi_frame_data frame=eos(&inst);
        assert(frame.buffer_type==HFI_BUFFER_INPUT && frame.flags==HFI_BUFFERFLAG_EOS);
        assert(frame.alloc_len==0 && frame.filled_len==0);
        assert(frame.device_addr==((FIXED && n==1) ? 0u : 0xdeadb000u));
        assert(pkt_session_etb_encoder(&pkt,cookie,&frame)==0);
        assert(pkt.packet_buffer==frame.device_addr && pkt.flags==HFI_BUFFERFLAG_EOS);
        assert(pkt.shdr.hdr.size==sizeof(pkt) && pkt.alloc_len==0 && pkt.filled_len==0);
    }
    struct hfi_frame_data frame={.device_addr=0,.alloc_len=4096};
    assert(pkt_session_etb_encoder(&pkt,cookie,&frame)==-EINVAL);
    frame.alloc_len=0; frame.flags=HFI_BUFFERFLAG_EOS;
    assert(pkt_session_etb_encoder(&pkt,cookie,&frame)==(FIXED ? 0 : -EINVAL));
    assert(pkt_session_etb_encoder(&pkt,NULL,&frame)==-EINVAL);
    frame.device_addr=0x10000; frame.alloc_len=4096; frame.filled_len=1024;
    assert(pkt_session_etb_encoder(&pkt,cookie,&frame)==0);
    assert(pkt.alloc_len==4096 && pkt.filled_len==1024 && pkt.packet_buffer==0x10000);
    return 0;
}
'''
                    source, binary = tmp/'eos.c', tmp/'eos'
                    source.write_text(PREFIX + body + make_eos + check)
                    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                    '-Wno-unused-parameter', f'-DFIXED={int(fixed)}',
                                    str(source), '-o', str(binary)], check=True)
                    subprocess.run([str(binary)], check=True, timeout=5)

    def test_transform_packet_and_version_compatibility(self):
        if not (SRC / VENUS / 'hfi_cmds.c').exists():
            self.skipTest('Run scripts/prepare-lte-kernel.py to test kernel code')
        headers = '\n'.join((SRC / VENUS / f).read_text()
                            for f in ('hfi_helper.h', 'hfi.h', 'hfi_cmds.h'))
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            target = tmp / VENUS / 'hfi_cmds.c'
            target.parent.mkdir(parents=True)
            target.write_bytes((SRC / VENUS / 'hfi_cmds.c').read_bytes())
            for fixed in (True, False):
                with self.subTest(fixed=fixed):
                    if not fixed:
                        subprocess.run(['patch', '--quiet', '--reverse', '--fuzz=0',
                                        '-p1', '-i', str(PATCH)], cwd=tmp, check=True)
                    body = re.sub(r'^#include[^\n]*\n', '', headers + target.read_text(), flags=re.M)
                    source, binary = tmp/'packet.c', tmp/'packet'
                    source.write_text(PREFIX + body + CHECK)
                    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                                    f'-DFIXED={int(fixed)}', str(source), '-o', str(binary)], check=True)
                    subprocess.run([str(binary)], check=True, timeout=5)


if __name__ == '__main__':
    unittest.main()
