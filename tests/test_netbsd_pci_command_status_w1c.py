#!/usr/bin/env python3
"""NetBSD-only PCI command/status W1C regression; no C compile or hardware I/O.

Frozen authority: NetBSD/src@03d918f6d0e81fa05b8f1160eca0628ad39988a6
  sys/dev/pci/pcireg.h: PCI_COMMAND_MASK=0xffff, PCI_STATUS_SHIFT=16.
Linux reference: rtlwifi/pci.c at
  torvalds/linux@fd179f8a05be3ccae366b9b96e176b51fbe54aab calls
  pci_enable_device() and pci_set_master(); NetBSD native code owns RMW.

This source and command-bit model test does not establish physical panic cause,
PCI driver attach success, NetBSD kernel object compilation, or WLAN operation.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import re

NETBSD_PIN = "03d918f6d0e81fa05b8f1160eca0628ad39988a6"
SRC = Path(__file__).resolve().parents[1] / "src/rtwn8723be_netbsd.c"
PCI_COMMAND_MASK = 0xffff
PCI_STATUS_SHIFT = 16

def function(text: str, name: str) -> str:
    matches = list(re.finditer(r"(?m)^" + re.escape(name) + r"\(void \*arg\)\s*\{", text))
    assert len(matches) == 1, f"wrong function count for {name}: {len(matches)}"
    start = matches[0].start()
    end = matches[0].end()
    depth = 1
    while depth:
        assert end < len(text), "unterminated function " + name
        if text[end] == "{": depth += 1
        elif text[end] == "}": depth -= 1
        end += 1
    return text[start:end]

def emitted(current: int, enable: int) -> int:
    # pci_conf_write receives the 32-bit value; upper status bits are zero.
    return (current & PCI_COMMAND_MASK) | enable

def peripheral_after_write(current: int, written: int) -> int:
    # The test models the generic W1C status behavior, not physical RTL HW.
    old_command = current & PCI_COMMAND_MASK
    old_status = current >> PCI_STATUS_SHIFT
    new_command = written & PCI_COMMAND_MASK
    new_status = old_status & ~(written >> PCI_STATUS_SHIFT)
    assert old_command <= PCI_COMMAND_MASK
    return (new_status << PCI_STATUS_SHIFT) | new_command

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pcireg-header", type=Path)
    args = parser.parse_args()
    if args.pcireg_header is not None:
        text = args.pcireg_header.read_text()
        for symbol, number in (("PCI_COMMAND_MASK", "0xffff"),
                               ("PCI_STATUS_SHIFT", "16")):
            assert re.search(r"(?m)^#define\s+" + symbol +
                             r"\s+" + number + r"(?:\s|$)", text), symbol
    src = SRC.read_text()
    cases = {
        "rtwn8723be_netbsd_pci_enable":
            "PCI_COMMAND_IO_ENABLE | PCI_COMMAND_MEM_ENABLE",
        "rtwn8723be_netbsd_pci_set_master":
            "PCI_COMMAND_MASTER_ENABLE",
    }
    for name, expr in cases.items():
        body = function(src, name)
        assert "PCI_COMMAND_STATUS_REG) & PCI_COMMAND_MASK;" in body, name
        # Match actual PCI operations, not their explanatory comment text.
        assert body.count("pci_conf_read(") == 1, name
        assert body.count("pci_conf_write(") == 1, name
        assert body.count("PCI_COMMAND_STATUS_REG,") == 1, name
        assert "command |= " + expr + ";" in body, name
        assert ("pci_conf_write(sc->sc_pc, sc->sc_tag, PCI_COMMAND_STATUS_REG,"
                in body), name
        assert re.search(r"(?s)command = pci_conf_read\(.*?"
                         r"PCI_COMMAND_STATUS_REG\) & PCI_COMMAND_MASK;"
                         r".*?command \|= " + re.escape(expr) +
                         r";.*?pci_conf_write\(.*?command\);", body), name

    # Demonstrate that no status write-one-to-clear flags are acknowledged.
    combinations = (0x0000, 0xffff, 0x0100, 0x2000, 0x8000)
    commands = (0x0000, 0x0007, 0x0002, 0x0080, 0xffff)
    masks = (0x0003, 0x0004)
    cases_run = 0
    for status in combinations:
        for command in commands:
            for bits in masks:
                current = (status << 16) | command
                written = emitted(current, bits)
                assert written >> 16 == 0
                final = peripheral_after_write(current, written)
                assert final >> 16 == status
                assert final & PCI_COMMAND_MASK == (command | bits)
                cases_run += 1
    # Negative control: old source copied high status bits into write and
    # thus acknowledges modeled status bits instead of leaving them alone.
    old = (0xa400 << 16) | 0x0010
    bad = peripheral_after_write(old, old | 0x0004)
    assert (bad >> 16) != (old >> 16)
    print("NETBSD_PCI_COMMAND_STATUS_W1C_SOURCE_AND_MODEL_PASS", cases_run)

if __name__ == "__main__":
    main()
