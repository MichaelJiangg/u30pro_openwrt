"""Run the patched real interface chooser with carrier-down, owned APs."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
FILES = os.environ.get('UNISOC_WIFI_FILES')
ROOT = Path('/home/kano/openwrt-build/package-work/u30pro-release/root')


@unittest.skipUnless(FILES and ROOT.is_dir(), 'explicit hostapd files and prepared target required')
class InterfaceOwner(unittest.TestCase):
    def test_paused_ap_and_disconnected_sta_are_not_reused(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='fullmac-owner-') as folder:
            folder = Path(folder)
            for name in ('common.uc',):
                raw = subprocess.check_output([
                    'docker', 'run', '--rm', '--network', 'none', '--pull', 'never',
                    '-v', 'e5-openwrt-src:/build:ro', '--entrypoint', 'cat',
                    'unisoc-hostapd-build', FILES+'/'+name])
                (folder/name).write_bytes(raw)
            patch = runpy.run_path(str(TOP/'openwrt/patch-hostapd-sae.py'))['patch_fullmac']
            patch(folder/'common.uc')
            once = (folder/'common.uc').read_text()
            patch(folder/'common.uc')
            self.assertEqual((folder/'common.uc').read_text(), once)
            chooser = once.split('function find_reusable_wdev', 1)[1].split('function wdev_set_radio_mask', 1)[0]
            test = '''
let fullmac = true, devices = [], files = {};
function __phy_is_fullmac(phy) { return fullmac; }
let nl80211 = { const: {}, request: function() { return devices; } };
function readfile(path) { return files[path]; }
'''+'function find_reusable_wdev'+chooser+'''
function check(expected) {
    let result = find_reusable_wdev(0);
    if (result != expected) die(`expected ${expected}, got ${result}`);
}
devices = [{ifname:'wlan0'}, {ifname:'wlan1'}, {ifname:'idle'}];
files = {
 '/sys/class/net/wlan0/flags':'0x1003', // AP: admin UP, carrier DOWN during scan.
 '/sys/class/net/wlan0/operstate':'down',
 '/sys/class/net/wlan1/flags':'0x1003', // STA: admin UP, not associated yet.
 '/sys/class/net/wlan1/operstate':'down',
 '/sys/class/net/idle/flags':'0x1002', // Unowned, administratively DOWN.
 '/sys/class/net/idle/operstate':'down',
};
check('idle');
devices = [{ifname:'wlan0'}, {ifname:'wlan1'}];
check(null);
devices = [{ifname:'vanished'}, {ifname:'idle'}];
check('idle');
fullmac = false;
check(null);
print('PASS real fullmac chooser: paused AP, disconnected STA, idle VIF, vanished VIF, softmac\\n');
'''
            (folder/'test.uc').write_text(test)
            result = subprocess.run(['docker', 'run', '--rm', '--pull', 'never',
                '--network', 'none', '--platform', 'linux/arm64',
                '-v', str(ROOT)+':/target', '--entrypoint', '/bin/sh',
                'mu300-openwrt-base:25.12.5', '-ec',
                'chroot /target /usr/bin/ucode /tmp/'+folder.name+'/test.uc'],
                text=True, capture_output=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            print(result.stdout, end='')


if __name__ == '__main__':
    unittest.main()
