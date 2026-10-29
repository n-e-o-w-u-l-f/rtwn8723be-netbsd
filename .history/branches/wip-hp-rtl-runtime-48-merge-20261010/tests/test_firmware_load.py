#!/usr/bin/env python3
"""Compile actual production firmware code on HP against frozen Linux bodies.

Firmware(9), MMIO and H2C/BT callbacks are explicit test models; this does not
establish kernel integration, physical hardware readiness or full-port parity.
"""
from pathlib import Path
import datetime
import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import time

if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    sys.exit("REFUSED: compiler-invoking firmware checks are HP/NetBSD only")
ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ.get("RTWN8723BE_HP_WORKDIR",
                           "/root/hp-driver-port-20261005"))
LINUX = Path(os.environ.get("RTWN8723BE_LINUX_TREE", "/root/linux-rtl8723be-ref-fresh"))
PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
PREFIX = "drivers/net/wireless/realtek/rtlwifi/"
EXPECTED = {
    "rtl8723com/fw_common.c": "50b79cf8fb3c41ab8897bfb26916e2c97c77170c",
    "efuse.c": "6518e77b89f5785a16ca69b1aac914e1ced80aaf",
    "core.c": "22633c3015642d8de221a8ab62d57ed3eec1671f",
    "rtl8723be/sw.c": "5967df08e34ecb0e1bfebb54b48cd5bf4254b054",
}
IMAGES = {
    "rtl8723befw_36.bin": "adba42ade555a5e4383373b76706443f27bf0f006fbc296a640c7155192febf2",
    "rtl8723befw.bin": "1bfa6d0910e072ed26d793ccf27889ebd774851be95d2d2543fd8de7cf31b969",
}
OUT = WORK / ("rtl-firmware-load-proof-" + str(time.time_ns()))
OUT.mkdir()
state = {"state": "RUNNING", "host": socket.gethostname(), "linux_pin": PIN,
         "started": datetime.datetime.now(datetime.timezone.utc).isoformat(),
         "commands": [], "runs": [], "frozen": {}, "images": {},
         "scope": "actual production fw.c and exact native download owner body; frozen Linux body traces under explicitly modeled firmware/MMIO/BT/H2C interfaces",
         "acceptance": "OPEN: native lifecycle/BTC/kernel link, physical WLAN and full driver port"}
def save():
    state["updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    tmp = OUT / "proof.tmp"
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT / "proof.json")
def sha(data):
    return hashlib.sha256(data).hexdigest()
def blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
def extract(source, name):
    """Keep the exact definition, skipping braces in comments and strings."""
    match = re.search(r"^(?:static\s+)?(?:void|int)\s*\n?\s*" + re.escape(name) + r"\s*\(", source, re.M)
    if match is None:
        raise RuntimeError("missing function " + name)
    start = match.start()
    opening = source.index("{", match.end())
    depth = 0
    mode = "code"
    i = opening
    while i < len(source):
        c = source[i]
        pair = source[i:i+2]
        if mode == "line":
            if c == "\n":
                mode = "code"
        elif mode == "block":
            if pair == "*/":
                mode = "code"
                i += 1
        elif mode in ('"', "'"):
            if c == "\\":
                i += 1
            elif c == mode:
                mode = "code"
        else:
            if pair == "//":
                mode = "line"
                i += 1
            elif pair == "/*":
                mode = "block"
                i += 1
            elif c in ('"', "'"):
                mode = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return source[start:i+1] + "\n"
        i += 1
    raise RuntimeError("unterminated function " + name)
def run(command, label, expected=0, tag=None):
    state["commands"].append(command)
    save()
    result = subprocess.run(command, text=True, encoding="utf-8",
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=150)
    (OUT / (label + ".log")).write_text(result.stdout, encoding="utf-8")
    state["runs"].append({"label": label, "exit": result.returncode,
                          "log_sha256": sha(result.stdout.encode())})
    save()
    if result.returncode != expected or (tag and tag not in result.stdout):
        print(result.stdout, flush=True)
        raise RuntimeError(label + " unexpected result " + str(result.returncode))
    if label.endswith("-run"):
        print(label + ": " + result.stdout.strip(), flush=True)
    return result
