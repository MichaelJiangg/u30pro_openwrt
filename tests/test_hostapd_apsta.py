"""Exercise the patched, pinned hostapd C method without a radio.

UNISOC_HOSTAPD_SOURCE explicitly selects an existing prepared source cache.
Only the patch's input files are copied into a temporary test fixture.
"""
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
SOURCE = os.environ.get('UNISOC_HOSTAPD_SOURCE')
INPUTS = ('src/ap/ucode.c', 'src/ap/ap_config.h', 'hostapd/config_file.c',
          'src/ap/drv_callbacks.c', 'src/drivers/driver_nl80211_event.c',
          'src/ap/beacon.c', 'src/drivers/driver_nl80211.c')

STUBS = r'''
#include <assert.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef struct { int type, value; } uc_value_t;
typedef struct { int marker; } uc_vm_t;
enum { UC_OBJECT = 1 };
struct hostapd_config { int ieee80211n, ieee80211ac, ieee80211ax; };
struct hostapd_data { int beacon_set_done; };
struct hostapd_iface {
    struct hostapd_config *conf;
    int num_bss;
    struct hostapd_data *bss[2];
};
struct freq_params {
    int sec_channel_offset, ht_enabled, vht_enabled, he_enabled;
    int bandwidth, freq, center_freq1, center_freq2;
};
struct csa_settings { int cs_count; struct freq_params freq_params; };
static struct hostapd_config config;
static struct hostapd_data first, second;
static struct hostapd_iface iface = { &config, 2, { &first, &second } };
static struct hostapd_iface *current = &iface;
static uc_value_t request = { UC_OBJECT, 0 }, yes = { 0, 1 }, no = { 0, 0 };
static int starts, switches, switch_error;
static uc_vm_t vm;
static void *uc_fn_thisval(const char *name) { (void) name; return current; }
static uc_value_t *uc_fn_arg(int index) { (void) index; return &request; }
static int ucv_type(uc_value_t *v) { return v->type; }
static uc_value_t *ucv_object_get(uc_value_t *v, const char *key, void *unused) {
    (void) v; (void) key; (void) unused; return NULL;
}
static int64_t ucv_int64_get(uc_value_t *v) {
    errno = v ? 0 : EINVAL; return v ? v->value : 0;
}
static uc_value_t *ucv_boolean_new(int value) { return value ? &yes : &no; }
static int hostapd_get_oper_chwidth(struct hostapd_config *c) { (void) c; return 0; }
static int hostapd_switch_channel(struct hostapd_data *bss, struct csa_settings *csa) {
    assert(bss->beacon_set_done);
    assert(csa->freq_params.bandwidth == 20);
    switches++; return switch_error;
}
static uc_value_t *uc_hostapd_iface_start(uc_vm_t *v, size_t nargs) {
    assert(v == &vm && nargs == 1);
    assert(uc_fn_arg(0) == &request); /* preserve the original frequency request */
    starts++; first.beacon_set_done = second.beacon_set_done = 1; return &yes;
}
'''

MAIN = r'''
int main(void) {
    /* AP+STA scanning stopped both beacons. Completion must start, not CSA. */
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == &yes);
    assert(starts == 1 && switches == 0);
    /* A later live channel change retains the original CSA path. */
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == &yes);
    assert(starts == 1 && switches == 2);
    /* A subsequent scan/resume, including a stopped secondary BSS. */
    second.beacon_set_done = 0;
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == &yes);
    assert(starts == 2 && switches == 2);
    /* Genuine live CSA errors must still be reported. */
    switch_error = -1;
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == &no);
    assert(starts == 2 && switches == 4);
    request.type = 0;
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == NULL);
    request.type = UC_OBJECT; current = NULL;
    assert(uc_hostapd_iface_switch_channel(&vm, 1) == NULL);
    assert(starts == 2 && switches == 4);
    puts("PASS actual hostapd C: stopped/resumed AP, live CSA, secondary BSS, errors and invalid calls");
    return 0;
}
'''


@unittest.skipUnless(SOURCE and shutil.which('cc'), 'explicit hostapd source and C compiler required')
class ApStaResume(unittest.TestCase):
    def test_production_c_lifecycle_and_idempotent_patch(self):
        with tempfile.TemporaryDirectory(prefix='hostapd-apsta-test-') as folder:
            root = Path(folder)
            for name in INPUTS:
                target = root/name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(Path(SOURCE)/name, target)
            patch = runpy.run_path(str(TOP/'openwrt/patch-hostapd-sae.py'))['patch_source']
            patch(root)
            before = {name:(root/name).read_bytes() for name in INPUTS}
            patch(root)
            self.assertEqual(before, {name:(root/name).read_bytes() for name in INPUTS})
            text = (root/'src/ap/ucode.c').read_text()
            start = text.index('static uc_value_t *\nuc_hostapd_iface_switch_channel(')
            end = text.index('\nstatic uc_value_t *', start+1)
            source = root/'apsta.c'
            source.write_text(STUBS + text[start:end] + MAIN)
            binary = root/'apsta'
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == '__main__':
    unittest.main()
