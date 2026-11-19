"""Execute MU300's actual key dispatch block with deterministic command results."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP=Path(__file__).resolve().parents[1]
SOURCE=TOP/'rootfs/overlay/opt/mu300/bin/mu300-sysd'


@unittest.skipUnless(os.name=='posix' and os.environ.get('MU300_TEST_RUNTIME_IMAGE'),
                     'select a prepared ARM64 OpenWrt image with ucode/socket via MU300_TEST_RUNTIME_IMAGE')
class ButtonEvents(unittest.TestCase):
    def test_entire_service_compiles_with_target_ucode(self):
        result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
            '-v',str(SOURCE)+':/service.uc:ro','--entrypoint','/usr/bin/ucode',
            os.environ['MU300_TEST_RUNTIME_IMAGE'],'-c','/service.uc','-o','/tmp/service.ucb'],
            capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_default_custom_and_power_hold_use_the_original_owner(self):
        source=SOURCE.read_text()
        block=source[source.index('const KEY_POWER'):source.index('// The existing LED helper owns')]
        prefix="""
const R='', BIN='/opt/mu300/bin',parts={};
let calls=[],custom_result=0,timers=[];
const uloop={timer:(ms,cb)=>{let t={run:cb,cancelled:false};t.cancel=()=>{t.cancelled=true;};push(timers,t);return t;}};
function flush(){let pending=timers;timers=[];for(let t in pending)if(!t.cancelled)t.run();}
function num(k,v){return v;}
function readfile(p){return 'f50pro';}
function exists(p){return p=='/etc/openwrt_release';}
function rd(p){return '10.00';}
function digits(s){return true;}
function deadline(s,p){return null;}
function idle_check(){}
function log(tag,text){}
function spawn(argv,cb){
 push(calls,argv);if(cb)cb(argv[0]=='/usr/libexec/unisoc-modem/buttons'?custom_result:0);
 return null;
}
"""
        suffix="""
function check(yes,msg){if(!yes)die(msg);}
press(KEY_WIFI,'short');flush();
check(length(calls)==1&&calls[0][0]=='/opt/mu300/bin/f50pro-key-action'&&calls[0][1]=='short','short lost');
calls=[];press(KEY_WIFI,'short');press(KEY_WIFI,'short');flush();
check(length(calls)==1&&calls[0][1]=='double','double emitted singles');
calls=[];press(KEY_WIFI,'long');flush();
check(length(calls)==1&&calls[0][1]=='long','function hold lost');
calls=[];press(KEY_POWER,'long');flush();
check(length(calls)==0,'F50 Pro entered inherited power policy');
print('PASS F50 Pro short/double/long: no inherited power actions');
"""
        with tempfile.TemporaryDirectory() as folder:
            test=Path(folder)/'events.uc';test.write_text(prefix+block+suffix)
            result=subprocess.run(['docker','run','--rm','--pull','never','--platform','linux/arm64','--network','none',
                '-v',str(test)+':/test.uc:ro','--entrypoint','/usr/bin/ucode',
                os.environ['MU300_TEST_RUNTIME_IMAGE'],'/test.uc'],capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)


if __name__=='__main__':unittest.main()
