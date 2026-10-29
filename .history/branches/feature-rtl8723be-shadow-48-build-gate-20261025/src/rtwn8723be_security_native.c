/* SPDX-License-Identifier: GPL-2.0
 * Frozen Linux fd179f8a rtl8723be_enable_hw_security_config(), including
 * HW_VAR_WPA_CONFIG -> byte write to REG_SECCFG. Software encryption is
 * an explicit OS policy, not a fallback for missing hardware key methods.
 * This configures the cipher engine; CAM key ownership remains separate.
 */
#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");
#include <sys/param.h>
#include <sys/systm.h>
#include <sys/errno.h>
#include "rtwn8723be_netbsd.h"
#include "rtwn8723be_security_native.h"

static bool
rtwn8723be_security_native_ready(const struct rtwn8723be_softc *sc)
{
    return sc != NULL && sc->sc_mapped && sc->sc_core_initialized &&
        sc->sc_bb_valid && sc->sc_rf_chnlval_valid &&
        sc->sc_efuse_autoload_ok && sc->sc_package_valid &&
        sc->sc_phy_identity_valid && sc->sc_phy_identity.pci_interface &&
        sc->sc_phy_identity.package_type == sc->sc_package_type &&
        sc->sc_mapsize >= 0x680U + sizeof(uint8_t) &&
        sc->sc_security_policy_valid && sc->sc_linux.mac_func_enable &&
        sc->sc_linux.fw_ready && sc->sc_linux.being_init_adapter &&
        sc->sc_linux.stage == R23BE_STAGE_SECURITY &&
        !sc->sc_linux.started && !sc->sc_irq_enabled;
}

int
rtwn8723be_netbsd_enable_hw_security(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    uint8_t security;

    if (sc == NULL)
        return EINVAL;
    sc->sc_security_configured = false;
    sc->sc_hw_security_enabled = false;
    if (!rtwn8723be_security_native_ready(sc))
        return ENXIO;
    /* Exact Linux software-crypto policy: no cipher-engine register writes. */
    if (sc->sc_sw_crypto || sc->sc_use_sw_sec) {
        sc->sc_security_configured = true;
        return 0;
    }
    /* SCR_TXENCENABLE | SCR_RXDECENABLE | SCR_TXBCUSEDK | SCR_RXBCUSEDK. */
    security = (1U << 2) | (1U << 3) | (1U << 6) | (1U << 7);
    if (sc->sc_use_defaultkey)
        security |= (1U << 0) | (1U << 1);
    rtwn8723be_write_1(sc, 0x100U + 1, 0x02);
    rtwn8723be_write_1(sc, 0x680, security);
    sc->sc_hw_security_enabled = true;
    sc->sc_security_configured = true;
    return 0;
}
