#!/usr/bin/env python3
"""Idempotent patches for the pinned OpenWrt 25.12 hostapd and wifi-scripts."""
from pathlib import Path
import argparse


def replace(path, old, new):
    text = path.read_text(encoding='utf-8')
    if new in text:
        return
    if text.count(old) != 1:
        raise ValueError('Unexpected hostapd source: ' + str(path) + ': ' + old[:65])
    path.write_text(text.replace(old, new, 1), encoding='utf-8')


def insert_import(path, anchor, declaration):
    # Composed patches share prepared sources. Keep each owned import once.
    text = path.read_text(encoding='utf-8').replace(declaration+'\n', '')
    if text.count(anchor) != 1:
        raise ValueError('Unexpected import anchor: '+str(path))
    path.write_text(text.replace(anchor, anchor+declaration+'\n', 1), encoding='utf-8')


def patch_source(root):
    root = Path(root)
    # Release builds omit DEBUG messages. Keep failed key-request metadata
    # available without logging key bytes or changing encryption policy.
    replace(root / 'src/drivers/driver_nl80211.c',
            '\tif (ret)\n'
            '\t\twpa_printf(MSG_DEBUG, "nl80211: set_key failed; err=%d %s",\n'
            '\t\t\t   ret, strerror(-ret));\n',
            '\tif (ret)\n'
            '\t\twpa_printf(MSG_INFO, "nl80211: set_key failed; err=%d %s "\n'
            '\t\t\t   "alg=%d idx=%d key_len=%zu seq_len=%zu "\n'
            '\t\t\t   "key_flag=0x%x link_id=%d",\n'
            '\t\t\t   ret, strerror(-ret), alg, key_idx, key_len,\n'
            '\t\t\t   seq_len, key_flag, link_id);\n')
    replace(root / 'src/ap/ucode.c',
            '\tif (!iface || ucv_type(info) != UC_OBJECT)\n\t\treturn NULL;\n\n'
            '\tconf = iface->conf;\n',
            '''\tif (!iface || ucv_type(info) != UC_OBJECT)
\t\treturn NULL;

\t/* AP+STA stop() removes the beacon while the station scans. A stopped
\t * BSS cannot announce a channel switch: resume it on the station's
\t * channel through start(), which sends START_AP rather than SET_BEACON.
\t */
\tfor (i = 0; i < iface->num_bss; i++)
\t\tif (!iface->bss[i]->beacon_set_done)
\t\t\treturn uc_hostapd_iface_start(vm, nargs);

\tconf = iface->conf;
''')
    replace(root / 'src/ap/ap_config.h', '\tint sae_require_mfp;\n',
            '\tint sae_require_mfp;\n\tint unisoc_sae; /* trusted firmware PMK indication */\n')
    replace(root / 'hostapd/config_file.c',
            '\t} else if (os_strcmp(buf, "sae_require_mfp") == 0) {',
            '\t} else if (os_strcmp(buf, "unisoc_sae") == 0) {\n'
            '\t\tif (os_strcmp(pos, "0") && os_strcmp(pos, "1"))\n'
            '\t\t\treturn 1;\n\t\tbss->unisoc_sae = atoi(pos);\n'
            '\t} else if (os_strcmp(buf, "sae_require_mfp") == 0) {')
    path = root / 'src/ap/drv_callbacks.c'
    replace(path, '#include "nan_usd_ap.h"\n',
            '#include "nan_usd_ap.h"\n#include "unisoc_sae.h"\n')
    replace(path, '\t\twpa_auth_set_rsn_selection(sta->wpa_sm, elems.rsn_selection,',
            '''#ifdef CONFIG_SAE
		if (unisoc_sae_import(hapd, sta, req_ies, req_ies_len) < 0) {
			wpa_printf(MSG_INFO, "Unisoc SAE: missing or invalid firmware key indication");
			reason = WLAN_REASON_UNSPECIFIED;
			goto fail;
		}
#endif
		wpa_auth_set_rsn_selection(sta->wpa_sm, elems.rsn_selection,''')
    path = root / 'src/drivers/driver_nl80211_event.c'
    replace(path, 'wpa_hexdump(MSG_DEBUG, "nl80211: Assoc Req IEs",',
            'wpa_hexdump_key(MSG_DEBUG, "nl80211: Assoc Req IEs",')
    (root / 'src/ap/unisoc_sae.h').write_bytes(
        Path(__file__).with_name('hostapd-unisoc-sae.h').read_bytes())
    replace(root / 'src/ap/beacon.c',
            '\t/* If SAE offload is enabled, provide password to lower layer for',
            '''	/* This BSP ABI has no H2E/group negotiation fields. Fail clearly
	 * rather than advertise mechanisms the firmware cannot be configured for.
	 */
	if (hapd->conf->unisoc_sae &&
	    (hapd->conf->wpa_key_mgmt & WPA_KEY_MGMT_SAE) &&
	    (!(hapd->iface->drv_flags2 & WPA_DRIVER_FLAGS2_SAE_OFFLOAD_AP) ||
	     (hapd->conf->sae_pwe != SAE_PWE_HUNT_AND_PECK &&
	      hapd->conf->sae_pwe != SAE_PWE_FORCE_HUNT_AND_PECK) ||
	     (hapd->conf->sae_groups &&
	      (hapd->conf->sae_groups[0] != 19 || hapd->conf->sae_groups[1])))) {
		wpa_printf(MSG_ERROR, "Unisoc SAE: requires firmware offload, hunting-and-pecking and group 19");
		return -1;
	}
	/* If SAE offload is enabled, provide password to lower layer for''')


