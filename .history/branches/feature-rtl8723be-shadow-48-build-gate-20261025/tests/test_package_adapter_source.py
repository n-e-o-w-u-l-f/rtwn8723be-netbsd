#!/usr/bin/env python3
"""Source-contract check for the real NetBSD physical-EFUSE package adapter.

This checks source integration, NOT native NetBSD compilation or MMIO behavior.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "src/rtwn8723be_netbsd.c").read_text()
HDR = (ROOT / "src/rtwn8723be_netbsd.h").read_text()
PACKAGE = (ROOT / "src/rtwn8723be_package.h").read_text()


def body(name: str, stop: str) -> str:
    start = SRC.index(name)
    return SRC[start:SRC.index(stop, start)]


def main() -> None:
    raw = body("rtwn8723be_netbsd_efuse_read_1(",
               "rtwn8723be_netbsd_package_power(")
    assert "addr != RTWN8723BE_PACKAGE_EFUSE_ADDRESS" in raw
    assert "addr >= R23BE_EFUSE_REAL_CONTENT_LEN" in raw
    assert "((addr >> 8) & 0x03)" in raw
    assert "retry < 10000" in raw
    assert "return ETIMEDOUT;" in raw
    assert "#define RTWN8723BE_PACKAGE_EFUSE_ADDRESS 0x01fbU" in PACKAGE

    power = body("rtwn8723be_netbsd_package_power(",
                 "rtwn8723be_netbsd_package_read_byte(")
    read = body("rtwn8723be_netbsd_package_read_byte(",
                "rtwn8723be_netbsd_efuse_shadow_read(")
    assert "if (!sc->sc_mapped)" in power
    assert "rtwn8723be_netbsd_efuse_power(sc, on);" in power
    assert "if (!sc->sc_mapped)" in read
    assert "rtwn8723be_netbsd_efuse_read_1(sc, addr, value)" in read

    shadow = body("rtwn8723be_netbsd_efuse_shadow_read(",
                  "rtwn8723be_netbsd_read_eeprom_info(")
    assert "while (addr < R23BE_EFUSE_REAL_CONTENT_LEN)" in shadow
    assert "rtwn8723be_netbsd_efuse_power(sc, false);" in shadow

    eeprom = body("rtwn8723be_netbsd_read_eeprom_info(",
                  "rtwn8723be_netbsd_init_sw_vars(")
    checks = (
        "sc->sc_package_valid = false;",
        "sc->sc_package_type = RTWN8723BE_PACKAGE_DEFAULT;",
        "if (!sc->sc_mapped)",
        "sc->sc_eeprom_id != R23BE_EEPROM_ID",
        "sc->sc_bt_ant_valid = true;",
        "error = rtwn8723be_package_read(",
        "if (error != 0)",
        "sc->sc_package_valid = true;",
    )
    positions = [eeprom.index(term) for term in checks[:-3]]
    package_call = eeprom.index(checks[-3])
    package_error = eeprom.index(checks[-2], package_call)
    published = eeprom.index(checks[-1], package_error)
    positions.extend((package_call, package_error, published))
    assert positions == sorted(positions), "physical EFUSE identity order"
    assert "uint8_t sc_package_type;" in HDR
    assert "bool sc_package_valid;" in HDR
    print("RTL_PACKAGE_NETBSD_SOURCE_CONTRACT_OK")
    print("LIMITATION: source inspection, not a native NetBSD build")


if __name__ == "__main__":
    main()
