#!/usr/bin/env python3
"""
elf.py - dependency-free ELF reader for the sakura extraction/verification chain.

Only the fields this project actually needs are parsed:

  * ELF class (32/64) and machine, so a blob extracted from the wrong firmware
    (Mi A2 Lite / daisy is ARM too, but an x86 or 32-bit library is a hard
    error) is rejected before it can be packed into a recovery ramdisk;
  * PT_INTERP, so a service binary whose interpreter would not exist in the
    ramdisk is caught;
  * DT_NEEDED + DT_SONAME, so every runtime library dependency can be resolved
    against the files that will actually be in the ramdisk.

The parser is deliberately tolerant: a file that is a valid ELF but has no
dynamic section (static binary) is not an error.

CLI:
  python3 tools/elf.py <file> [<file> ...]
"""

from __future__ import annotations

import struct
import sys

EM_ARM = 40
EM_AARCH64 = 183
EM_386 = 3
EM_X86_64 = 62

MACHINE_NAMES = {
    EM_ARM: "ARM",
    EM_AARCH64: "AArch64",
    EM_386: "x86",
    EM_X86_64: "x86-64",
}

# Program header types
PT_LOAD = 1
PT_DYNAMIC = 2
PT_INTERP = 3

# Dynamic tags
DT_NULL = 0
DT_NEEDED = 1
DT_STRTAB = 5
DT_STRSZ = 10
DT_SONAME = 14


class ElfError(Exception):
    pass


class Elf:
    """Minimal ELF view: class, machine, interpreter, needed[], soname."""

    def __init__(self, path):
        self.path = path
        with open(path, "rb") as fh:
            self.data = fh.read()
        self._parse()

    # -- header ---------------------------------------------------------
    def _parse(self):
        data = self.data
        if len(data) < 52 or data[:4] != b"\x7fELF":
            raise ElfError(f"{self.path}: not an ELF file")

        ei_class = data[4]
        ei_data = data[5]
        if ei_class not in (1, 2):
            raise ElfError(f"{self.path}: unknown EI_CLASS {ei_class}")
        if ei_data not in (1, 2):
            raise ElfError(f"{self.path}: unknown EI_DATA {ei_data}")

        self.is64 = ei_class == 2
        self.endian = "<" if ei_data == 1 else ">"
        e = self.endian

        try:
            if self.is64:
                (self.e_type, self.machine, _version, _entry, phoff, _shoff,
                 _flags, _ehsize, phentsize, phnum, _shentsize, _shnum,
                 _shstrndx) = struct.unpack_from(e + "HHIQQQIHHHHHH", data, 16)
            else:
                (self.e_type, self.machine, _version, _entry, phoff, _shoff,
                 _flags, _ehsize, phentsize, phnum, _shentsize, _shnum,
                 _shstrndx) = struct.unpack_from(e + "HHIIIIIHHHHHH", data, 16)
        except struct.error as exc:
            raise ElfError(f"{self.path}: truncated ELF header ({exc})") from exc

        self.machine_name = MACHINE_NAMES.get(self.machine, f"e_machine={self.machine}")
        self.bits = 64 if self.is64 else 32
        self.interp = None
        self.needed = []
        self.soname = None

        segments = []
        if phoff and phnum:
            for i in range(phnum):
                off = phoff + i * phentsize
                if self.is64:
                    if off + 56 > len(data):
                        break
                    p_type, _p_flags, p_offset, p_vaddr, _p_paddr, p_filesz, \
                        _p_memsz, _p_align = struct.unpack_from(e + "IIQQQQQQ", data, off)
                else:
                    if off + 32 > len(data):
                        break
                    p_type, p_offset, p_vaddr, _p_paddr, p_filesz, _p_memsz, \
                        _p_flags, _p_align = struct.unpack_from(e + "IIIIIIII", data, off)
                segments.append((p_type, p_offset, p_vaddr, p_filesz))
                if p_type == PT_INTERP and p_filesz:
                    raw = data[p_offset:p_offset + p_filesz]
                    self.interp = raw.split(b"\x00", 1)[0].decode("utf-8", "replace")

        dyn = next((s for s in segments if s[0] == PT_DYNAMIC), None)
        if dyn is None:
            return
        _t, dyn_off, _vaddr, dyn_size = dyn
        entsize = 16 if self.is64 else 8
        entries = []
        for off in range(dyn_off, dyn_off + dyn_size - entsize + 1, entsize):
            if off + entsize > len(data):
                break
            if self.is64:
                d_tag, d_val = struct.unpack_from(e + "qQ", data, off)
            else:
                d_tag, d_val = struct.unpack_from(e + "iI", data, off)
            if d_tag == DT_NULL:
                break
            entries.append((d_tag, d_val))

        strtab_vaddr = None
        strtab_size = 0
        for tag, val in entries:
            if tag == DT_STRTAB:
                strtab_vaddr = val
            elif tag == DT_STRSZ:
                strtab_size = val
        if strtab_vaddr is None:
            return

        strtab_off = None
        for p_type, p_offset, p_vaddr, p_filesz in segments:
            if p_type == PT_LOAD and p_vaddr <= strtab_vaddr < p_vaddr + p_filesz:
                strtab_off = p_offset + (strtab_vaddr - p_vaddr)
                break
        if strtab_off is None:
            return
        strtab = data[strtab_off:strtab_off + (strtab_size or 0)] if strtab_size \
            else data[strtab_off:]

        def cstr(idx):
            if idx >= len(strtab):
                return None
            end = strtab.find(b"\x00", idx)
            if end < 0:
                end = len(strtab)
            return strtab[idx:end].decode("utf-8", "replace")

        for tag, val in entries:
            if tag == DT_NEEDED:
                name = cstr(val)
                if name:
                    self.needed.append(name)
            elif tag == DT_SONAME:
                self.soname = cstr(val)

    # -- helpers --------------------------------------------------------
    @property
    def is_dynamic(self):
        return bool(self.needed) or bool(self.interp)

    def summary(self):
        bits = f"{self.bits}-bit {self.machine_name}"
        interp = self.interp or "(static)"
        return f"{bits}, interp {interp}, {len(self.needed)} DT_NEEDED"


def inspect(path):
    try:
        return Elf(path)
    except (OSError, ElfError) as exc:
        raise ElfError(str(exc)) from exc


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for path in argv[1:]:
        try:
            elf = inspect(path)
        except ElfError as exc:
            print(f"FAIL {exc}")
            rc = 1
            continue
        print(f"{path}: {elf.summary()}")
        if elf.soname:
            print(f"    soname: {elf.soname}")
        for need in elf.needed:
            print(f"    needs : {need}")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
