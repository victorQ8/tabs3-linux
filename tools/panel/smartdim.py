#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Port of Samsung's GPL smart dimming for the AMS968HH01 (ANA38401), from
# drivers/video/msm/mdss/samsung/ss_dsi_smart_dimming_*.c in
# awesometic/android_kernel_samsung_msm8996 @ f48aec90. It reads the tables
# from those two source files at run time:
#   smartdim.py ss_dsi_smart_dimming_common.c \
#       ss_dsi_smart_dimming_ANA38401_AMS968HH01.h <33 MTP bytes in hex>
# It reproduces the 360 nit gamma our driver computes byte for byte. See
# docs/panel-ams968hh01/brightness.md, section C.
"""Bit-exact Python port of Samsung ss_dsi_smart_dimming_ANA38401_AMS968HH01.c
(arm64: plain char is unsigned).  Usage: smartdim.py <common.c> <panel.h> <mtp hex...>"""
import re, sys, json
M64 = (1 << 64) - 1
common = open(sys.argv[1]).read()
panelh = open(sys.argv[2]).read()
mtp_raw = [int(x, 16) for x in sys.argv[3:]]
assert len(mtp_raw) == 33

def c_int_array(src, name):
    m = re.search(r'int\s+%s\s*\[[^\]]*\]\s*=\s*\{(.*?)\};' % name, src, re.S)
    body = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)
    return [int(x) for x in re.findall(r'-?\d+', body)]
def c_2d(src, name, cols):
    m = re.search(r'static int\s+%s\s*\[\]\s*\[[^\]]*\]\s*=\s*\{(.*?)\n\s*\};' % name, src, re.S)
    body = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)
    nums = [int(x) for x in re.findall(r'-?\d+', body)]
    return [nums[i:i+cols] for i in range(0, len(nums), cols)]

coeff_2p15 = c_int_array(common, 'candela_coeff_2p15')
coeff_2p2 = c_int_array(common, 'candela_coeff_2p2')
curve_2p2_360 = c_int_array(common, 'curve_2p2_360')
assert len(coeff_2p15) == len(coeff_2p2) == len(curve_2p2_360) == 256
candela_table = c_2d(panelh, 'candela_table', 2)
base_lum = c_2d(panelh, 'base_luminance_revA', 2)
grad = c_2d(panelh, 'gradation_offset_revA', 9)
rgbo = c_2d(panelh, 'rgb_offset_revA', 24)
assert len(candela_table) == len(base_lum) == len(grad) == len(rgbo) == 65, (len(candela_table), len(base_lum), len(grad), len(rgbo))

BIT_SHIFT = 22
REF_L = 28521267
REF_H = 6291456
INFL = [0, 1, 3, 11, 23, 35, 51, 87, 151, 203, 255]
u8 = lambda v: v & 0xff

def char_to_int(d):
    return -(d & 0x7f) if d & 0x80 else d
def char_to_int_v255(msb, lsb):
    return -lsb if msb else lsb

# ---- mtp_sorting
sorting = [9, 7, 6, 5, 4, 3, 2, 1, 0, 8, 10, 20, 18, 17, 16, 15, 14, 13, 12, 11, 19, 21, 31, 29, 28, 27, 26, 25, 24, 23, 22, 30, 32]
MTP = [mtp_raw[s] for s in sorting]
for c in range(3):
    if MTP[c*11]:
        MTP[c*11] = u8(-MTP[c*11])
# MTP per colour: 255msb 255lsb 203 151 87 51 35 23 11 3 1
F = {'255msb': 0, '255lsb': 1, '203': 2, '151': 3, '87': 4, '51': 5, '35': 6, '23': 7, '11': 8, '3': 9, '1': 10}
def mtp(c, k): return MTP[c*11 + F[k]]

# ---- gamma_cell_determine (center values, unsigned char)
V255_MSB, V255_LSB = 0x01, 0x00
CENTER = 0x80
VT_CENTER = 0x00
max_lux_table = [0x01, 0x00, 0x01, 0x00, 0x01, 0x00] + [0x80]*24 + [0, 0, 0]

# ---- voltages; level index order: 0,1,3,11,23,35,51,87,151,203,255
L = {c: {} for c in range(3)}
VT = [0]*3
vt_coefficient = [0, 12, 24, 36, 48, 60, 72, 84, 96, 108, 138, 148, 158, 168, 178, 186]
for c in range(3):
    lsb = char_to_int_v255(mtp(c, '255msb'), mtp(c, '255lsb'))
    add = (lsb + ((V255_MSB << 8) | V255_LSB)) & M64
    r2 = (((129 + add) & M64) << BIT_SHIFT) // 640
    r3 = (((REF_L - REF_H) * r2) & M64) >> BIT_SHIFT
    L[c][255] = (REF_L - r3) & M64
    L[c][0] = REF_L
    L[c][1] = 0       # never written (kzalloc)
    lsb = char_to_int(mtp(c, '1'))
    assert lsb >= 0, 'negative VT MTP would index vt_coefficient[] out of bounds'
    r2 = (vt_coefficient[lsb] << BIT_SHIFT) // 600
    r3 = (REF_L * r2) >> BIT_SHIFT
    VT[c] = REF_L - r3
    prev = 255
    for pt in [203, 151, 87, 51, 35, 23, 11]:
        lsb = char_to_int(mtp(c, str(pt)))
        add = (lsb + CENTER) & M64
        r1 = (VT[c] - L[c][prev]) & M64
        r2 = (((64 + add) & M64) << BIT_SHIFT) // 320
        r3 = ((r1 * r2) & M64) >> BIT_SHIFT
        L[c][pt] = (VT[c] - r3) & M64
        prev = pt
    lsb = char_to_int(mtp(c, '3'))
    add = lsb + CENTER
    r1 = (REF_L - L[c][11]) & M64
    r2 = (((64 + add) & M64) << BIT_SHIFT) // 320
    r3 = ((r1 * r2) & M64) >> BIT_SHIFT
    L[c][3] = (REF_L - r3) & M64

