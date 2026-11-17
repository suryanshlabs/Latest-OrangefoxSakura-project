#!/usr/bin/env python3
"""
simg2img.py - convert an Android sparse image to a raw image, dependency-free.

Stock Xiaomi fastboot ROMs ship `vendor.img` either raw or in the Android
sparse format (`simg2img` from the Android SDK is not guaranteed to exist on a
build host, and this project must not require the SDK). This converter is the
one piece of that tooling the extraction workflow needs.

A file that is already raw is copied unchanged, so callers can always run this
step and then treat the output as a plain ext4 image.

Usage:
  python3 tools/simg2img.py <input> <output>
  python3 tools/simg2img.py --info <input>     # print format, do not convert
"""

from __future__ import annotations

import shutil
import struct
import sys

SPARSE_MAGIC = 0xED26FF3A
CHUNK_RAW = 0xCAC1
CHUNK_FILL = 0xCAC2
CHUNK_DONT_CARE = 0xCAC3
CHUNK_CRC32 = 0xCAC4


class SparseError(Exception):
    pass


def is_sparse(path):
    with open(path, "rb") as fh:
        head = fh.read(4)
    return len(head) == 4 and struct.unpack("<I", head)[0] == SPARSE_MAGIC


def info(path):
    with open(path, "rb") as fh:
        head = fh.read(28)
        if len(head) < 28 or struct.unpack("<I", head[:4])[0] != SPARSE_MAGIC:
            return None
        (magic, major, _minor, file_hdr_sz, chunk_hdr_sz, blk_sz,
         total_blks, total_chunks, _checksum) = struct.unpack("<IHHHHIIII", head)
        return {
            "magic": magic,
            "major": major,
            "file_hdr_sz": file_hdr_sz,
            "chunk_hdr_sz": chunk_hdr_sz,
            "blk_sz": blk_sz,
            "total_blks": total_blks,
            "total_chunks": total_chunks,
            "raw_size": blk_sz * total_blks,
        }


def convert(src, dst):
    """Convert src (sparse or raw) to a raw image at dst. Returns bytes written."""
    with open(src, "rb") as fh:
        head = fh.read(28)
        fh.seek(0)
        if len(head) < 28 or struct.unpack("<I", head[:4])[0] != SPARSE_MAGIC:
            with open(dst, "wb") as out:
                shutil.copyfileobj(fh, out)
            return _size(dst)

        (_m, major, _minor, file_hdr_sz, chunk_hdr_sz, blk_sz, total_blks,
         total_chunks, _cs) = struct.unpack("<IHHHHIIII", head)
        if major != 1:
            raise SparseError(f"unsupported sparse major version {major}")
        if file_hdr_sz < 28 or chunk_hdr_sz < 12:
            raise SparseError(
                f"implausible sparse header sizes (file {file_hdr_sz}, chunk {chunk_hdr_sz})")

        fh.seek(file_hdr_sz)
        written = 0
        with open(dst, "wb") as out:
            for index in range(total_chunks):
                chunk_head = fh.read(chunk_hdr_sz)
                if len(chunk_head) < 12:
                    raise SparseError(f"truncated chunk header at chunk {index}")
                c_type, _reserved, chunk_sz, total_sz = struct.unpack_from("<HHII", chunk_head)
                payload = total_sz - chunk_hdr_sz
                if payload < 0:
                    raise SparseError(f"chunk {index} has negative payload size")
                out_bytes = chunk_sz * blk_sz

                if c_type == CHUNK_RAW:
                    remaining = payload
                    while remaining:
                        block = fh.read(min(1 << 20, remaining))
                        if not block:
                            raise SparseError(f"chunk {index}: truncated raw data")
                        out.write(block)
                        remaining -= len(block)
                    written += out_bytes
                elif c_type == CHUNK_FILL:
                    fill = fh.read(4)
                    if len(fill) < 4:
                        raise SparseError(f"chunk {index}: truncated fill value")
                    step = 1 << 20
                    remaining = out_bytes
                    pad = (fill * (step // 4 + 1))[:step]
                    while remaining:
                        take = min(step, remaining)
                        out.write(pad[:take])
                        remaining -= take
                    written += out_bytes
                elif c_type == CHUNK_DONT_CARE:
                    step = 1 << 20
                    remaining = out_bytes
                    zeros = bytes(step)
                    while remaining:
                        take = min(step, remaining)
                        out.write(zeros[:take])
                        remaining -= take
                    written += out_bytes
                elif c_type == CHUNK_CRC32:
                    # Metadata only: the 4-byte CRC of this chunk footprint.
                    fh.seek(payload, 1)
                else:
                    raise SparseError(f"chunk {index}: unknown type 0x{c_type:04X}")

            expected = blk_sz * total_blks
            if written != expected:
                raise SparseError(
                    f"sparse expansion produced {written} bytes, header promised {expected}")
    return written


def _size(path):
    import os
    return os.path.getsize(path)


def main(argv):
    args = argv[1:]
    if len(args) == 2 and args[0] == "--info":
        data = info(args[1])
        if data is None:
            print(f"{args[1]}: raw image (not Android sparse)")
            return 0
        print(f"{args[1]}: Android sparse v{data['major']}, block {data['blk_sz']} B, "
              f"{data['total_chunks']} chunks, raw size {data['raw_size']} B")
        return 0
    if len(args) != 2:
        print(__doc__)
        return 2
    try:
        written = convert(args[0], args[1])
    except (OSError, SparseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"converted {args[0]} -> {args[1]} ({written} bytes raw)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
