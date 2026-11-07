#!/usr/bin/env python3
"""Build the SM-T825 sensor registry image from this tablet's own Android backup.

Run on the PC from the project root, with Unicorn and pyelftools installed
(see tools/sensor-registry/README.md):

    python3 tools/sensor-registry/make-registry.py \\
        private/backups/<stamp>-system/system.img.zst [private/sensors]

The sensor DSP (SLPI) reads its configuration from a registry served by the
application processor. Android's sensors.qti created that registry, sns.reg:
one byte image of 100 groups at fixed offsets. Each group starts from the
defaults that sns_group_data_init() fills in, and sensor_def_qcomdev.conf
then sets single items. This script runs Samsung's own sns_group_data_init()
in a Unicorn ARM64 emulator for every group, applies the configuration file
and writes:

    OUTDIR/registry.bin   the registry image
    OUTDIR/groups.conf    "group size offset" for every group

Both files derive from Samsung's software: keep them under private/ and
never commit or publish them. The table addresses below come from IDA's
analysis of the exact sensors.qti build checked by SENSORS_QTI_SHA256.
"""
import hashlib
import io
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from elftools.elf.elffile import ELFFile
from unicorn import UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM, Uc, UcError
from unicorn.arm64_const import (UC_ARM64_REG_LR, UC_ARM64_REG_PC, UC_ARM64_REG_SP,
                                 UC_ARM64_REG_TPIDR_EL0, UC_ARM64_REG_X0, UC_ARM64_REG_X1,
                                 UC_ARM64_REG_X2)

SENSORS_QTI = '/vendor/bin/sensors.qti'
SENSOR_DEF = '/vendor/etc/sensors/sensor_def_qcomdev.conf'
SENSORS_QTI_SHA256 = '5b7bf4d54af3fa75060336178ddee443065554699adaf7522d308a8d810bb14b'
# registry.bin that brought the SLPI's Sensor Manager up on 2026-10-13
VALIDATED_SHA256 = '381ca9df9d7eff5cdf356ecb6179fe6333c1413fd82b9820b03a16bc9ed5db51'

GROUP_TABLE, GROUP_COUNT = 0x34E70, 100   # u16 size, u16 offset, u16 id
ITEM_TABLE, ITEM_COUNT = 0x292F0, 2400    # 20 bytes: u32 type, u16 offset @4, u16 id @16
TYPE_SIZES = 0x24B10                      # u8 size per item type
SNS_GROUP_DATA_INIT = 0x14274
PATCH_RETURN_1 = [0x183D0]                # sns_debug_is_module_disabled
PATCH_RETURN = [0x17F34]                  # sns_debug_printf_string

TRAP_BASE, TRAP_SIZE = 0x10000000, 0x10000
STOP = TRAP_BASE + TRAP_SIZE - 4
STACK_BASE, STACK_SIZE = 0x20000000, 0x100000
TLS_BASE = 0x30000000
BUF_BASE = 0x40000000

RET = struct.pack('<I', 0xD65F03C0)
MOV_W0_1 = struct.pack('<I', 0x52800020)


def page(x, up=False):
    return (x + 0xFFF) & ~0xFFF if up else x & ~0xFFF


