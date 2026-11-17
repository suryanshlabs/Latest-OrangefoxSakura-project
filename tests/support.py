"""
support.py - synthetic fixtures for the sakura tooling tests.

No cross-compiler and no Android SDK are available on a clean host, so the
tests build the few artefacts they need themselves:

  * make_elf()      a real ELF header/program-header/dynamic section for the
                    target machine, so tools/elf.py is exercised on actual
                    bytes rather than on a mock;
  * make_sparse()   an Android sparse image (the format a stock fastboot ROM's
                    vendor.img may arrive in), for tools/simg2img.py;
  * make_ext4()     a populated ext4 filesystem, written with e2fsprogs'
                    mke2fs -d, so build/extract_blobs.sh can be tested against
                    a real filesystem read through debugfs.

Everything is dependency-free (python3 + e2fsprogs).
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO, "tools")

EM_386 = 3
EM_X86_64 = 62
EM_AARCH64 = 183


# ---------------------------------------------------------------------------
# ELF
# ---------------------------------------------------------------------------
def make_elf(interp=None, needed=(), soname=None, bits=64, machine=EM_AARCH64):
    """Return the bytes of a minimal but well-formed ELF object.

    With `bits=64`, PT_INTERP/PT_DYNAMIC sections are emitted so a DT_NEEDED
    graph can be expressed: the strings live in a dynstr that a PT_LOAD covers,
    exactly how tools/elf.py resolves them.
    """
    if bits == 32:
        ident = b"\x7fELF" + bytes([1, 1, 1, 0]) + b"\x00" * 8
        hdr = struct.pack("<HHIIIIIHHHHHH", 3, machine, 1, 0, 0, 0, 0, 52, 32, 0, 40, 0, 0)
        return ident + hdr

    ident = b"\x7fELF" + bytes([2, 1, 1, 0]) + b"\x00" * 8

    names = list(needed) + ([soname] if soname else [])
    dynstr = bytearray(b"\x00")
    offsets = {}
    for name in names:
        offsets[name] = len(dynstr)
        dynstr += name.encode() + b"\x00"

    entries = []
    for name in needed:
        entries.append((1, offsets[name]))          # DT_NEEDED
    if soname:
        entries.append((14, offsets[soname]))       # DT_SONAME
    entries.append((5, 0))                          # DT_STRTAB (patched below)
    entries.append((10, len(dynstr)))               # DT_STRSZ
    entries.append((0, 0))                          # DT_NULL

    phnum = 1 + (1 if interp else 0) + 1
    off = 64 + 56 * phnum

    interp_bytes = (interp.encode() + b"\x00") if interp else b""
    interp_off = (off + 7) & ~7
    off = interp_off + len(interp_bytes)
    dynstr_off = (off + 7) & ~7
    off = dynstr_off + len(dynstr)
    dyn_off = (off + 7) & ~7
    total = dyn_off + 16 * len(entries)

    entries = [(5, dynstr_off) if tag == 5 else (tag, val) for tag, val in entries]

    phdrs = bytearray()
    phdrs += struct.pack("<IIQQQQQQ", 1, 7, 0, 0, 0, total, total, 0x1000)  # PT_LOAD
    if interp:
        phdrs += struct.pack("<IIQQQQQQ", 3, 4, interp_off, interp_off,
                             interp_off, len(interp_bytes), len(interp_bytes), 1)
    phdrs += struct.pack("<IIQQQQQQ", 2, 6, dyn_off, dyn_off,
                         dyn_off, 16 * len(entries), 16 * len(entries), 8)

    ehdr = ident + struct.pack("<HHIQQQIHHHHHH", 3, machine, 1, 0, 64, 0, 0,
                               64, 56, phnum, 64, 0, 0)
    body = bytearray(total)
    body[0:len(ehdr)] = ehdr
    body[64:64 + len(phdrs)] = phdrs
    if interp:
        body[interp_off:interp_off + len(interp_bytes)] = interp_bytes
    body[dynstr_off:dynstr_off + len(dynstr)] = dynstr
    for i, (tag, val) in enumerate(entries):
        struct.pack_into("<qQ", body, dyn_off + 16 * i, tag, val)
    return bytes(body)


# ---------------------------------------------------------------------------
# Android sparse image
# ---------------------------------------------------------------------------
def make_sparse(payload, block_size=4096):
    """Wrap raw bytes in an Android sparse image made of RAW chunks."""
    if len(payload) % block_size:
        payload = payload + bytes(block_size - len(payload) % block_size)
    blocks = len(payload) // block_size
    chunk_hdr_sz = 12
    file_hdr_sz = 28
    total_sz = chunk_hdr_sz + len(payload)
    header = struct.pack("<IHHHHIIII", 0xED26FF3A, 1, 0, file_hdr_sz, chunk_hdr_sz,
                         block_size, blocks, 1, 0)
    chunk = struct.pack("<HHII", 0xCAC1, 0, blocks, total_sz)
    return header + chunk + payload


# ---------------------------------------------------------------------------
# ext4 image
# ---------------------------------------------------------------------------
def make_ext4(image_path, files, size_blocks=32768, block_size=1024):
    """Create an ext4 image at image_path containing `files` (path -> bytes|str).

    `files` keys are absolute image paths (e.g. "/build.prop") or relative.
    """
    if not shutil.which("mke2fs"):
        raise RuntimeError("mke2fs is required for the ext4 fixture "
                           "(apt-get install e2fsprogs)")
    staging = image_path + ".tree"
    shutil.rmtree(staging, ignore_errors=True)
    for rel, content in files.items():
        rel = rel.lstrip("/")
        target = os.path.join(staging, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = content.encode() if isinstance(content, str) else content
        with open(target, "wb") as fh:
            fh.write(data)
    os.makedirs(staging, exist_ok=True)
    proc = subprocess.run(
        ["mke2fs", "-q", "-F", "-t", "ext4", "-b", str(block_size),
         "-d", staging, image_path, str(size_blocks)],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"mke2fs failed: {proc.stderr}")
    return image_path


def run(cmd, cwd=REPO, env=None, timeout=300):
    merged = dict(os.environ)
    if env:
        merged.update(env)
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                          env=merged, timeout=timeout)


def run_tool(name, args, **kwargs):
    """Run one of this repository's tools/ scripts with the current python."""
    return run([sys.executable, os.path.join(TOOLS, name), *args], **kwargs)
