"""Run the production UCI backend in the existing target root, without hardware."""
from pathlib import Path
import subprocess
import tempfile

TOP=Path(__file__).resolve().parents[1]
ROOT=Path('/home/kano/openwrt-build/package-work/u30pro-release/root')
with tempfile.TemporaryDirectory(dir=ROOT/'tmp',prefix='wifi-relay-test-') as folder:
    test=Path(folder)/'test.uc'
    test.write_bytes((TOP/'tests/u30pro_wifi_native.uc').read_bytes())
    path='/tmp/'+Path(folder).name+'/test.uc'
    result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
        '-v',str(ROOT)+':/target','--entrypoint','/bin/sh','mu300-openwrt-base:25.12.5',
        '-ec','chroot /target /usr/bin/ucode '+path],text=True,capture_output=True,timeout=45)
    print(result.stdout,end='')
    if result.returncode:raise RuntimeError(result.stderr)