save()
try:
    head = subprocess.check_output(["git", "-C", str(LINUX), "rev-parse", "HEAD"], text=True).strip()
    if head != PIN:
        raise RuntimeError("Linux reference HEAD mismatch")
    source = {}
    for path, expected in EXPECTED.items():
        data = subprocess.check_output(["git", "-C", str(LINUX), "show", PIN + ":" + PREFIX + path])
        if blob(data) != expected:
            raise RuntimeError("frozen Git blob mismatch " + path)
        source[path] = data.decode("utf-8")
        state["frozen"][path] = {"git_blob": expected, "sha256": sha(data)}
    if "alt_fw_name" not in source["core.c"] or "rtl8723befw_36.bin" not in source["rtl8723be/sw.c"]:
        raise RuntimeError("missing frozen firmware selection evidence")
    for name, expected in IMAGES.items():
        image = Path("/libdata/firmware/if_rtwn8723be") / name
        data = image.read_bytes()
        if sha(data) != expected:
            raise RuntimeError("firmware image changed " + name)
        state["images"][name] = {"path": str(image), "bytes": len(data), "sha256": expected}
    pieces = []
    for name in ("rtl_fw_block_write", "rtl_fw_page_write", "rtl_fill_dummy"):
        pieces.append(extract(source["efuse.c"], name))
    for name in ("rtl8723_enable_fw_download", "rtl8723_write_fw",
                 "rtl8723be_firmware_selfreset", "rtl8723_fw_free_to_go",
                 "rtl8723_download_fw"):
        pieces.append(extract(source["rtl8723com/fw_common.c"], name))
    (OUT / "linux_reference.inc").write_text("\n".join(pieces), encoding="utf-8")
    fixture = ROOT / "compat/firmware-load"
    shutil.copyfile(fixture / "model_fixture.h", OUT / "model_fixture.h")
    mocksys = OUT / "mock/sys"
    mocksys.mkdir(parents=True)
    (mocksys / "bus.h").write_text("""#ifndef MODEL_SYS_BUS_H
#define MODEL_SYS_BUS_H
#include <stdint.h>
#include <stddef.h>
struct trace;
typedef struct trace *bus_space_tag_t;
typedef uintptr_t bus_space_handle_t;
typedef size_t bus_size_t;
uint8_t bus_space_read_1(bus_space_tag_t,bus_space_handle_t,bus_size_t);
uint32_t bus_space_read_4(bus_space_tag_t,bus_space_handle_t,bus_size_t);
void bus_space_write_1(bus_space_tag_t,bus_space_handle_t,bus_size_t,uint8_t);
void bus_space_write_4(bus_space_tag_t,bus_space_handle_t,bus_size_t,uint32_t);
#endif
""", encoding="utf-8")
    (mocksys / "systm.h").write_text("""#ifndef MODEL_SYS_SYSTM_H
#define MODEL_SYS_SYSTM_H
#include <string.h>
void delay(unsigned int);
#endif
""", encoding="utf-8")
    original = ROOT / "src/rtwn8723be_netbsd.c"
    owner = extract(original.read_text(encoding="utf-8"), "rtwn8723be_netbsd_download_firmware")
    (OUT / "current-owner-function.c").write_text(owner, encoding="utf-8")
    state["owner_function_sha256"] = sha(owner.encode())
    state["compiled_source_sha256"] = {
        str(p.relative_to(ROOT)): sha(p.read_bytes())
        for p in (ROOT / "src/rtwn8723be_fw.c", ROOT / "src/rtwn8723be_fw.h",
                  original, ROOT / "src/rtwn8723be_netbsd.h",
                  ROOT / "src/rtwn8723be_f16_1.h", fixture / "model_fixture.h",
                  ROOT / "tests/firmware_load_check.c", Path(__file__).resolve())
    }
    baseline_fw = fixture / "baseline-fw.c"
    baseline_owner = fixture / "baseline-owner-function.c"
    if blob(baseline_fw.read_bytes()) != "22d22223c6dfa62eabfd5d33cea8e2bd3f560149":
        raise RuntimeError("baseline firmware source mismatch")
    if blob(baseline_owner.read_bytes()) != "21decfaa3e0818fb9bfc815a78070fe1acda21d2":
        raise RuntimeError("baseline owner source mismatch")
    flags = ["-D_NETBSD_SOURCE", "-std=gnu11", "-O2", "-g",
             "-Wall", "-Wextra", "-Werror", "-Wshadow",
             "-I" + str(OUT / "mock"), "-I" + str(ROOT / "src"),
             "-I" + str(OUT), "-include", str(OUT / "model_fixture.h")]
    variants = (
        ("positive", [], ROOT / "src/rtwn8723be_fw.c", owner, [], 0, "FW_ACTUAL_SOURCE_REFERENCE_PASS"),
        ("ubsan", [], ROOT / "src/rtwn8723be_fw.c", owner,
         ["-fsanitize=undefined", "-fno-sanitize-recover=all"], 0, "FW_ACTUAL_SOURCE_REFERENCE_PASS"),
        ("baseline-poll", ["-DBASELINE_POLL"], baseline_fw, baseline_owner.read_text(),
         [], 77, "FW_CHECK_FAIL POLL_RESULT_PARITY"),
        ("baseline-owner", ["-DBASELINE_OWNER"], ROOT / "src/rtwn8723be_fw.c",
         baseline_owner.read_text(), [], 77, "FW_CHECK_FAIL FALLBACK_LOAD"),
    )
    for label, defines, production, body, sanitize, expected, tag in variants:
        (OUT / "native_owner.inc").write_text(body, encoding="utf-8")
        object_path = OUT / (label + "-fw.o")
        dep = OUT / (label + "-fw.d")
        run(["/usr/bin/cc", *flags, *sanitize, "-MMD", "-MF", str(dep),
             "-c", str(production), "-o", str(object_path)], label + "-production-compile")
        deptext = dep.read_text()
        if str(production) not in deptext or str(ROOT / "src/rtwn8723be_fw.h") not in deptext:
            raise RuntimeError("production compiler dependency mismatch")
        # Frozen Linux warning annotations surround only the frozen excerpt.
        # Controls also leave unrelated fixture tests unused; production flags
        # remain strict, without suppressions.
        fixture_flags = ["-Wno-unused-function"] if defines else []
        binary = OUT / label
        run(["/usr/bin/cc", *flags, *sanitize, *defines, *fixture_flags,
             str(ROOT / "tests/firmware_load_check.c"), str(object_path),
             "-o", str(binary)], label + "-fixture-compile")
        result = run([str(binary), *[state["images"][n]["path"] for n in IMAGES]],
                     label + "-run", expected, tag)
        if expected == 0:
            match = re.search(r"cases=(\d+)", result.stdout)
            if match is None or int(match.group(1)) < 113:
                raise RuntimeError("unexpected positive case count")
            state[label + "_cases"] = int(match.group(1))
    (OUT / "native_owner.inc").write_text(owner, encoding="utf-8")
    state["negative_controls"] = {
        "old_poll": "compiled old actual fw.c; semantic failure at frozen poll boundary",
        "old_owner": "compiled old actual owner; semantic failure when primary image is missing"}
    state["state"] = "PASSED"
    state["reference_error_adaptation"] = (
        "NetBSD propagates positive errno if MCU readiness fails; frozen Linux "
        "rtl8723_download_fw logs the failure but returns zero")
except Exception as exc:
    state["state"] = "FAILED"
    state["error"] = str(exc)
    save()
    print("FIRMWARE_LOAD_PROOF", OUT, flush=True)
    raise
save()
print("FIRMWARE_LOAD_PROOF", OUT, flush=True)
