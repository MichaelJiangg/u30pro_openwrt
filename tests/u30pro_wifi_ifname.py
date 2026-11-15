#!/usr/bin/env python3
"""Run the production AP binding migration with real UCI in an isolated root."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

TOP=Path(__file__).resolve().parents[1]
SCENARIO=r'''
from pathlib import Path
import copy,json,os,subprocess
case=Path('/case'); config=case/'config';config.mkdir()
binary='/target/usr/bin/ucode'
source=Path('/repo/devices/u30pro/overlay/usr/libexec/u30pro-wifi-ifname').read_text().split('\n',1)[1]
prefix="""import { cursor as fixture_cursor } from 'uci';
function cursor() {
    let c=fixture_cursor('/case/config');
    if(getenv('FIXTURE_PENDING')=='1') c.set('wireless','radio0','channel','44');
    return c;
}
"""
script=case/'migration.uc'
script.write_text(prefix+source.replace("import { cursor } from 'uci';",""))
query="import { cursor } from 'uci'; let u=cursor('/case/config'); printf('%J',u.get_all('wireless'));"
def snapshot():
    return json.loads(subprocess.check_output([binary,'-e',query],text=True))
for name,channel,mode,binding,extra,pending in [
    ('saved-44',44,'ap','',False,False),
    ('saved-149',149,'ap','',False,False),
    ('custom-name',149,'ap','myap0',False,False),
    ('client-role',44,'sta','',False,False),
    ('occupied-name',149,'ap','',True,False),
    ('pending-change',149,'ap','',False,True),
]:
    text=("config wifi-device 'radio0'\n option type 'mac80211'\n option band '5g'\n"
          " option channel '"+str(channel)+"'\n option country 'CN'\n option htmode 'HE80'\n"
          "config wifi-iface 'default_radio0'\n option device 'radio0'\n"
          " option mode '"+mode+"'\n option ssid 'Saved AP'\n"
          " option encryption 'psk2'\n option key 'saved-password'\n option network 'lan'\n")
    if binding:text+=" option ifname '"+binding+"'\n"
    if extra:text+="config wifi-iface 'custom_sta'\n option device 'radio0'\n option mode 'sta'\n option ifname 'wlan0'\n"
    (config/'wireless').write_text(text)
    before=snapshot(); expected=copy.deepcopy(before)
    change=mode=='ap' and not binding and not extra and not pending
    if change:expected['default_radio0']['ifname']='wlan0'
    env=dict(os.environ,FIXTURE_PENDING='1' if pending else '0')
    result=subprocess.run([binary,str(script)],env=env,capture_output=True,text=True)
    assert (result.returncode!=0)==(extra or pending),(name,result.stdout,result.stderr)
    assert snapshot()==expected,(name,before,snapshot())
    saved=(config/'wireless').read_bytes()
    if extra or pending:
        assert saved==text.encode(),name
    else:
        subprocess.run([binary,str(script)],env=env,check=True)
        assert (config/'wireless').read_bytes()==saved,name
    assert 'saved-password' not in result.stdout+result.stderr
    print('PASS',name,': channel, credentials, bandwidth and custom choices retained',flush=True)
template=Path('/repo/devices/u30pro/overlay/etc/config/wireless').read_text()
assert "option ifname 'wlan0'" in template
print('PASS fresh Pro/F50 Pro default interface binding',flush=True)
'''

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--image',required=True)
    args=parser.parse_args();root=args.root.resolve()
    if root==Path('/') or not (root/'etc/openwrt_release').is_file():
        raise ValueError('Use an existing prepared OpenWrt root')
    with tempfile.TemporaryDirectory(prefix='pro-wifi-ifname-',dir=os.environ.get('TMPDIR')) as directory:
        path=Path(directory);(path/'scenario.py').write_text(SCENARIO)
        subprocess.run(['docker','run','--rm','--platform','linux/arm64','--network','none',
            '-v',str(root)+':/target:ro','-v',str(TOP)+':/repo:ro','-v',str(path)+':/case',
            '-e','PYTHONHOME=/target/usr','-e','PYTHONDONTWRITEBYTECODE=1',
            '-e','LD_LIBRARY_PATH=/target/usr/lib:/target/lib',
            '--entrypoint','/target/usr/bin/python3',args.image,'-B','/case/scenario.py'],
            check=True,timeout=45)

if __name__=='__main__':main()
