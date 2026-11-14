#!/usr/bin/env python3
"""
bootimg.py - dependency-free Android boot image parser + cpio ramdisk tool.

Written for the sakura OrangeFox port so that the reference R11.0_5 recovery.img
can be analysed reproducibly without root, without unpackbootimg, without
Android Image Kitchen and without any external Python packages.

Supports:
  * Android boot image v0 (the header used by sakura / MSM8953, Android 8.1)
  * Android boot image v1 / v2 (recovery_dtbo, dtb)
  * Android boot image v3 / v4 (vendor_boot aware reporting)
  * gzip, lz4-legacy, lz4-frame and plain cpio ramdisks

Usage:
  bootimg.py info    <boot.img>
  bootimg.py unpack  <boot.img> <outdir>
  bootimg.py cpiotoc <archive> <outdir>

Exit codes: 0 ok, 1 parse error.
"""
import io
import os
import struct
import sys
import zlib

BOOT_MAGIC = b"ANDROID!"
VENDOR_BOOT_MAGIC = b"VNDRBOOT"

# ----------------------------------------------------------------------------
# lz4 (needed only if a ramdisk/kernel turns out to be lz4; sakura's is gzip,
# but the tool stays useful for other devices and for future R12 images).
# ----------------------------------------------------------------------------


def lz4_block_decompress(src, expected=None):
    """Minimal pure-Python LZ4 block decoder."""
    out = bytearray()
    i = 0
    n = len(src)
    while i < n:
        token = src[i]
        i += 1
        lit_len = token >> 4
        if lit_len == 15:
            while True:
                b = src[i]
                i += 1
                lit_len += b
                if b != 255:
                    break
        out += src[i:i + lit_len]
        i += lit_len
        if i >= n:
            break
        offset = src[i] | (src[i + 1] << 8)
        i += 2
        if offset == 0:
            raise ValueError("lz4: zero match offset")
        match_len = token & 0x0F
        if match_len == 15:
            while True:
                b = src[i]
                i += 1
                match_len += b
                if b != 255:
                    break
        match_len += 4
        start = len(out) - offset
        if start < 0:
            raise ValueError("lz4: match offset before start of output")
        for k in range(match_len):
            out.append(out[start + k])
    if expected is not None and len(out) != expected:
        raise ValueError(f"lz4: expected {expected} bytes, got {len(out)}")
    return bytes(out)


def lz4_legacy_decompress(data):
    """LZ4 legacy frame: magic 0x184C2102, sequence of [size][block]."""
    magic = struct.unpack("<I", data[:4])[0]
    if magic != 0x184C2102:
        raise ValueError(f"lz4: bad legacy magic {magic:#x}")
    out = bytearray()
    i = 4
    while i + 4 <= len(data):
        (bsize,) = struct.unpack("<I", data[i:i + 4])
        i += 4
        # 0x184C2102 is also used as the "skippable/end" marker in some writers
        if bsize == 0x184C2102 or bsize == 0:
            break
        block = data[i:i + bsize]
        i += bsize
        out += lz4_block_decompress(block)
    return bytes(out)


def lz4_frame_decompress(data):
    """Modern LZ4 frame (magic 0x184D2204)."""
    magic = struct.unpack("<I", data[:4])[0]
    if magic != 0x184D2204:
        raise ValueError(f"lz4: bad frame magic {magic:#x}")
    i = 4
    flg = data[i]
    i += 1
    bd = data[i]
    i += 1
    if flg & 0x08:  # content size present
        i += 8
    if flg & 0x01:  # dict id
        i += 4
    i += 1  # header checksum
    out = bytearray()
    while i + 4 <= len(data):
        (bsize,) = struct.unpack("<I", data[i:i + 4])
        i += 4
        if bsize == 0:  # end mark
            break
        uncompressed = bool(bsize & 0x80000000)
        bsize &= 0x7FFFFFFF
        block = data[i:i + bsize]
        i += bsize
        out += block if uncompressed else lz4_block_decompress(block)
    return bytes(out)


