#!/usr/bin/env python3
"""Actual portable DM initializer versus frozen Linux functions.

Strict C11/UBSan and executed mutations cover logical state and fallible I/O.
Kernel primitives, hardware, watchdog execution and radio operation are separate.
"""
from pathlib import Path
import hashlib
import json
import os
import platform
import re
import resource
import socket
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
WORK = Path(os.environ["RTWN8723BE_HP_WORKDIR"]).resolve(strict=True)
LINUX = Path(os.environ["RTWN8723BE_LINUX_TREE"]).resolve(strict=True)
PIN = "fd179f8a05be3ccae366b9b96e176b51fbe54aab"
PREFIX = "drivers/net/wireless/realtek/rtlwifi/"
if platform.system() != "NetBSD" or not socket.gethostname().startswith("hp-tpnw121"):
    raise SystemExit("REFUSED: compilation is authorized only on HP/NetBSD")
if WORK.name != "fixture-tmp" or WORK.parent.parent != ROOT.parent / "audit":
    raise SystemExit("REFUSED: declare the project audit fixture-tmp workspace")
if Path.cwd().resolve() != WORK or Path(os.environ["TMPDIR"]).resolve() != WORK:
    raise SystemExit("REFUSED: cwd and TMPDIR must equal the fixture workspace")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
assert subprocess.check_output(
    ["git", "--no-optional-locks", "-C", str(LINUX), "rev-parse", "HEAD"],
    text=True).strip() == PIN
FROZEN = ("core.c", "core.h", "wifi.h", "rtl8723be/dm.c", "rtl8723be/dm.h",
          "rtl8723be/reg.h", "rtl8723be/sw.c", "rtl8723com/dm_common.c")
refs = {p: subprocess.check_output(
    ["git", "--no-optional-locks", "-C", str(LINUX), "show", PIN + ":" + PREFIX + p],
    text=True) for p in FROZEN}

def function(source, name):
    match = re.search(r"^(?:static\s+)?(?:void|int|bool)\s+" +
                      re.escape(name) + r"\s*\(", source, re.M)
    assert match, name
    opening = source.index("{", match.start())
    depth = 0
    for i in range(opening, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():i + 1]
    raise AssertionError(name)

# The oracle uses the raw pinned function equations, with explicit type/storage
# adaptation only. It does not derive expected assignments from production C.
names = [
    ("core.c", "rtl_dm_diginit"),
    ("rtl8723be/dm.c", "rtl8723be_dm_init_rate_adaptive_mask"),
    ("rtl8723com/dm_common.c", "rtl8723_dm_init_edca_turbo"),
    ("rtl8723com/dm_common.c", "rtl8723_dm_init_dynamic_bb_powersaving"),
    ("rtl8723com/dm_common.c", "rtl8723_dm_init_dynamic_txpower"),
    ("rtl8723be/dm.c", "rtl8723be_dm_init_txpower_tracking"),
    ("rtl8723be/dm.c", "rtl8723be_dm_init_dynamic_atc_switch"),
    ("rtl8723be/dm.c", "rtl8723be_dm_init"),
]
raw = "\n\n".join(function(refs[p], n) for p, n in names)
header = (ROOT / "src/rtwn8723be_dm.h").read_text()
thermal = (ROOT / "src/rtwn8723be_thermal.h").read_text()
def struct_body(text, name):
    return re.search(r"struct\s+" + name + r"\s*\{([\s\S]*?)\n\};", text)[1]
def fields(text, name):
    body = re.sub(r"/\*[\s\S]*?\*/", "", struct_body(text, name))
    result = []
    for kind, declarators in re.findall(
            r"\b(bool|u?int(?:8|16|32|64)_t|long|int)\s+([^;]+);", body):
        for item in declarators.split(","):
            m = re.fullmatch(r"\s*(\w+)(\[[^\]]+\])?\s*", item)
            assert m, item
            result.append((kind, m[1], bool(m[2])))
    return result
thermal_fields = fields(thermal, "rtwn8723be_thermal_state")
for _, name, _ in thermal_fields:
    raw = re.sub(r"\brtlpriv->dm\." + name + r"\b",
                 "rtlpriv->dm.thermal." + name, raw)
raw = raw.replace("&rtlpriv->dm_digtable", "&rtlpriv->dm.dig")
raw = raw.replace("&rtlpriv->ra", "&rtlpriv->dm.ra")
raw = raw.replace("&rtlpriv->dm_pstable", "&rtlpriv->dm.powersaving")
raw = raw.replace("rtlpriv->efuse.crystalcap", "hw->crystalcap")

