#!/usr/bin/env python3
"""Compile exact production RX-binding functions with mock NetBSD structures.

Tests shared frame/C2H dispatch context and fail-closed callback preflight;
not a native kernel compile, hardware test, or IRQ concurrency proof.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
src = (ROOT / "src/rtwn8723be_rx_binding.c").read_text()

def function(anchor):
    marker = "\n" + anchor + "("
    if src.count(marker) != 1:
        raise AssertionError("production binding function missing: " + anchor)
    body = anchor + "(" + src.split(marker, 1)[1]
    start, depth = body.index("{"), 0
    for index in range(start, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                return body[:index+1]
    raise AssertionError("unbalanced binding function")

extracted = "\n".join([
    "static int\n" + function("rtwn8723be_rx_binding_frame"),
    "static int\n" + function("rtwn8723be_rx_binding_c2h"),
    "int\n" + function("rtwn8723be_rx_binding_init"),
])
prologue = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <errno.h>
#include <string.h>
#include "rtwn8723be_c2h.h"
struct rtwn8723be_softc { bool sc_btcoexist; };
struct rtwn8723be_net80211 {
    struct rtwn8723be_softc *sc;
    bool registered;
};
struct rtwn8723be_rx_packet { int kind; };
struct rtwn8723be_rx_dispatch {
    void *arg;
    int (*frame)(void *, const uint8_t *, size_t,
        const struct rtwn8723be_rx_packet *);
    int (*c2h)(void *, const uint8_t *, size_t,
        const struct rtwn8723be_rx_packet *);
};
struct rtwn8723be_rx_binding {
    struct rtwn8723be_net80211 *net;
    struct rtwn8723be_c2h_handlers firmware;
    struct rtwn8723be_rx_dispatch dispatch;
};
static int frame_calls, c2h_calls;
static int rtwn8723be_net80211_rx_frame(void *n, const uint8_t *data,
    size_t len, const struct rtwn8723be_rx_packet *p)
{
    assert(n && data && len && p);
    frame_calls++;
    return 0;
}
static int rtwn8723be_c2h_native_receive(
    const struct rtwn8723be_c2h_handlers *h,
    const uint8_t *data, size_t len, const struct rtwn8723be_rx_packet *p)
{
    assert(h && data && len && p);
    c2h_calls++;
    return 0;
}
"""
epilogue = r"""
static int on_event(void *arg, const struct rtwn8723be_c2h_event *ev)
{ (void)arg; (void)ev; return 0; }
int main(void)
{
    struct rtwn8723be_rx_binding b = {0};
    struct rtwn8723be_softc sc = {0};
    struct rtwn8723be_net80211 n = {.sc=&sc, .registered=true};
    struct rtwn8723be_c2h_handlers h = {
        .tx_report=on_event, .ra_report=on_event
    };
    struct rtwn8723be_rx_packet p = {0};
    uint8_t bytes[3] = {0};

    assert(rtwn8723be_rx_binding_init(&b, &n, &h) == 0);
    assert(b.dispatch.arg == &b && b.dispatch.frame && b.dispatch.c2h);
    assert(b.dispatch.frame(b.dispatch.arg, bytes, sizeof(bytes), &p) == 0);
    assert(b.dispatch.c2h(b.dispatch.arg, bytes, sizeof(bytes), &p) == 0);
    assert(frame_calls == 1 && c2h_calls == 1);
    assert(rtwn8723be_rx_binding_init(&b, &n, &h) == EBUSY);
    n.registered = false;
    assert(b.dispatch.frame(b.dispatch.arg, bytes, sizeof(bytes), &p)
           == ENXIO);
    n.registered = true;
    memset(&b, 0, sizeof(b));
    h.tx_report = NULL;
    assert(rtwn8723be_rx_binding_init(&b, &n, &h) == ENOSYS);
    h.tx_report = on_event;
    sc.sc_btcoexist = true;
    assert(rtwn8723be_rx_binding_init(&b, &n, &h) == ENOSYS);
    h.bt_info = on_event;
    h.bt_mp = on_event;
    assert(rtwn8723be_rx_binding_init(&b, &n, &h) == 0);
    assert(rtwn8723be_rx_binding_init(NULL, &n, &h) == EINVAL);
    puts("RTL_RX_FRAME_C2H_SHARED_CONTEXT_C11_UBSAN_OK");
    return 0;
}
"""
with tempfile.TemporaryDirectory(prefix="rtl-rx-bind-") as name:
    p = Path(name)
    harness = p / "test.c"
    exe = p / "test"
    harness.write_text(prologue + extracted + epilogue)
    subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-pedantic",
        "-fsanitize=undefined", "-fno-sanitize-recover=all",
        "-I", str(ROOT / "src"), str(harness), "-o", str(exe)
    ], check=True)
    subprocess.run([str(exe)], check=True)