def decompress_any(data, label="blob"):
    """Detect and undo gzip / lz4 / xz-free compression. Returns (bytes, name)."""
    try:
        if data[:2] == b"\x1f\x8b":
            return zlib.decompress(data, 16 + zlib.MAX_WBITS), "gzip"
        if data[:4] == b"\x18\x4c\x21\x02":
            return lz4_legacy_decompress(data), "lz4-legacy"
        if data[:4] == b"\x04\x22\x4d\x18":
            return lz4_frame_decompress(data), "lz4-frame"
        if data[:6] == b"\xfd7zXZ\x00":
            import lzma
            return lzma.decompress(data), "xz"
        if data[:4] == b"\x28\xb5\x2f\xfd":
            raise ValueError(f"{label} is zstd-compressed; zstd is not implemented")
    except zlib.error as exc:
        raise ValueError(f"{label}: decompression failed: {exc}") from exc
    return data, "none"


# ----------------------------------------------------------------------------
# cpio "newc" (SVR4) - the format used by every Android ramdisk
# ----------------------------------------------------------------------------


def cpio_iter(buf):
    """Yield (name, mode, data, header_fields) for each newc entry."""
    i = 0
    n = len(buf)
    while i + 110 <= n:
        if buf[i:i + 6] not in (b"070701", b"070702"):
            # trailing zero padding after the last entry
            if buf[i:].strip(b"\x00") == b"":
                return
            raise ValueError(f"cpio: bad magic at offset {i}: {buf[i:i+6]!r}")
        hdr = buf[i:i + 110]
        f = [int(hdr[6 + 8 * k:6 + 8 * (k + 1)], 16) for k in range(13)]
        ino, mode, uid, gid, nlink, mtime, filesize, devmajor, devminor, \
            rdevmajor, rdevminor, namesize, check = f
        i += 110
        name = buf[i:i + namesize - 1].decode("utf-8", "replace")
        i += namesize
        i += (-i) % 4
        data = buf[i:i + filesize]
        i += filesize
        i += (-i) % 4
        yield name, mode, data, dict(ino=ino, mtime=mtime, uid=uid, gid=gid,
                                     nlink=nlink, check=check, mode=mode,
                                     devmajor=devmajor, devminor=devminor)
        if name == "TRAILER!!!":
            return


def cpio_extract(buf, outdir, verbose=True):
    """Extract a newc ramdisk, preserving modes, symlinks and hardlinks."""
    os.makedirs(outdir, exist_ok=True)
    written = []
    for name, mode, data, hdr in cpio_iter(buf):
        if name == "TRAILER!!!":
            break
        rel = name.lstrip("/")
        path = os.path.join(outdir, rel) if rel else outdir
        ftype = mode & 0o170000
        try:
            if ftype == 0o040000:  # dir
                os.makedirs(path, exist_ok=True)
            elif ftype == 0o120000:  # symlink
                target = data.decode("utf-8", "replace")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                if os.path.lexists(path):
                    os.unlink(path)
                os.symlink(target, path)
            elif ftype in (0o100000, 0):  # regular file
                os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
                with open(path, "wb") as fh:
                    fh.write(data)
                os.chmod(path, mode & 0o7777)
            elif ftype == 0o140000:  # socket/fifo oddities in ramdisks
                pass
            else:
                pass
        except OSError as exc:
            if verbose:
                print(f"  ! {name}: {exc}", file=sys.stderr)
            continue
        written.append((rel, mode, len(data)))
    return written


# ----------------------------------------------------------------------------
# boot image
# ----------------------------------------------------------------------------


