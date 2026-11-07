"""Exercise the driver's stock command tuple, write failures and off-state caching."""
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def added_function(name):
    patch = ROOT / 'kernel/patches/0006-drm-panel-samsung-ams968hh01-complete-sm-t825-support.patch'
    added = '\n'.join(s[1:] for s in patch.read_text().splitlines()
                      if s.startswith(('+', ' ')) and not s.startswith('+++'))
    start = added.index('static int ' + name + '(')
    opening = added.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (added[end] == '{') - (added[end] == '}')
        end += 1
    return added[start:end]


class BrightnessCommandTests(unittest.TestCase):
    def test_tuple_errors_and_deferred_requests(self):
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint32_t u32; typedef int16_t s16;
#include "ams968hh01-dimming-data.h"
#define AMS_GAMMA_BYTES 33
#define MIPI_DSI_MODE_LPM 1
#define BACKLIGHT_POWER_ON 0
struct mipi_dsi_device { unsigned long mode_flags; };
struct mipi_dsi_multi_context { struct mipi_dsi_device *dsi; int accum_err; };
struct ams968hh01 {
 struct mipi_dsi_device *dsi[2]; bool gamma_valid, enabled;
 u8 gamma[65][33]; unsigned brightness, applied_brightness; int cmd_lock;
};
struct backlight_device { struct {unsigned brightness,power;} props; struct ams968hh01 *ctx; bool blank; };
#define mutex_lock(x) ((void)(x))
#define mutex_unlock(x) ((void)(x))
#define bl_get_data(b) ((b)->ctx)
#define backlight_is_blank(b) ((b)->blank)
static u8 packets[14][34]; static unsigned sizes[14], count, fail_at;
static void ams968hh01_write_register(struct mipi_dsi_multi_context *x, const void *p, unsigned n) {
 if(x->accum_err)return;
 assert(!(x->dsi->mode_flags & MIPI_DSI_MODE_LPM));
 assert(count<14 && n<=34); sizes[count]=n; memcpy(packets[count],p,n); count++;
 if(fail_at && count==fail_at)x->accum_err=-EIO;
}
#define mipi_dsi_dcs_write_seq_multi(ctx,...) do {u8 p[]={__VA_ARGS__}; ams968hh01_write_register(ctx,p,sizeof(p));}while(0)
#define ams968hh01_register_seq mipi_dsi_dcs_write_seq_multi
'''
        code += added_function('ams968hh01_apply_brightness') + '\n'
        code += added_function('ams968hh01_bl_update') + '\n'
        code += r'''
int main(void) {
 struct mipi_dsi_device dsi={.mode_flags=MIPI_DSI_MODE_LPM|0x80};
 struct ams968hh01 ctx={.dsi={&dsi,0},.gamma_valid=true,.enabled=true};
 struct backlight_device bl={.props={86,0},.ctx=&ctx};
 for(unsigned i=0;i<33;i++)ctx.gamma[45][i]=i;
 assert(!ams968hh01_bl_update(&bl));
 assert(count==14 && ctx.brightness==86 && ctx.applied_brightness==86);
 assert(dsi.mode_flags==(MIPI_DSI_MODE_LPM|0x80));
 const u8 expected[][4]={
  {0x90,0,0,0x99},{0xb0,0x4d},{0xb2,5},{0xb0,0x49},{0xb2,0x7f},
  {0xb0,0x36},{0xb2,0x12},{0xb0,0x67},{0xb2,0x21},{0xb0,0x6d},
  {0xb2,0x85},{0x83},{0xb0,0x35},{0xb2,1}};
 for(unsigned i=0;i<14;i++){
  assert(sizes[i]==(i==0?4:i==11?34:2));
  assert(!memcmp(packets[i],expected[i],i==0?4:i==11?1:2));
 }
 assert(!memcmp(packets[11]+1,ctx.gamma[45],33));
 for(unsigned failure=1;failure<=14;failure++){
  count=0;fail_at=failure;bl.props.brightness=255;
  assert(ams968hh01_bl_update(&bl)==-EIO);
  assert(count==failure && ctx.brightness==86 && ctx.applied_brightness==86);
  assert(dsi.mode_flags==(MIPI_DSI_MODE_LPM|0x80));
 }
 count=fail_at=0;ctx.enabled=false;bl.props.brightness=0;
 assert(!ams968hh01_bl_update(&bl) && !count && ctx.brightness==0);
 bl.props.brightness=255;
 assert(!ams968hh01_bl_update(&bl) && !count && ctx.brightness==255);
 bl.props.brightness=256;
 assert(ams968hh01_bl_update(&bl)==-EINVAL && !count);
 bl.props.brightness=86;bl.props.power=4;
 assert(ams968hh01_bl_update(&bl)==-EOPNOTSUPP && !count);
 return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            p = pathlib.Path(directory)
            (p / 'commands.c').write_text(code)
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                            '-I', str(ROOT / 'kernel'), str(p / 'commands.c'),
                            '-o', str(p / 'commands')], check=True)
            subprocess.run([str(p / 'commands')], check=True)


if __name__ == '__main__':
    unittest.main()
