"""Pro overlay feature introduction and update through the real delta engine."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOP/'installer'),str(TOP/'installer/tests')]
from test_ota import mu_release
from backend.ota_package import analyze
from backend.ota_engine import Engine, Patch

NAMES=('usr/libexec/unisoc-modem/wifi-relay','usr/libexec/rpcd/u30pro-wifi-relay',
       'usr/share/ucode/mu300/wifi-relay.uc','usr/share/ucode/mu300/wifi-native.uc',
       'usr/share/luci/menu.d/u30pro-wifi-relay.json','usr/share/rpcd/acl.d/u30pro-wifi-relay.json',
       'www/luci-static/resources/view/mu300/wifi-relay.js',
       'www/luci-static/resources/mu300/wifi-relay.css')


@unittest.skipUnless(sys.platform=='linux','Linux update metadata')
class Delivery(unittest.TestCase):
    def test_both_pro_products_receive_new_code_and_keep_network_settings(self):
        for profile in ('u30pro','f50pro'):
            with self.subTest(profile=profile),tempfile.TemporaryDirectory() as folder:
                base=Path(folder);live=base/'live';live.mkdir()
                user={'etc/config/wireless':b'custom AP + STA credentials',
                      'etc/config/network':b'user interface priorities',
                      'etc/config/firewall':b'user firewall rules',
                      'etc/config/u30pro_native_control':b'user screen settings'}
                initial={'usr/lib/anchor':b'old'}
                code={name:(TOP/'devices/u30pro/overlay'/name).read_bytes() for name in NAMES}
                for name,raw in dict(initial,**user).items():
                    p=live/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                # An existing installation lacks the new RPC/view ancestors.
                # The actual generator and applier must handle introduction.
                identity=live/'etc/mu300/release.json';identity.parent.mkdir(parents=True)
                identity.write_text(json.dumps(dict(image_version=profile+'-r1',profile=profile,kernel_release='6.12.94-u30pro-p1')))
                releases=[]
                for generation,files in enumerate((initial,dict(initial,**code),
                        dict(initial,**{name:raw+b'\n' for name,raw in code.items()})),1):
                    path=base/str(generation);mu_release(path,profile+'-r'+str(generation),files)
                    receipt=path/'desktop/release.json';value=json.loads(receipt.read_text())
                    value.update(profile=profile,kernel_release='6.12.94-u30pro-p1');receipt.write_text(json.dumps(value))
                    releases.append(path)
                for generation in range(2):
                    package=base/(str(generation)+'.ota')
                    result=analyze(releases[generation],releases[generation+1],package)
                    self.assertTrue(result['can_export'],result['blockers'])
                    self.assertTrue(set(code)<={op['path'] for op in result['manifest']['operations']})
                    with Patch(package) as archive:
                        self.assertEqual(Engine(live).apply(archive)['status'],'complete')
                    for name,raw in user.items():self.assertEqual((live/name).read_bytes(),raw)
                    for name,raw in code.items():self.assertEqual((live/name).read_bytes(),raw+b'\n'*generation)


if __name__=='__main__':unittest.main()
