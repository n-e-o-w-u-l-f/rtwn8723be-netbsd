#include <sys/cdefs.h>
__KERNEL_RCSID(0, "$NetBSD$");

#include <sys/param.h>
#include <sys/device.h>
#include <sys/systm.h>

#include <dev/pci/pcireg.h>
#include <dev/pci/pcivar.h>
#include <dev/pci/pcidevs.h>
#include <dev/firmload.h>
#include <sys/bus.h>
#include "rtwn8723be_pwrseq_plan.h"

struct rtwn8723be_softc {
    device_t sc_dev;
    pci_chipset_tag_t sc_pc;
    pcitag_t sc_tag;
    bus_space_tag_t sc_st;
    bus_space_handle_t sc_sh;
    bus_addr_t sc_base;
    bus_size_t sc_mapsize;
};

static int
rtwn8723be_match(device_t parent, cfdata_t cf, void *aux)
{
    struct pci_attach_args *pa = aux;

    if (PCI_VENDOR(pa->pa_id) != PCI_VENDOR_REALTEK)
        return 0;
    if (PCI_PRODUCT(pa->pa_id) != 0xb723)
        return 0;
    return 1;
}

static void
rtwn8723be_pwrseq_dryrun(device_t self)
{
    size_t i;
    const struct rtwn8723be_pwr_step *s;
    size_t selected = 0;
    size_t skipped = 0;

    aprint_normal_dev(self,
        "F8.4 NIC_ENABLE_FLOW dry-run: PCI interface only; NO hardware access\n");
    aprint_normal_dev(self, "F8.4 phase 1: CARDDIS->CARDEMU\n");
    for (i = 0; i < RTWN8723BE_CARDDIS_TO_CARDEMU_STEPS; i++) {
        s = &rtwn8723be_carddis_to_carde_mu[i];
        if ((s->intf_mask & RTWN8723BE_PWR_INTF_PCI) == 0) {
            skipped++;
            continue;
        }
        selected++;
        aprint_normal_dev(self,
            "F8.4 step %zu: cmd=%u offset=0x%04x mask=0x%02x value=0x%02x\n",
            selected, s->cmd, s->offset, s->mask, s->value);
    }

    aprint_normal_dev(self, "F8.4 phase 2: CARDEMU->ACT\n");
    for (i = 0; i < RTWN8723BE_CARDEMU_TO_ACT_STEPS; i++) {
        s = &rtwn8723be_carde_mu_to_act[i];
        if ((s->intf_mask & RTWN8723BE_PWR_INTF_PCI) == 0) {
            skipped++;
            continue;
        }
        selected++;
        aprint_normal_dev(self,
            "F8.4 step %zu: cmd=%u offset=0x%04x mask=0x%02x value=0x%02x\n",
            selected, s->cmd, s->offset, s->mask, s->value);
    }

    aprint_normal_dev(self, "F8.4 step %zu: END (model only)\n", selected + 1);
    aprint_normal_dev(self,
        "F8.4 dry-run complete: %zu PCI steps selected, %zu non-PCI steps skipped; END modeled; no hardware access\n",
        selected, skipped);
}

static void
rtwn8723be_firmware_probe(device_t self)
{
    firmware_handle_t fwh = NULL;
    uint8_t hdr[32];
    int fwerr, error;
    off_t fwsize;
    uint16_t fw_signature, fw_version, fw_subversion, ramcodesize;
    uint32_t svnidx;
    uint32_t payload_size;
    /* F3: firmware-format validation only. No PCI command writes, BAR mapping,
     * MMIO access, DMA, interrupts, or firmware download. */
    fwerr = firmware_open("if_rtwn8723be", "rtl8723befw_36.bin", &fwh);
    if (fwerr != 0) {
        aprint_error_dev(self,
            "firmware_open rtl8723befw_36.bin failed: %d\n", fwerr);
        return;
    }

    fwsize = firmware_get_size(fwh);
    if (fwsize < (off_t)sizeof(hdr)) {
        aprint_error_dev(self, "firmware too small: %lld bytes\n",
            (long long)fwsize);
        firmware_close(fwh);
        return;
    }

    error = firmware_read(fwh, 0, hdr, sizeof(hdr));
    firmware_close(fwh);
    if (error != 0) {
        aprint_error_dev(self, "firmware_read header failed: %d\n", error);
        return;
    }

    fw_signature = (uint16_t)hdr[0] | ((uint16_t)hdr[1] << 8);
    fw_version = (uint16_t)hdr[4] | ((uint16_t)hdr[5] << 8);
    fw_subversion = (uint16_t)hdr[6] | ((uint16_t)hdr[7] << 8);
    ramcodesize = (uint16_t)hdr[12] | ((uint16_t)hdr[13] << 8);
    svnidx = (uint32_t)hdr[16] | ((uint32_t)hdr[17] << 8) |
        ((uint32_t)hdr[18] << 16) | ((uint32_t)hdr[19] << 24);
    payload_size = (uint32_t)fwsize - (uint32_t)sizeof(hdr);

    if ((fw_signature & 0xfff0) != 0x5300) {
        aprint_error_dev(self,
            "invalid RTL8723BE firmware signature: 0x%04x\n",
            fw_signature);
        return;
    }
    if ((uint32_t)ramcodesize != payload_size) {
        aprint_error_dev(self,
            "firmware payload size mismatch: header=%u file=%u\n",
            ramcodesize, payload_size);
        return;
    }

    aprint_normal_dev(self,
        "firmware rtl8723befw_36.bin validated, size=%lld, signature=0x%04x, "
        "version=%u.%u, date=%02x-%02x %02x:%02x, payload=%u, svnidx=0x%08x\n",
        (long long)fwsize, fw_signature, fw_version, fw_subversion,
        hdr[8], hdr[9], hdr[10], hdr[11], payload_size, svnidx);

    aprint_normal_dev(self,
        "F3 passive firmware validation complete; signature/payload verified; hardware access intentionally skipped\n");
}

