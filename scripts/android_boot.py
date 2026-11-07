#!/usr/bin/env python3
"""Read Android v0 / Samsung legacy boot containers without extracting files."""
import dataclasses
import hashlib
import struct
import zlib


def align(size, page):
    return (size + page - 1) // page * page


@dataclasses.dataclass
class BootImage:
    kernel: bytes
    ramdisk: bytes
    device_trees: bytes
    kernel_addr: int
    ramdisk_addr: int
    tags_addr: int
    page_size: int
    os_version: int
    cmdline: str


def parse_boot(data):
    if len(data) < 1632 or data[:8] != b'ANDROID!':
        raise ValueError('Not an Android boot image')
    ks, ka, rs, ra, ss, sa, ta, ps, dt_size, osv = struct.unpack_from('<10I', data, 8)
    if ps not in (2048, 4096, 8192, 16384) or not ks or ss:
        raise ValueError('Unsupported page size, empty kernel or second-stage payload')
    # Old Samsung headers use the future header_version word for dt_size.
    # Modern v1/v2/v3/v4 have a small version value: do not misparse those.
    if 0 < dt_size < 4096:
        raise ValueError('Unsupported modern boot header version')
    rdoff = ps + align(ks, ps)
    dtoff = rdoff + align(rs, ps)
    if ps + ks > len(data) or rdoff + rs > len(data) or dtoff + dt_size > len(data):
        raise ValueError('Truncated boot image')
    cmd = (data[64:576] + data[608:1632]).split(b'\0', 1)[0].decode('ascii')
    return BootImage(data[ps:ps+ks], data[rdoff:rdoff+rs], data[dtoff:dtoff+dt_size],
                     ka, ra, ta, ps, osv, cmd)


def appended_dtbs(image):
    if image.device_trees:
        data = image.device_trees
        if data[:4] != b'QCDT':
            raise ValueError('Expected Qualcomm DT table in legacy boot image')
    elif image.kernel[:2] == b'\x1f\x8b':
        decoder = zlib.decompressobj(31)
        decoder.decompress(image.kernel)
        if not decoder.eof:
            raise ValueError('Truncated kernel gzip')
        data = decoder.unused_data
    else:
        raise ValueError('Unsupported donor kernel layout')
    result = []
    pos = 0
    while (pos := data.find(b'\xd0\x0d\xfe\xed', pos)) >= 0:
        if pos + 40 > len(data):
            raise ValueError('Truncated DTB header')
        size = struct.unpack_from('>I', data, pos + 4)[0]
        if not 40 <= size <= 2 * 1024 * 1024 or pos + size > len(data):
            raise ValueError('Invalid DTB length')
        result.append(data[pos:pos+size])
        pos += size
    if not result:
        raise ValueError('No donor DTBs found')
    return result


def verify_v0_id(data):
    image = parse_boot(data)
    if image.device_trees:
        raise ValueError('ID validation here only supports generated v0 images')
    digest = hashlib.sha1()
    for payload in (image.kernel, image.ramdisk, b''):
        digest.update(payload)
        digest.update(struct.pack('<I', len(payload)))
    if data[576:608] != digest.digest().ljust(32, b'\0'):
        raise ValueError('Android image ID checksum mismatch')
    return image
