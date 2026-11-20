"""Apply a real delta from an explicitly selected old ZIP to staged Wi-Fi code."""
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile

TOP = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(TOP/'installer'), str(TOP/'installer/tests')]
from test_ota import mu_release
from backend.ota_package import analyze
from backend.ota_engine import Engine, Patch

BASE = os.environ.get('PRO_APSTA_BASE_ZIP')
TARGET = os.environ.get('PRO_APSTA_TARGET_ROOT')
FILES = ('usr/sbin/wpad', 'usr/share/hostap/hostapd.uc', 'usr/share/hostap/common.uc',
         'usr/share/hostap/wpa_supplicant.uc', 'usr/share/ucode/wifi/ap.uc',
         'usr/share/ucode/wifi/supplicant.uc',
         'opt/u30pro/bin/u30pro-panel', 'usr/sbin/u30pro-panel-control')


@unittest.skipUnless(BASE and TARGET and sys.platform == 'linux',
                     'explicit base ZIP and staged target root required')
class NativeWifiDelivery(unittest.TestCase):
    def test_both_products_receive_real_program_and_preserve_user_network(self):
        old = {}
        with zipfile.ZipFile(BASE) as package:
            manifest = json.loads(package.read('desktop/manifest.json'))
            with package.open(manifest['magisk_layout']['mu300-openwrt.tar.gz']) as stream:
                with tarfile.open(fileobj=stream, mode='r|gz') as archive:
                    for entry in archive:
                        name = entry.name.removeprefix('./')
                        if name in FILES:
                            old[name] = archive.extractfile(entry).read()
        self.assertEqual(set(old), set(FILES))
        new = {name:(Path(TARGET)/name).read_bytes() for name in FILES}
        self.assertNotEqual(old['usr/sbin/wpad'], new['usr/sbin/wpad'])
        receipt = 'usr/share/mu300/wifi-userspace.json'
        new[receipt] = (Path(TARGET)/receipt).read_bytes()
        for profile in ('u30pro', 'f50pro'):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                live = root/'live'
                user = {'etc/config/wireless':b'AP and STA credentials, explicitly enabled AP',
                        'etc/config/network':b'user routing priorities',
                        'etc/config/firewall':b'user firewall zones',
                        'etc/config/u30pro_native_control':b'user screen and wallpaper settings'}
                for name, raw in dict(old, **user).items():
                    path = live/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
                identity = live/'etc/mu300/release.json'
                identity.parent.mkdir(parents=True)
                identity.write_text(json.dumps(dict(image_version=profile+'-r1', profile=profile,
                                                     kernel_release='6.12.94-u30pro-p1')))
                for version, files in ((1, old), (2, new)):
                    release = root/str(version)
                    mu_release(release, profile+'-r'+str(version), files)
                    path = release/'desktop/release.json'
                    value = json.loads(path.read_text())
                    value.update(profile=profile, kernel_release='6.12.94-u30pro-p1')
                    path.write_text(json.dumps(value))
                output = root/'wifi.ota'
                result = analyze(root/'1', root/'2', output)
                self.assertTrue(result['can_export'], result['blockers'])
                changed = {op['path'] for op in result['manifest']['operations']}
                self.assertIn('usr/sbin/wpad', changed)
                self.assertIn('opt/u30pro/bin/u30pro-panel', changed)
                self.assertIn('usr/sbin/u30pro-panel-control', changed)
                self.assertIn(receipt, changed)
                with Patch(output) as archive:
                    self.assertEqual(Engine(live).apply(archive)['status'], 'complete')
                for name, raw in new.items():
                    self.assertEqual((live/name).read_bytes(), raw, name)
                for name, raw in user.items():
                    self.assertEqual((live/name).read_bytes(), raw, name)


if __name__ == '__main__':
    unittest.main()