static void
rtwn8723be_attach(device_t parent, device_t self, void *aux)
{
    struct rtwn8723be_softc *sc = device_private(self);
    struct pci_attach_args *pa = aux;
    uint32_t pcicmd;
    pcireg_t memtype;
    int error;

    sc->sc_dev = self;
    sc->sc_pc = pa->pa_pc;
    sc->sc_tag = pa->pa_tag;
    pci_aprint_devinfo(pa, NULL);

    /* F4: one read-only PCI configuration snapshot.  No config writes,
     * power-state changes, BAR mapping, MMIO, DMA, interrupts, or download. */
    pcicmd = pci_conf_read(pa->pa_pc, pa->pa_tag, PCI_COMMAND_STATUS_REG);
    aprint_normal_dev(self,
        "F4 PCI config snapshot: command=0x%04x [io=%s mem=%s master=%s], status=0x%04x; no hardware state changed\n",
        pcicmd & 0xffff,
        (pcicmd & PCI_COMMAND_IO_ENABLE) ? "on" : "off",
        (pcicmd & PCI_COMMAND_MEM_ENABLE) ? "on" : "off",
        (pcicmd & PCI_COMMAND_MASTER_ENABLE) ? "on" : "off",
        (pcicmd >> 16) & 0xffff);

    /* F5: map the existing 64-bit MMIO BAR only.  No register access,
     * PCI command writes, bus mastering, DMA, interrupts, or firmware I/O. */
    memtype = pci_mapreg_type(pa->pa_pc, pa->pa_tag, 0x18);
    error = pci_mapreg_map(pa, 0x18, memtype, 0,
        &sc->sc_st, &sc->sc_sh, &sc->sc_base, &sc->sc_mapsize);
    if (error != 0) {
        aprint_error_dev(self,
            "F5 MMIO BAR mapping failed: %d\n", error);
        return;
    }
    aprint_normal_dev(self,
        "F5 MMIO BAR mapped: base=0x%llx size=0x%llx; "
        "no MMIO access performed\n",
        (unsigned long long)sc->sc_base,
        (unsigned long long)sc->sc_mapsize);

    /* F8: source-only RTL8723BE PCIe power-sequence mapping.
     * No MMIO reads/writes are performed here.  The sequence below is
     * derived from the Linux RTL8723BE reference driver and is retained
     * as a hardware-access plan until each transition is implemented. */
    aprint_normal_dev(self,
        "F8 mapping: PCI interface mask=BIT(2), MAC register BAR offsets; "
        "no power-sequence access performed\n");
    aprint_normal_dev(self,
        "F8 PCIe CARDEMU->ACT: ALL: 0x0005(mask=0x1c,value=0), "
        "PCI: 0x0075(bit0=1), ALL: poll 0x0006(bit1=1), "
        "PCI: 0x0075(bit0=0), ALL: 0x0006(bit0=1), "
        "ALL: 0x0005(bit7=0), 0x0005(bits4:3=0), "
        "0x0005(bit0=1), poll 0x0005(bit0=0), "
        "0x0010(bit6=1), 0x0049(bit1=1), 0x0063(bit1=1), "
        "0x0062(bit1=0), 0x0058(bit0=1), 0x005a(bit1=1), "
        "0x0068(bit3=1 test-cut only), 0x0069(bit6=1)\n");
    aprint_normal_dev(self,
        "F8 register map: 0x00e4=PCIE_MIO_INTF, 0x00e8=PCIE_MIO_INTD, "
        "0x00ec=HPON_FSM, 0x00f0=SYS_CFG, 0x00f4=GPIO_OUTSTS, "
        "0x00f8=MAC_PHY_CTRL_NORMAL, 0x00fc=SYS_CFG1, 0x0100=CR, "
        "0x0301=PCIe DMA control, 0x0361=PCIe RPWM\n");

    rtwn8723be_pwrseq_dryrun(self);

    /* Firmware access remains deferred until the filesystem is available. */
    config_mountroot(self, rtwn8723be_firmware_probe);
}

CFATTACH_DECL_NEW(rtwn8723be, sizeof(struct rtwn8723be_softc),
    rtwn8723be_match, rtwn8723be_attach, NULL, NULL);
