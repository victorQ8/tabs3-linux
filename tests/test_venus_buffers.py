"""Compile the real queue setup before/after the HFI-v3 pool-growth guard.

Transport/PM are mocked; this validates ioctl decisions, not firmware behavior.
"""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'work' / json.loads((ROOT / 'config/sources.json').read_text())['kernel']['directory']
VENC = Path('drivers/media/platform/qcom/venus/venc.c')
PATCH = ROOT / 'kernel/patches/0050-media-venus-refuse-live-static-capture-pool-growth.patch'

HARNESS = r'''
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stddef.h>
#define V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE 10
#define V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE 9
#define IS_V3(c) ((c)->version==3)
#define max(a,b) ((a)>(b)?(a):(b))
#define test_bit(n,p) (!!*(p))
#define wait_event_interruptible(w,c) ((c)?0:-EINTR)
#define mutex_lock(p) (++*(p))
#define mutex_unlock(p) (--*(p))
struct device { int unused; };
struct venus_core { unsigned version,sys_error,sys_err_done; };
struct venus_format { unsigned num_planes,pixfmt; };
struct venus_inst {
    struct venus_core *core; struct venus_format *fmt_out,*fmt_cap;
    unsigned input_buf_size,output_buf_size,num_input_bufs,num_output_bufs;
    unsigned out_width,out_height,width,height;
    bool nonblock,streamon_cap; int lock;
};
struct vb2_queue { struct venus_inst *priv; unsigned type; };
#define vb2_get_drv_priv(q) ((q)->priv)
static int venc_pm_get(struct venus_inst *i) { return 0; }
static int venc_pm_put(struct venus_inst *i,bool last) { return 0; }
static int venc_init_session(struct venus_inst *i) { return 0; }
static int venc_out_num_buffers(struct venus_inst *i,unsigned *num) { *num=4; return 0; }
static unsigned venus_helper_get_framesz(unsigned f,unsigned w,unsigned h) { return 4096; }
'''

CHECK = r'''
int main(void) {
    struct venus_core core={.version=3};
    struct venus_format format={.num_planes=1};
    struct venus_inst i={.core=&core,.fmt_cap=&format,.fmt_out=&format,
        .input_buf_size=4096,.output_buf_size=4096};
    struct vb2_queue q={.priv=&i,.type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE};
    unsigned count=1,planes=1,size=4096;
    i.streamon_cap=true;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==(FIXED ? -EBUSY : 0));
    i.streamon_cap=false;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==0);
    /* Reserve a larger pool up front: no arbitrary four-buffer ceiling. */
    count=12; planes=0;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==0);
    assert(count==12 && i.num_output_bufs==12 && planes==1 && size==4096 && !i.lock);
    size=4095;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==-EINVAL);
    size=4096; planes=2;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==-EINVAL);
    planes=1; i.streamon_cap=true;
    q.type=V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==0);
    q.type=V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    for(unsigned n=4;n<=6;n+=2) {
        core.version=n;
        assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==0);
    }
    core.version=3; core.sys_error=1; i.nonblock=true; i.streamon_cap=false; planes=0;
    assert(venc_queue_setup(&q,&count,&planes,&size,NULL)==-EAGAIN);
    return 0;
}
'''


class VenusBufferTests(unittest.TestCase):
    def test_capture_growth_and_other_queue_paths(self):
        if not (SRC / VENC).exists():
            self.skipTest('Run scripts/prepare-lte-kernel.py first')
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            target = tmp / VENC
            target.parent.mkdir(parents=True)
            target.write_bytes((SRC / VENC).read_bytes())
            for fixed in (True, False):
                with self.subTest(fixed=fixed):
                    if not fixed:
                        subprocess.run(['patch','--quiet','--reverse','--fuzz=0','-p1',
                                        '-i',str(PATCH)],cwd=tmp,check=True)
                    body = target.read_text()
                    match = re.search(r'static int venc_queue_setup\([^;]*?\)\n\{', body)
                    end, depth = match.end(), 1
                    while depth:
                        depth += (body[end]=='{') - (body[end]=='}')
                        end += 1
                    source, binary = tmp/'queue.c', tmp/'queue'
                    source.write_text(HARNESS + body[match.start():end] + CHECK)
                    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                                    f'-DFIXED={int(fixed)}',str(source),'-o',str(binary)],check=True)
                    subprocess.run([str(binary)],check=True,timeout=5)


if __name__ == '__main__':
    unittest.main()
