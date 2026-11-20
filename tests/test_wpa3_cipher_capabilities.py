"""Execute real wifi-scripts parsing against old and capability-aware sources."""
import copy
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
BASE = os.environ.get('WPA3_CIPHER_BASE')
IMAGE = os.environ.get('WPA3_CIPHER_IMAGE')


@unittest.skipUnless(BASE and IMAGE and shutil.which('docker'),
                     'explicit original source fixture and ucode image required')
class CipherCapabilities(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='wpa3-cipher-')
        self.root = Path(self.temp.name)
        for name in ('iface.uc', 'ap.uc', 'hostapd.uc'):
            shutil.copyfile(Path(BASE)/('before-'+name), self.root/name)
        self.original = (self.root/'iface.uc').read_text()
        self.patch = runpy.run_path(str(TOP/'openwrt/patch-hostapd-sae.py'))['patch_cipher_capabilities']
        self.patch(self.root)
        self.patched = (self.root/'iface.uc').read_text()
        self.ccmp = [0x000fac01, 0x000fac05, 0x000fac02, 0x000fac04, 0x000fac06, 0x00147201]

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, cases):
        def function(text, name):
            return text[text.index('export function parse_encryption('):
                        text.index('export function wpa_key_mgmt(')].replace(
                            'export function parse_encryption(', 'function '+name+'(', 1)
        program = function(self.original, 'original') + function(self.patched, 'patched')
        program += '\nlet cases = '+json.dumps(cases)+'; let result=[];\n'
        program += '''for (let c in cases) {
            let old=json(sprintf('%J', c.config)), next=json(sprintf('%J', c.config));
            original(old, c.device); patched(next, c.device, c.suites);
            push(result, {old, next});
        } print(sprintf('%J', result));'''
        result = subprocess.run(['docker', 'run', '--rm', '-i', '--network', 'none',
                                 '--platform', 'linux/arm64', '--entrypoint', 'ucode', IMAGE, '-'],
                                input=program, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def case(self, suites=None, **config):
        value = dict(encryption='sae', rsn_override=1, ieee80211w=2, key='preserved-secret')
        value.update(config)
        return dict(config=value, device=dict(htmode='HE80'), suites=suites)

    def test_01_actual_aic_cipher_list_reproduces_and_fixes_hidden_override(self):
        value = self.parse([self.case(self.ccmp)])[0]
        self.assertEqual(value['old']['rsn_override_pairwise'], 'GCMP-256 CCMP')
        self.assertEqual(value['next']['wpa_pairwise'], 'CCMP')
        self.assertIsNone(value['next'].get('rsn_override_pairwise'))
        self.assertEqual(value['next']['ieee80211w'], 2)
        self.assertEqual(value['next']['key'], 'preserved-secret')

    def test_02_capable_radio_retains_gcmp256_and_rsn_override(self):
        for value in self.parse([self.case(self.ccmp+[0x000fac09], rsn_override=x) for x in (0, 1)]):
            self.assertEqual(value['old'], value['next'])

    def test_03_missing_capabilities_do_not_invent_gcmp256_support(self):
        for value in self.parse([self.case(s) for s in (None, [], [0x000fac08], [0x000fac10])]):
            self.assertNotIn('GCMP', value['next']['wpa_pairwise'])
            self.assertNotIn('GCMP', value['next'].get('rsn_override_pairwise') or '')

    def test_04_explicit_ciphers_and_enterprise192_are_not_silently_replaced(self):
        names = ['sae+ccmp', 'sae+gcmp', 'sae+gcmp256', 'sae+ccmp256',
                 'sae-mixed+ccmp', 'psk2+tkip+ccmp', 'wpa3-192']
        for value in self.parse([self.case(self.ccmp, encryption=e) for e in names]):
            self.assertEqual(value['old'], value['next'])

    def test_05_auth_band_override_matrix_matches_supported_original_behavior(self):
        cases=[]
        for auth in ('none', 'psk2', 'psk-mixed', 'sae', 'sae-mixed', 'psk3', 'psk3-mixed', 'owe', 'wpa2', 'wpa3'):
            for htmode in ('HT20', 'VHT80', 'HE20', 'HE80', 'EHT80'):
                for override in (0, 1):
                    c=self.case(self.ccmp, encryption=auth, rsn_override=override)
                    c['device']['htmode']=htmode
                    cases.append(c)
        values=self.parse(cases)
        references=copy.deepcopy(cases)
        for reference in references:
            if reference['device']['htmode'].startswith(('HE', 'EHT')):
                reference['device']['htmode']='VHT80'
        expected_values=self.parse(references)
        for c, value, reference in zip(cases, values, expected_values):
            expected=reference['old']
            self.assertEqual(expected, value['next'], c)

    def test_06_patch_is_idempotent_and_uses_existing_wiphy_dump(self):
        before={p.name:p.read_bytes() for p in self.root.iterdir()}
        self.patch(self.root)
        self.assertEqual(before, {p.name:p.read_bytes() for p in self.root.iterdir()})
        self.assertIn('phy_features.cipher_suites = phy.cipher_suites ?? [];',
                      (self.root/'hostapd.uc').read_text())
        self.assertIn('iface.parse_encryption(config, data.config, phy_features.cipher_suites);',
                      (self.root/'ap.uc').read_text())


if __name__ == '__main__':
    unittest.main()