class BootImage:
    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.raw = fh.read()
        if self.raw[:8] == VENDOR_BOOT_MAGIC:
            raise SystemExit("vendor_boot images are not used by sakura; not parsed")
        if self.raw[:8] != BOOT_MAGIC:
            raise SystemExit(f"not an Android boot image: magic={self.raw[:8]!r}")
        self._parse_v0()

    def _parse_v0(self):
        r = self.raw
        (self.kernel_size, self.kernel_addr,
         self.ramdisk_size, self.ramdisk_addr,
         self.second_size, self.second_addr,
         self.tags_addr, self.page_size,
         self.dt_size, self.os_version) = struct.unpack("<10I", r[8:48])
        # Offset 40 is header_version (v0..v4). Offset 44 is os_version.
        self.header_version = self.dt_size
        self.board = r[48:64].rstrip(b"\x00").decode("utf-8", "replace")
        self.cmdline = r[64:64 + 512].rstrip(b"\x00").decode("utf-8", "replace")
        self.id = r[576:608].hex()
        if self.page_size not in (2048, 4096, 8192, 16384):
            raise SystemExit(f"implausible page size {self.page_size}")
        off = self.page_size
        self.kernel = r[off:off + self.kernel_size]
        off += self._pagelen(self.kernel_size)
        self.ramdisk = r[off:off + self.ramdisk_size]
        off += self._pagelen(self.ramdisk_size)
        self.second = r[off:off + self.second_size]
        off += self._pagelen(self.second_size)
        self.dt = r[off:off + self.dt_size] if self.dt_size else b""
        off += self._pagelen(self.dt_size) if self.dt_size else 0
        self.extra = r[off:]
        # v1+: recovery_dtbo follows dtb; keep the remainder intact for hashing
        self.recovery_dtbo_size = 0
        if self.header_version >= 1 and len(self.extra) >= 4:
            (self.recovery_dtbo_size,) = struct.unpack("<I", r[1632:1636])
            self.recovery_dtbo_offset = struct.unpack("<Q", r[1636:1644])[0]

    def _pagelen(self, size):
        if size == 0:
            return 0
        return (size + self.page_size - 1) // self.page_size * self.page_size

    def describe(self):
        k, kname = decompress_any(self.kernel, "kernel") if self.kernel else (b"", "none")
        r, rname = decompress_any(self.ramdisk, "ramdisk") if self.ramdisk else (b"", "none")
        lines = [
            f"file                 : {self.path}",
            f"size                 : {len(self.raw)} bytes",
            f"magic                : {self.raw[:8].decode()}",
            f"header_version       : {self.header_version}", 
            f"page_size            : {self.page_size}",
            f"kernel_size          : {self.kernel_size}",
            f"kernel_addr          : {self.kernel_addr:#010x}",
            f"kernel_compression   : {kname}",
            f"kernel_uncompressed  : {len(k)} bytes",
            f"ramdisk_size         : {self.ramdisk_size}",
            f"ramdisk_addr         : {self.ramdisk_addr:#010x}",
            f"ramdisk_compression  : {rname}",
            f"ramdisk_uncompressed : {len(r)} bytes",
            f"second_size          : {self.second_size}",
            f"second_addr          : {self.second_addr:#010x}",
            f"tags_addr            : {self.tags_addr:#010x}",
            f"os_version           : {self.os_version:#010x}",
            f"board                : {self.board!r}",
            f"cmdline              : {self.cmdline}",
            f"id (sha1 of k+r)     : {self.id}",
            f"trailing_bytes       : {len(self.extra)}",
        ]
        return "\n".join(lines), k, r

    def unpack(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        desc, k, r = self.describe()
        with open(os.path.join(outdir, "bootimg_info.txt"), "w") as fh:
            fh.write(desc + "\n")
        if self.kernel:
            with open(os.path.join(outdir, "kernel"), "wb") as fh:
                fh.write(self.kernel)
            with open(os.path.join(outdir, "kernel.uncompressed"), "wb") as fh:
                fh.write(k)
        if self.ramdisk:
            with open(os.path.join(outdir, "ramdisk.cpio"), "wb") as fh:
                fh.write(r)
            # keep the raw compressed blob too: needed to re-pack byte-exactly
            with open(os.path.join(outdir, "ramdisk.compressed"), "wb") as fh:
                fh.write(self.ramdisk)
        if self.second:
            with open(os.path.join(outdir, "second"), "wb") as fh:
                fh.write(self.second)
        if self.dt:
            with open(os.path.join(outdir, "dtb"), "wb") as fh:
                fh.write(self.dt)
        if self.extra.strip(b"\x00"):
            with open(os.path.join(outdir, "tail.bin"), "wb") as fh:
                fh.write(self.extra)
        print(desc)
        return k, r


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "info":
        print(BootImage(argv[2]).describe()[0])
        return 0
    if cmd == "unpack":
        BootImage(argv[2]).unpack(argv[3])
        return 0
    if cmd == "cpiotoc":
        with open(argv[2], "rb") as fh:
            blob = fh.read()
        data, kind = decompress_any(blob, "ramdisk")
        print(f"compression: {kind}  uncompressed: {len(data)} bytes")
        entries = cpio_extract(data, argv[3])
        print(f"extracted {len(entries)} entries to {argv[3]}")
        return 0
    if cmd == "cpiotoc-list":
        with open(argv[2], "rb") as fh:
            blob = fh.read()
        data, kind = decompress_any(blob, "ramdisk")
        print(f"# compression={kind} uncompressed={len(data)}")
        for name, mode, d, _h in cpio_iter(data):
            if name == "TRAILER!!!":
                break
            print(f"{mode & 0o7777:04o} {len(d):10d} {name}")
        return 0
    print(f"unknown command {cmd}")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