constant_names = (
    "DIG_EXT_PORT_STAGE_MAX DIG_STA_DISCONNECT DIG_MULTISTA_DISCONNECT "
    "DM_DIG_THRESH_LOW DM_DIG_THRESH_HIGH DM_FALSEALARM_THRESH_LOW "
    "DM_FALSEALARM_THRESH_HIGH DM_DIG_MAX DM_DIG_MIN DM_DIG_BACKOFF_DEFAULT "
    "DM_DIG_BACKOFF_MAX DM_DIG_BACKOFF_MIN CCK_PD_STAGE_MAX CCK_PD_STAGE_LOWRSSI "
    "DM_TYPE_BYDRIVER DM_RATR_STA_INIT CCA_MAX RF_MAX TXHIGHPWRLEVEL_NORMAL "
    "CFO_THRESHOLD_XTAL ROFDM0_XAAGCCORE1 ROFDM1_CFOTRACKING RF90_PATH_A").split()
definitions, seen = [], set()
texts = [refs[p] for p in FROZEN]
for name in constant_names:
    found = False
    for text in texts:
        m = re.search(r"^#define\s+" + name + r"\s+([^\n]+)", text, re.M)
        if m:
            definition = "#define " + name + " " + m[1]
            if definition not in seen:
                definitions.append(definition)
                seen.add(definition)
            found = True
            break
    if not found:
        for text in texts:
            for enum in re.findall(r"enum\s+\w*\s*\{[\s\S]*?\};", text):
                if re.search(r"\b" + name + r"\b", enum):
                    if enum not in seen:
                        definitions.append(enum)
                        seen.add(enum)
                    found = True
                    break
            if found:
                break
    assert found, "missing frozen constant " + name

seed = ["static void seed(struct rtwn8723be_dm_state *s) {",
        "memset(s,0,sizeof(*s));"]
for text, typ, prefix in [
        (header, "rtwn8723be_dm_dig", "dig."),
        (header, "rtwn8723be_dm_rate_adaptive", "ra."),
        (header, "rtwn8723be_dm_powersaving", "powersaving."),
        (thermal, "rtwn8723be_thermal_state", "thermal."),
        (header, "rtwn8723be_dm_state", "")]:
    for kind, name, array in fields(text, typ):
        value = "true" if kind == "bool" else "-3" if kind.startswith("int8") else "53"
        member = "s->" + prefix + name
        if array:
            seed.append("for(size_t i=0;i<sizeof(" + member + ")/sizeof(" +
                        member + "[0]);i++) " + member + "[i]=" + value + ";")
        else:
            seed.append(member + "=" + value + ";")
