"""First/subsequent actual differential updates and rollback preserve settings."""
import hashlib
import io
import json
import os
import runpy
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(TOP/'installer'),str(TOP/'installer/tests')]
from test_ota import mu_release
from backend.ota_package import analyze
from backend.ota_engine import Engine, Patch

FILES={
 'etc/init.d/u30pro-charge-mode':'devices/u30pro/overlay/etc/init.d/u30pro-charge-mode',
 'usr/libexec/u30pro-charge-mode':'devices/u30pro/overlay/usr/libexec/u30pro-charge-mode',
 'usr/share/ucode/mu300/charger-boot.uc':'devices/u30pro/overlay/usr/share/ucode/mu300/charger-boot.uc',
 'etc/hotplug.d/power_supply/75-mu300-charge':'openwrt/luci-app-mu300/root/etc/hotplug.d/power_supply/75-mu300-charge',
}

def release(root,version,files):
    mu_release(root,version,{'usr/lib/anchor':b'old'})
    payload=root/'payload/mu300-openwrt.tar.gz'
    with tarfile.open(payload,'w:gz') as tar:
        parents={str(parent) for name in files for parent in Path(name).parents if str(parent)!='.'}
        for name in sorted(parents,key=lambda p:(p.count('/'),p)):
            entry=tarfile.TarInfo(name);entry.type=tarfile.DIRTYPE;entry.mode=0o755;tar.addfile(entry)
        for name,data in files.items():
            entry=tarfile.TarInfo(name);entry.mode=0o755 if name.startswith(('etc/init.d/','usr/libexec/','usr/sbin/','opt/u30pro/bin/')) else 0o644
            entry.size=len(data);tar.addfile(entry,io.BytesIO(data))
        if 'etc/init.d/u30pro-charge-mode' in files:
            entry=tarfile.TarInfo('etc/rc.d');entry.type=tarfile.DIRTYPE;entry.mode=0o755;tar.addfile(entry)
            entry=tarfile.TarInfo('etc/rc.d/S09u30pro-charge-mode');entry.type=tarfile.SYMTYPE
            entry.mode=0o777;entry.linkname='../init.d/u30pro-charge-mode';tar.addfile(entry)
    manifest=root/'desktop/manifest.json';value=json.loads(manifest.read_text())
    value['magisk']['payload/mu300-openwrt.tar.gz']=hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value))


@unittest.skipUnless(os.name=='posix' and os.geteuid()==0,'POSIX root for actual updater metadata')
class ChargeDelivery(unittest.TestCase):
    def test_two_updates_and_each_rollback_preserve_radio_wifi_bluetooth_and_data(self):
        current={name:(TOP/source).read_bytes() for name,source in FILES.items()}
        runtime=runpy.run_path(str(TOP/'tools/u30pro-runtime.py'))
        receipt=json.loads((runtime['OUT']/'runtime.json').read_text())
        for name,target in (('u30pro-panel','opt/u30pro/bin/u30pro-panel'),('mu300-keys','usr/sbin/mu300-keys')):
            row=receipt['files'][name]
            for source,digest in row['inputs']['sources'].items():
                self.assertEqual(hashlib.sha256((TOP/source).read_bytes()).hexdigest(),digest)
            current[target]=(runtime['OUT']/name).read_bytes()
            self.assertEqual(hashlib.sha256(current[target]).hexdigest(),row['sha256'])
        current['usr/lib/anchor']=b'old'
        old={'usr/lib/anchor':b'old','opt/u30pro/bin/u30pro-panel':b'previous panel',
             'usr/sbin/mu300-keys':b'previous key helper'}
        following=dict(current);following['usr/share/ucode/mu300/charger-boot.uc']+=b'\n// later update\n'
        saved={'etc/config/wireless':b'user Wi-Fi, client and AP choices',
               'etc/config/unisoc_modem':b'user SIM and radio permissions',
               'etc/unisoc-bluetooth/config.json':b'{"autostart":true,"alias":"paired gateway"}',
               'etc/config/mu300-charge':b'user charge thresholds, pause and auto start',
               'etc/config/u30pro_native_control':b'user screen wallpaper and lock',
               'etc/mu300/default-boot':b'linux\n','root/user.txt':b'keep'}
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);live=base/'live'
            for name,data in dict(old,**saved).items():
                p=live/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            (live/'etc/mu300/release.json').write_text(json.dumps(dict(profile='mu300',image_version='mu300-r1',kernel_release='7.2.8')))
            for index,files in enumerate((old,current,following),1):release(base/str(index),'mu300-r'+str(index),files)
            for index,files,original in ((1,current,old),(2,following,current)):
                patch=base/(str(index)+'.ota');result=analyze(base/str(index),base/str(index+1),patch)
                self.assertTrue(result['can_export'],result['blockers'])
                for roundtrip in range(2):
                    with Patch(patch) as archive:self.assertEqual(Engine(live).apply(archive)['status'],'complete')
                    for name,data in files.items():self.assertEqual((live/name).read_bytes(),data)
                    link=live/'etc/rc.d/S09u30pro-charge-mode'
                    self.assertTrue(link.is_symlink());self.assertEqual(os.readlink(link),'../init.d/u30pro-charge-mode')
                    for name,data in saved.items():self.assertEqual((live/name).read_bytes(),data)
                    if not roundtrip:
                        rollback=TOP/'installer/runtime/luci-app-unisoc-ota/root/usr/lib/unisoc-ota/engine.py'
                        p=subprocess.run([sys.executable,str(rollback),'rollback','--root',str(live)],capture_output=True,text=True)
                        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
                        for name,data in original.items():self.assertEqual((live/name).read_bytes(),data)
                        for name,data in saved.items():self.assertEqual((live/name).read_bytes(),data)


if __name__=='__main__':unittest.main()