def extract(backup, workdir):
    """Copy the two vendor files out of the ext4 system image (read-only)."""
    image = backup
    if backup.suffix == '.zst':
        image = workdir / 'system.img'
        with open(image, 'wb') as out:
            subprocess.run(['zstd', '-q', '-d', '-c', str(backup)], stdout=out, check=True)
    files = {}
    for path in (SENSORS_QTI, SENSOR_DEF):
        dest = workdir / Path(path).name
        subprocess.run(['debugfs', '-R', f'dump {path} {dest}', str(image)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not dest.is_file() or dest.stat().st_size == 0:
            sys.exit(f'{path} not found in {backup}')
        files[path] = dest.read_bytes()
    if image != backup:
        image.unlink()
    return files[SENSORS_QTI], files[SENSOR_DEF].decode()


def emulate(data):
    """Return the default image, the group table and the item table."""
    elf = ELFFile(io.BytesIO(data))
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    for seg in elf.iter_segments():
        if seg['p_type'] != 'PT_LOAD':
            continue
        lo, hi = page(seg['p_vaddr']), page(seg['p_vaddr'] + seg['p_memsz'], up=True)
        mu.mem_map(lo, hi - lo)
        mu.mem_write(seg['p_vaddr'], data[seg['p_offset']:seg['p_offset'] + seg['p_filesz']])

    # Imports: every GOT slot points at its own RET in the trap page.
    mu.mem_map(TRAP_BASE, TRAP_SIZE)
    mu.mem_write(TRAP_BASE, RET * (TRAP_SIZE // 4))
    dynsym = elf.get_section_by_name('.dynsym')
    traps = {}
    for sec in elf.iter_sections():
        if sec['sh_type'] != 'SHT_RELA':
            continue
        for r in sec.iter_relocations():
            kind = r['r_info_type']
            if kind == 1027:                       # R_AARCH64_RELATIVE
                mu.mem_write(r['r_offset'], struct.pack('<Q', r['r_addend']))
            elif kind in (1025, 1026):             # GLOB_DAT, JUMP_SLOT
                addr = TRAP_BASE + 4 * len(traps)
                traps[addr] = dynsym.get_symbol(r['r_info_sym']).name
                mu.mem_write(r['r_offset'], struct.pack('<Q', addr))

    for ea in PATCH_RETURN_1:
        mu.mem_write(ea, MOV_W0_1 + RET)
    for ea in PATCH_RETURN:
        mu.mem_write(ea, RET)

    mu.mem_map(STACK_BASE, STACK_SIZE)
    mu.mem_map(TLS_BASE, 0x1000)
    mu.mem_write(TLS_BASE + 40, struct.pack('<Q', 0x5A5A5A5A12345678))   # stack guard
    mu.reg_write(UC_ARM64_REG_TPIDR_EL0, TLS_BASE)
    mu.mem_map(BUF_BASE, 0x10000)

    def on_trap(uc, address, size, _):
        if address == STOP:
            uc.emu_stop()
            return
        name = traps.get(address, f'trap@{address:#x}')
        x0, x1, x2 = (uc.reg_read(r) for r in (UC_ARM64_REG_X0, UC_ARM64_REG_X1, UC_ARM64_REG_X2))
        if name in ('memcpy', 'memmove', '__memcpy_chk', '__memmove_chk'):
            uc.mem_write(x0, bytes(uc.mem_read(x1, x2)))
        elif name in ('memset', '__memset_chk'):
            uc.mem_write(x0, bytes([x1 & 0xFF]) * x2)
        elif name == '__stack_chk_fail':
            raise RuntimeError('stack protector failure in emulated code')
        else:
            uc.reg_write(UC_ARM64_REG_X0, 0)       # debug and logging calls
        # the trap slot itself is a RET, which returns to the caller

    mu.hook_add(UC_HOOK_CODE, on_trap, begin=TRAP_BASE, end=TRAP_BASE + TRAP_SIZE - 1)

    groups = [struct.unpack_from('<HHH', data, GROUP_TABLE + 6 * i) for i in range(GROUP_COUNT)]
    image = bytearray(max(off for _, off, _ in groups) + 256)
    failed = []
    for size, off, gid in groups:
        mu.mem_write(BUF_BASE, b'\0' * 0x1000)
        mu.reg_write(UC_ARM64_REG_SP, STACK_BASE + STACK_SIZE - 0x100)
        mu.reg_write(UC_ARM64_REG_X0, gid)
        mu.reg_write(UC_ARM64_REG_X1, BUF_BASE)
        mu.reg_write(UC_ARM64_REG_LR, STOP)
        try:
            mu.emu_start(SNS_GROUP_DATA_INIT, STOP, count=2_000_000)
        except UcError as e:
            sys.exit(f'group {gid}: emulation error {e} at pc {mu.reg_read(UC_ARM64_REG_PC):#x}')
        if mu.reg_read(UC_ARM64_REG_X0) & 0xFFFFFFFF:
            failed.append(gid)                      # as sns_reg_storage_init: zeros
            continue
        image[off:off + size] = bytes(mu.mem_read(BUF_BASE, size))

    sizes = data[TYPE_SIZES:TYPE_SIZES + 32]
    items = {}
    for i in range(ITEM_COUNT):
        rec = data[ITEM_TABLE + 20 * i:ITEM_TABLE + 20 * (i + 1)]
        typ, off, iid = (struct.unpack_from('<I', rec)[0], struct.unpack_from('<H', rec, 4)[0],
                         struct.unpack_from('<H', rec, 16)[0])
        items.setdefault(iid, (sizes[typ] if typ < len(sizes) else None, off))
    return image, groups, items, failed


def apply_config(image, items, conf):
    """Write each "item value" line of sensor_def_qcomdev.conf into the image."""
    written, unknown = 0, []
    for line in conf.splitlines():
        m = re.match(r'^(\d+)\s+(-?(?:0[xX][0-9a-fA-F]+|\d+))', line.split('#', 1)[0].strip())
        if not m:
            continue
        iid, value = int(m.group(1)), int(m.group(2), 0)
        size, off = items.get(iid, (None, 0))
        if not size:
            unknown.append(iid)
            continue
        image[off:off + size] = (value & ((1 << (8 * size)) - 1)).to_bytes(size, 'little')
        written += 1
    return written, unknown


def main():
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__.split('\n\n')[1])
    backup = Path(sys.argv[1])
    outdir = Path(sys.argv[2] if len(sys.argv) == 3 else 'private/sensors')
    for tool in ('zstd', 'debugfs'):
        if not shutil.which(tool):
            sys.exit(f'{tool} is required')
    outdir.mkdir(parents=True, exist_ok=True)
    outdir.chmod(0o700)
    with tempfile.TemporaryDirectory(dir=outdir) as tmp:
        qti, conf = extract(backup, Path(tmp))
    if hashlib.sha256(qti).hexdigest() != SENSORS_QTI_SHA256:
        sys.exit(f'{SENSORS_QTI} is not the build this script was written for '
                 f'(sha256 {hashlib.sha256(qti).hexdigest()})')
    image, groups, items, failed = emulate(qti)
    written, unknown = apply_config(image, items, conf)
    (outdir / 'registry.bin').write_bytes(bytes(image))
    (outdir / 'groups.conf').write_text(
        '# group size offset (Samsung SM-T825 sensors.qti registry table)\n' +
        ''.join(f'{gid} {size} {off}\n' for size, off, gid in groups))
    digest = hashlib.sha256(image).hexdigest()
    print(f'{len(groups)} groups ({len(failed)} without defaults), '
          f'{written} configuration items ({len(unknown)} unknown)')
    print(f'{outdir}/registry.bin: {len(image)} bytes, sha256 {digest}')
    print('matches the validated image' if digest == VALIDATED_SHA256 else
          'DIFFERS from the validated image')


if __name__ == '__main__':
    main()