def patch_wifi(root):
    root = Path(root)
    patch_fullmac(root / 'usr/share/hostap/common.uc')
    patch_cipher_capabilities(root.parent / 'files-ucode/usr/share/ucode/wifi')
    path = root / 'lib/netifd/hostapd.sh'
    # Shared hotspot policy: disable U-APSD advertisement, retaining WMM and
    # the existing beacon/DTIM settings. Also covers restored old UCI values.
    replace(path, '\tset_default uapsd 1\n',
            '\tuapsd=0 # U-APSD is disabled by the shared hotspot policy.\n')
    replace(path, 'hostapd_set_bss_options() {',
            '. /lib/netifd/hostapd-unisoc.sh\n\nhostapd_set_bss_options() {')
    replace(path, '\t[ -n "$spp_amsdu" ] && append bss_conf "spp_amsdu=$spp_amsdu" "$N"\n',
            '\t[ -n "$spp_amsdu" ] && append bss_conf "spp_amsdu=$spp_amsdu" "$N"\n'
            '\n\tunisoc_sae_bss_options\n')
    (root / 'lib/netifd/hostapd-unisoc.sh').write_bytes(
        Path(__file__).with_name('hostapd-unisoc.sh').read_bytes())
    # OpenWrt 25.12 normally uses the ucode generator; the shell path above
    # remains available to builds that deliberately select legacy scripts.
    ucode = root.parent / 'files-ucode/usr/share/ucode/wifi'
    path = ucode / 'ap.uc'
    patch_apsta_ap(path)
    patch_apsta_supplicant(ucode / 'supplicant.uc')
    replace(path, '\tconfig.wmm_enabled = 1;\n',
            '\tconfig.wmm_enabled = 1;\n'
            '\tconfig.uapsd_advertisement_enabled = 0; // Shared hotspot policy.\n')
    insert_import(path, "import * as iface from 'wifi.iface';\n",
                  "import { configure as unisoc_sae_config } from 'wifi.unisoc-sae';")
    replace(path, '\tiface_auth_type(config);',
            "\tunisoc_sae_config(config, fs.realpath(`/sys/class/ieee80211/${data.phy}/device/driver/module`));\n"
            "\tif (config.unisoc_sae)\n\t\tappend('unisoc_sae', config.unisoc_sae);\n"
            '\tiface_auth_type(config);')
    (ucode / 'unisoc-sae.uc').write_bytes(
        Path(__file__).with_name('hostapd-unisoc.uc').read_bytes())


def patch_cipher_capabilities(root):
    root = Path(root)
    # HE/EHT describes PHY operation, not hardware cipher support. Reuse the
    # wiphy dump already obtained for this radio instead of advertising GCMP-256
    # solely because Wi-Fi 6/7 is enabled. Explicit user ciphers stay unchanged.
    replace(root / 'hostapd.uc',
            '\tphy_features.ftm_responder = device_extended_features(phy.extended_features, NL80211_EXT_FEATURE_ENABLE_FTM_RESPONDER);\n',
            '\tphy_features.cipher_suites = phy.cipher_suites ?? [];\n'
            '\tphy_features.ftm_responder = device_extended_features(phy.extended_features, NL80211_EXT_FEATURE_ENABLE_FTM_RESPONDER);\n')
    replace(root / 'ap.uc',
            '\tiface.parse_encryption(config, data.config);\n',
            '\tiface.parse_encryption(config, data.config, phy_features.cipher_suites);\n')
    replace(root / 'iface.uc',
            'export function parse_encryption(config, dev_config) {',
            'export function parse_encryption(config, dev_config, cipher_suites) {')
    replace(root / 'iface.uc',
            "\tif (wildcard(dev_config?.htmode, 'EHT*') || wildcard(dev_config?.htmode, 'HE*'))\n",
            "\tif ((wildcard(dev_config?.htmode, 'EHT*') || wildcard(dev_config?.htmode, 'HE*')) &&\n"
            '\t    index(cipher_suites ?? [], 0x000fac09) >= 0)\n')


def patch_apsta_ap(path):
    insert_import(path, "import * as fs from 'fs';\n",
                  "import { phy_supports_ap_sta_mcc } from '/usr/share/hostap/common.uc';")
    replace(path, '\tconfig.start_disabled = data.ap_start_disabled;\n',
            '\tconfig.start_disabled = data.ap_start_disabled && !phy_supports_ap_sta_mcc(data.phy);\n')