# ---- generate_gray_scale
seg = {2: (2, 3), 3: (7, 8), 4: (11, 12), 5: (11, 12), 6: (15, 16), 7: (35, 36), 8: (63, 64), 9: (51, 52), 10: (51, 52)}
G = [[0]*256 for _ in range(3)]
for c in range(3):
    for i, p in enumerate(INFL):
        G[c][p] = L[c][p] if p in L[c] else 0
    def lin(up, low, coeff, deno, cnt):
        r1 = (up - low) & M64
        r2 = (((r1 * (coeff - cnt)) & M64) << BIT_SHIFT) // deno
        return (low + (r2 >> BIT_SHIFT)) & 0xffffffff
    cal = 0
    for cnt in range(256):
        if cnt in INFL and cnt != 1:   # C: cnt==1 falls in the (V0,V3) interpolation branch
            cal = 0; continue
        ai = next(i for i in range(1, 11) if cnt < INFL[i])
        if ai == 1: ai = 2
        up_idx = INFL[ai-2] if ai == 2 else INFL[ai-1]
        coeff, deno = seg[ai]
        G[c][cnt] = lin(G[c][up_idx], G[c][INFL[ai]], coeff, deno, cal)
        cal += 1
# int conversion (GRAY tables are int)
def s32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v

def search(cand):
    for cnt in range(255):
        d1 = cand - curve_2p2_360[cnt]; d2 = cand - curve_2p2_360[cnt+1]
        if d2 < 0: return cnt if d1 + d2 <= 0 else cnt + 1
        if d1 == 0: return cnt
        if d2 == 0: return cnt + 1
    return -1

def gamma_init(cd):
    bl = dict(base_lum)[cd]
    coef = coeff_2p15 if cd < 360 else coeff_2p2
    idx = [search(coef[INFL[k+1]] * bl) for k in range(10)]
    ti = dict(candela_table)[cd]
    for cnt in range(1, 10):
        idx[10 - cnt] += grad[ti][cnt - 1]
        if idx[10 - cnt] == 0: idx[10 - cnt] = 1
    s = [0]*33
    for c in range(3):
        g = lambda i: s32(G[c][i])
        vt = s32(VT[c])
        r1 = (REF_L - g(idx[9])) & M64
        r3 = (((r1 * 640) & M64) // (REF_L - REF_H) - 129) & M64
        s[c*2] = (r3 & 0xff00) >> 8; s[c*2+1] = r3 & 0xff
        pairs = [(6, 8, 9), (9, 7, 8), (12, 6, 7), (15, 5, 6), (18, 4, 5), (21, 3, 4), (24, 2, 3)]
        for base, lo, hi in pairs:
            r1 = (vt - g(idx[lo])) & M64; r2 = (r1 * 320) & M64; r3 = (vt - g(idx[hi])) & M64
            s[base + c] = ((r2 // r3) - 64) & 0xff
        r1 = (REF_L - g(idx[1])) & M64; r2 = (r1 * 320) & M64; r3 = (REF_L - g(idx[2])) & M64
        s[27 + c] = ((r2 // r3) - 64) & 0xff
    s[30:33] = [0, 0, 0]
    gs = list(s)
    for cnt in range(24):
        if cnt < 3:
            v = (s[cnt*2] << 8 | s[cnt*2+1]) + rgbo[ti][cnt]
            gs[cnt*2] = int(v / 256) & 0xff   # C truncation
            gs[cnt*2+1] = v & 0xff
        else:
            gs[cnt+3] += rgbo[ti][cnt]
    return [u8(x) for x in gs], idx

lux = [cd for cd, _ in candela_table]
gen = {}
idxs = {}
for cd in lux:
    gen[cd], idxs[cd] = gamma_init(cd)
gen[360] = list(max_lux_table)

post_sort = [24, 21, 18, 15, 12, 9, 6, 1, 27, 0, 30, 25, 22, 19, 16, 13, 10, 7, 3, 28, 2, 31, 26, 23, 20, 17, 14, 11, 8, 5, 29, 4, 32]
def offeset_add(offset, value):
    if value + offset < 0: return 0
    if value + offset > 255: return 0x80
    return value + offset
out = {}
for cd in lux:
    t = []
    for k in range(33):
        v = gen[cd][post_sort[k]]
        if cd == 360:
            v = offeset_add(v, mtp_raw[k] + 0x7f) if v == 0x01 else offeset_add(v, mtp_raw[k])
        t.append(u8(v))
    for c in range(3):
        if t[c*11 + 9] == 0x01: t[c*11 + 9] = 0x80
    out[cd] = t
json.dump({'gamma': {str(k): v for k, v in out.items()}, 'idx': {str(k): v for k, v in idxs.items()}}, open(sys.argv[0].rsplit('/', 1)[0] + '/gamma-table.json', 'w'))
for cd in lux:
    print(f'{cd:3d} cd: ' + ' '.join(f'{b:02x}' for b in out[cd]))