seed.append("}")
preamble = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "rtwn8723be_dm.h"
typedef uint8_t u8;
typedef uint32_t u32;
#define BIT(n) (UINT32_C(1) << (n))
#define dig_t rtwn8723be_dm_dig
#define rate_adaptive rtwn8723be_dm_rate_adaptive
#define ps_t rtwn8723be_dm_powersaving
#define rtl_dbg(...) ((void)0)
struct rtl_priv { struct rtwn8723be_dm_state dm; };
struct ieee80211_hw {
    struct rtl_priv priv;
    uint8_t crystalcap;
    uint32_t agc,atc;
    unsigned reads;
};
static struct rtl_priv *rtl_priv(struct ieee80211_hw *hw) { return &hw->priv; }
"""
oracle_io = r"""
static u32 rtl_get_bbreg(struct ieee80211_hw *hw,u32 reg,u32 mask) {
    hw->reads++;
    if(reg==ROFDM0_XAAGCCORE1) { assert(mask==0x7f);return hw->agc; }
    assert(reg==ROFDM1_CFOTRACKING && mask==0x800);
    return hw->atc;
}
"""
harness = r"""
struct ioenv {
    bool leased;
    unsigned ready_calls,reads,revoke_at,fail_read,no_output;
    uint32_t agc,atc;
};
static bool ready(void *arg) {
    struct ioenv *e=arg;
    e->ready_calls++;
    return e->leased && e->ready_calls!=e->revoke_at;
}
static int read_bb(void *arg,uint32_t reg,uint32_t mask,uint32_t *out) {
    struct ioenv *e=arg;
    assert(e->leased && out);
    e->reads++;
    if(e->reads==e->fail_read) return EIO;
    if(e->reads==e->no_output) return 0;
    if(e->reads==1) {
        assert(reg==R23BE_DM_AGC_REG && mask==R23BE_DM_AGC_MASK);
        *out=e->agc;
    } else {
        assert(e->reads==2 && reg==R23BE_DM_ATC_REG && mask==R23BE_DM_ATC_MASK);
        *out=e->atc;
    }
    return 0;
}
static const struct rtwn8723be_dm_io io={ready,read_bb};
static struct ioenv fresh(void) {
    struct ioenv e={.leased=true,.agc=0x32,.atc=1};
    return e;
}
static void unchanged(struct rtwn8723be_dm_state *s,struct ioenv *e,int error) {
    struct rtwn8723be_dm_state old=*s;
    assert(rtwn8723be_dm_init(s,&io,e,0x20)==error);
    assert(memcmp(s,&old,sizeof(old))==0);
}
int main(void) {
    struct rtwn8723be_dm_state state,expected,old;
    struct ioenv e;
    struct rtwn8723be_dm_io broken=io;
    unsigned cases=0;
    seed(&state);
    rtwn8723be_dm_construct(&state);
    memset(&expected,0,sizeof(expected));expected.dm_initialgain_enable=true;
    assert(memcmp(&state,&expected,sizeof(state))==0);
    rtwn8723be_dm_construct(NULL);
    assert(R23BE_DM_AGC_REG==ROFDM0_XAAGCCORE1);
    assert(R23BE_DM_ATC_REG==ROFDM1_CFOTRACKING);
    for(unsigned agc=0;agc<=127;agc++) for(unsigned atc=0;atc<2;atc++)
    for(unsigned cap=0;cap<3;cap++) {
        struct ieee80211_hw hw;
        seed(&state);memset(&hw,0,sizeof(hw));hw.priv.dm=state;
        hw.agc=agc;hw.atc=atc;hw.crystalcap=(uint8_t)(cap==0?0:cap==1?32:63);
        e=fresh();e.agc=agc;e.atc=atc;
        rtl8723be_dm_init(&hw);
        assert(rtwn8723be_dm_init(&state,&io,&e,hw.crystalcap)==0);
        assert(hw.reads==2 && e.reads==2 && e.ready_calls==3);
        assert(memcmp(&state,&hw.priv.dm,sizeof(state))==0);
        cases++;
    }
    seed(&state);old=state;e=fresh();
    assert(rtwn8723be_dm_init(NULL,&io,&e,0)==EINVAL);
    assert(rtwn8723be_dm_init(&state,NULL,&e,0)==EINVAL);
    broken.ready=NULL;assert(rtwn8723be_dm_init(&state,&broken,&e,0)==ENOSYS);
    broken=io;broken.read_bb=NULL;
    assert(rtwn8723be_dm_init(&state,&broken,&e,0)==ENOSYS);
    assert(rtwn8723be_dm_init(&state,&io,&e,64)==EINVAL && e.reads==0);
    assert(memcmp(&state,&old,sizeof(state))==0);
    for(unsigned i=1;i<=3;i++) {e=fresh();e.revoke_at=i;unchanged(&state,&e,ENXIO);}
    for(unsigned i=1;i<=2;i++) {e=fresh();e.fail_read=i;unchanged(&state,&e,EIO);}
    for(unsigned i=1;i<=2;i++) {e=fresh();e.no_output=i;unchanged(&state,&e,EINVAL);}
    e=fresh();e.agc=128;unchanged(&state,&e,EINVAL);
    e=fresh();e.atc=2;unchanged(&state,&e,EINVAL);
    e=fresh();e.leased=false;unchanged(&state,&e,ENXIO);assert(e.reads==0);
    printf("DM_DIFFERENTIAL_CASES=%u FAILURE_CASES=15\n",cases);
    return 0;
}
"""
# Cold defaults are tied to the genuine sw_vars producer, not a fabricated
# per-start constructor. The raw initializer above preserves unassigned history.
sw = function(refs["rtl8723be/sw.c"], "rtl8723be_init_sw_vars")
assert re.search(r"dm\.dm_initialgain_enable\s*=\s*true", sw)
assert re.search(r"dm\.disable_framebursting\s*=\s*false", sw)
program = preamble + "\n".join(definitions) + "\n" + oracle_io + raw + "\n"
program += "\n".join(seed) + "\n" + harness
source = (ROOT / "src/rtwn8723be_dm.c").read_text()
mutations = [
    ("cold-not-zero", "memset(state, 0, sizeof(*state));", "(void)state;"),
    ("warm-history-erased", "next = *state;", "memset(&next, 0, sizeof(next));"),
    ("DIG-similar-wrong-field", "dig->cur_sta_cstate = R23BE_DM_DIG_STA_DISCONNECT;",
     "dig->cursta_cstate = R23BE_DM_DIG_STA_DISCONNECT;"),
    ("DIG-signed-backoff", "dig->back_range_min = -4;", "dig->back_range_min = 4;"),
    ("RA-threshold", "state->ra.high_rssi_thresh_for_ra = 50;",
     "state->ra.high_rssi_thresh_for_ra = 49;"),
    ("EDCA-reset-omitted", "dm_edca_init(&next);",
     "if (next.dm_type == UINT8_MAX) dm_edca_init(&next);"),
    ("thermal-init-omitted", "rtwn8723be_thermal_txpower_init(&next.thermal);",
     "(void)next.thermal;"),
    ("AGC-bounds-ignored", "if (current_igi > R23BE_DM_AGC_MASK)", "if (current_igi == 999U)"),
    ("ATC-bounds-ignored", "if (atc > 1U)", "if (atc == 999U)"),
    ("final-ready-ignored",
     "if (!io->ready(arg))\n        return ENXIO;\n\n    *state = next;",
     "if (false && !io->ready(arg))\n        return ENXIO;\n\n    *state = next;"),
    ("early-publication",
     "if (!io->ready(arg))\n        return ENXIO;\n\n    *state = next;",
     "*state = next;\n    if (!io->ready(arg))\n        return ENXIO;"),
    ("ATC-wrong-value", "next.atc_status = atc != 0;", "next.atc_status = atc == 0;"),
]
proof = {"result": "RUNNING", "linux_pin": PIN, "cases": [], "mutants": [],
         "scope": "Actual portable DM/thermal/calibration C; raw frozen function oracle with explicit logical storage adaptation.",
         "physical": "NOT_RUN"}
with tempfile.TemporaryDirectory(prefix="dm-proof-", dir=WORK) as name:
    temp = Path(name)
    (temp / "main.c").write_text(program)
    def execute(label, body, mutant=False):
        unit = temp / (label + ".c")
        unit.write_text(body)
        exe = temp / label
        command = ["/usr/bin/cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                   "-pedantic", "-Wno-unused-parameter", "-fsanitize=undefined",
                   "-fno-sanitize-recover=all", "-I", str(ROOT / "src"),
                   str(temp / "main.c"), str(unit),
                   str(ROOT / "src/rtwn8723be_thermal.c"),
                   str(ROOT / "src/rtwn8723be_calibration.c"), "-o", str(exe)]
        compiled = subprocess.run(command, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=180)
        (WORK / ("dm-" + label + "-compile.log")).write_text(compiled.stdout)
        assert compiled.returncode == 0, (label, "compile", compiled.stdout)
        run = subprocess.run([str(exe)], cwd=WORK, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=90)
        (WORK / ("dm-" + label + "-run.log")).write_text(run.stdout)
        if mutant:
            assert run.returncode != 0 and "assert" in run.stdout.lower(), (label, run.returncode, run.stdout)
            proof["mutants"].append({"name": label, "compile_exit": 0, "run_exit": run.returncode})
        else:
            assert run.returncode == 0, (label, run.returncode, run.stdout)
            proof["cases"].append({"name": label, "compile_exit": 0, "run_exit": 0, "stdout": run.stdout})
    execute("baseline", source)
    for label, before, after in mutations:
        assert source.count(before) == 1, label
        execute(label, source.replace(before, after), True)
proof.update(result="PASS", mutants_executed=len(mutations),
             frozen_sha256={PREFIX+p: hashlib.sha256(s.encode()).hexdigest() for p,s in refs.items()},
             source_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in [ROOT/"src/rtwn8723be_dm.c", ROOT/"src/rtwn8723be_dm.h",
                                      ROOT/"src/rtwn8723be_thermal.c", ROOT/"src/rtwn8723be_thermal.h",
                                      ROOT/"src/rtwn8723be_calibration.c", Path(__file__)]})
receipt = WORK / "dm-proof.json"
receipt.write_text(json.dumps(proof, sort_keys=True, indent=2)+"\n")
print("DM_PASS mutants_executed=" + str(len(mutations)), receipt)
