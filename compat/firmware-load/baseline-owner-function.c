int
rtwn8723be_netbsd_download_firmware(void *arg)
{
    struct rtwn8723be_softc *sc = arg;
    firmware_handle_t fwh = NULL;
    uint8_t hdr[R23BE_FW_HEADER_SIZE];
    uint8_t *payload = NULL;
    off_t fwsize;
    size_t payload_len;
    uint16_t signature, ramcodesize;
    int error;

    if (!sc->sc_mapped)
        return ENXIO;
    rtwn8723be_h2c_native_reset(sc);

    error = firmware_open(RTWN8723BE_FIRMWARE_DRIVER,
        RTWN8723BE_FIRMWARE_FILE, &fwh);
    if (error != 0)
        return error;

    fwsize = firmware_get_size(fwh);
    if (fwsize < (off_t)R23BE_FW_HEADER_SIZE) {
        error = EINVAL;
        goto out;
    }

    payload_len = (size_t)fwsize - R23BE_FW_HEADER_SIZE;
    if (payload_len == 0 ||
        payload_len > (size_t)R23BE_FW_MAX_PAGES * R23BE_FW_PAGE_SIZE) {
        error = EFBIG;
        goto out;
    }

    error = firmware_read(fwh, 0, hdr, sizeof(hdr));
    if (error != 0)
        goto out;

    signature = (uint16_t)hdr[0] | ((uint16_t)hdr[1] << 8);
    ramcodesize = (uint16_t)hdr[12] | ((uint16_t)hdr[13] << 8);
    if ((signature & 0xfff0U) != 0x5300U ||
        (size_t)ramcodesize != payload_len) {
        error = EINVAL;
        goto out;
    }

    payload = kmem_alloc(payload_len, KM_SLEEP);
    error = firmware_read(fwh, R23BE_FW_HEADER_SIZE, payload, payload_len);
    if (error != 0)
        goto out;

    error = rtwn8723be_netbsd_bt_preload_firmware(sc);
    if (error != 0)
        goto out;

    /*
     * rtwn8723be_fw_download() preserves the pinned Linux transfer
     * semantics: RAM_DL_SEL recovery, page upload, checksum polling,
     * MCUFWDL_RDY, MCU self-reset and WINTINI_RDY handshake.
     */
    error = rtwn8723be_fw_download(sc->sc_st, sc->sc_sh,
        payload, payload_len);
    if (error == 0)
        error = rtwn8723be_h2c_native_fw_ready(sc);

out:
    if (error != 0)
        rtwn8723be_h2c_native_reset(sc);
    if (payload != NULL)
        kmem_free(payload, payload_len);
    if (fwh != NULL)
        firmware_close(fwh);
    return error;
}