def patch_apsta_supplicant(path):
    insert_import(path, "import * as fs from 'fs';\n",
                  "import { phy_supports_ap_sta_mcc } from '/usr/share/hostap/common.uc';")
    replace(path, '\tband = wiphy_band(phy, band);\n\tif (!band)\n',
            '\tlet bands = band == null ? phy?.wiphy_bands : [wiphy_band(phy, band)];\n\tif (!bands)\n')
    replace(path, '\tfor (let chan in band.freqs)\n'
            '\t\tif (!chan.disabled && freq_in_range(ranges, chan.freq))\n'
            '\t\t\tpush(freqs, chan.freq);\n',
            '\tfor (let _, candidate in bands)\n'
            '\t\tfor (let chan in candidate?.freqs ?? [])\n'
            '\t\t\tif (!chan.disabled && freq_in_range(ranges, chan.freq))\n'
            '\t\t\t\tpush(freqs, chan.freq);\n')
    replace(path, '\t\tdata.config.scan_list = wiphy_frequencies(data.phy, data.config.band, data.config.radio);\n',
            '\t\tdata.config.scan_list = wiphy_frequencies(data.phy,\n'
            '\t\t\tinterface.config.mode == "sta" && phy_supports_ap_sta_mcc(data.phy) ? null : data.config.band,\n'
            '\t\t\tdata.config.radio);\n')


def patch_fullmac(path):
    # AP+STA pauses beacons without releasing the administratively UP AP.
    # Carrier loss does not make that interface available to wpa_supplicant.
    replace(path,
            '\tfor (let res in data)\n'
            '\t\tif (trim(readfile(`/sys/class/net/${res.ifname}/operstate`)) == "down")\n'
            '\t\t\treturn res.ifname;\n',
            '''\tfor (let res in data) {
\t\tlet flags = readfile(`/sys/class/net/${res.ifname}/flags`);
\t\tif (flags != null && !(int(trim(flags), 16) & 1)) // IFF_UP: preserve configured AP/STA owners.
\t\t\treturn res.ifname;
\t}
''')
    replace(path, 'function wdev_set_radio_mask(name, mask)\n',
            '''// Keep independent AP/STA channels only when one advertised combination
// permits both roles and at least two channels. No channel or country override.
function phy_supports_ap_sta_mcc(phy)
{
\tphy = split(phy, ".")[0]; // hostapd may append a radio index.
\tlet index = readfile(`/sys/class/ieee80211/${phy}/index`);
\tif (index == null)
\t\treturn false;
\tlet caps = nl80211.request(nl80211.const.NL80211_CMD_GET_WIPHY, 0, { wiphy: int(index) });
\tfor (let combo in caps?.interface_combinations ?? []) {
\t\tif (combo.maxnum < 2 || combo.num_channels < 2)
\t\t\tcontinue;
\t\tlet ap = false, sta = false;
\t\tfor (let limit in combo.limits ?? []) {
\t\t\tif (limit.max < 1 || (limit.types.ap && limit.types.managed && limit.max < 2))
\t\t\t\tcontinue;
\t\t\tap = ap || !!limit.types.ap;
\t\t\tsta = sta || !!limit.types.managed;
\t\t}
\t\tif (ap && sta)
\t\t\treturn true;
\t}
\treturn false;
}

function wdev_set_radio_mask(name, mask)
''')
    replace(path, 'phy_is_fullmac, phy_open',
            'phy_is_fullmac, phy_supports_ap_sta_mcc, phy_open')


def patch_reload(root):
    root = Path(root)
    replace(root / 'hostapd.uc', 'phy_is_fullmac, phy_open,',
            'phy_is_fullmac, phy_supports_ap_sta_mcc, phy_open,')
    replace(root / 'hostapd.uc',
            'function iface_add(phy, config, phy_status)\n{\n',
            '''function iface_add(phy, config, phy_status)
{
\t// A multi-channel radio need not start its AP disabled or follow the STA.
\tif (phy_supports_ap_sta_mcc(phy))
\t\tphy_status = null;
''')
    replace(root / 'hostapd.uc',
            '\t\t\tif (!req.args.up) {\n\t\t\t\tiface.stop();\n',
            '''\t\t\t// MCC keeps the configured AP running while the STA scans, fails,
\t\t\t// reconnects or changes channel. Regulatory checks remain in each role.
\t\t\tif (phy_supports_ap_sta_mcc(phy))
\t\t\t\treturn 0;

\t\t\tif (!req.args.up) {
\t\t\t\tiface.stop();
''')
    # SET_BEACON has no crypto-settings callback in cfg80211. In-place BSS
    # reloads cannot update the firmware password; restart only when an SAE
    # BSS configuration actually changes, not on each ordinary reload.
    replace(root / 'hostapd.uc',
            '\tif (is_equal(old_config.bss, config.bss))\n\t\treturn true;\n',
            '''\tif (is_equal(old_config.bss, config.bss))
		return true;

	/* A changed firmware-SAE BSS needs START_AP with its new password. */
	for (let cfg in [ old_config, config ])
		for (let bss in cfg.bss ?? [])
			for (let line in bss.data ?? [])
				if (line == 'unisoc_sae=1')
					return false;
''')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('kind', choices=['source', 'wifi', 'reload'])
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    {'source': patch_source, 'wifi': patch_wifi, 'reload': patch_reload}[args.kind](args.root)
