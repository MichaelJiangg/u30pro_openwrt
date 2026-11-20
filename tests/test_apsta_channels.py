"""Execute the real hostapd policy: MCC keeps AP alive; SCC follows STA."""
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
ROOT = Path('/home/kano/openwrt-build/package-work/u30pro-release/root')
CACHE = os.environ.get('UNISOC_APSTA_CACHE')


@unittest.skipUnless(CACHE and ROOT.is_dir(), 'explicit OpenWrt source cache required')
class Channels(unittest.TestCase):
    def test_real_apsta_events_and_creation_respect_driver_concurrency(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tmp', prefix='apsta-channels-') as temp:
            folder = Path(temp)
            for name, source in {
                'common.uc':'package/network/config/wifi-scripts/files/usr/share/hostap/common.uc',
                'hostapd.uc':'package/network/services/hostapd/files/hostapd.uc',
                'ap.uc':'package/network/config/wifi-scripts/files-ucode/usr/share/ucode/wifi/ap.uc',
                'supplicant.uc':'package/network/config/wifi-scripts/files-ucode/usr/share/ucode/wifi/supplicant.uc',
            }.items():
                raw = subprocess.check_output(['docker','run','--rm','--pull','never',
                    '--network','none','-v','e5-openwrt-src:/build:ro','--entrypoint','cat',
                    'unisoc-hostapd-build',CACHE+'/'+source])
                (folder/name).write_bytes(raw)
            patch = runpy.run_path(str(TOP/'openwrt/patch-hostapd-sae.py'))
            for _ in range(2):
                patch['patch_fullmac'](folder/'common.uc')
                patch['patch_reload'](folder)
                patch['patch_apsta_ap'](folder/'ap.uc')
                patch['patch_apsta_supplicant'](folder/'supplicant.uc')
            common = (folder/'common.uc').read_text()
            helper = 'function phy_supports_ap_sta_mcc'+common.split('function phy_supports_ap_sta_mcc',1)[1].split('function wdev_set_radio_mask',1)[0]
            host = (folder/'hostapd.uc').read_text()
            start = host.index('function iface_add(')
            create = host[start:host.index('\nfunction iface_config_macaddr_list',start)]
            handler = host.split('\tapsta_state: {',1)[1].split('\n\tconfig_get_macaddr_list:',1)[0]
            ap_flag = (folder/'ap.uc').read_text().split('config.start_disabled = ',1)[1].split(';',1)[0]
            supplicant = (folder/'supplicant.uc').read_text()
            frequency = supplicant[supplicant.index('function freq_in_range('):supplicant.index('export function generate(')]
            scan_start = supplicant.index('\tif (!data.config.scan_list)')
            scan = supplicant[scan_start:supplicant.index('\n\tif (data.config.scan_list)',scan_start)]
            code = r'''
let caps, indexes = {'/sys/class/ieee80211/phy0/index':'0\n'};
let starts=0, stops=0, switches=0, generated=null;
let libubus={STATUS_INVALID_ARGUMENT:2,STATUS_UNKNOWN_ERROR:9};
function readfile(p) { return indexes[p]; }
let nl80211={const:{},request:function(){return caps;}};
'''+helper+'\nfunction ap_flag(data) {return '+ap_flag+';}\n'+r'''
function phy_name(p,r) {return p;}
function iface_gen_config(c, disabled) {generated={channel:c.radio.channel,disabled};return 'inline';}
function iface_freq_info(iface,c,p) {return {frequency:p.frequency};}
let iface={stop:function(){stops++;},start:function(){starts++;return true;},switch_channel:function(){switches++;return true;}};
let config={radio:{channel:36},bss:[{ifname:'wlan0'}]};
let hostapd={data:{config:{phy0:config}},interfaces:{phy0:iface},add_iface:function(){return 0;}};
'''+create+'\nlet policy={apsta_state:{'+handler+r'''};
let phyinfo={wiphy_bands:[{freqs:[{freq:2412}]},{freqs:[{freq:5180},{freq:5745,disabled:true}]}]};
function wiphy_info(p) {return phyinfo;}
function wiphy_band(p,b) {return p.wiphy_bands[b=='2g'?0:1];}
'''+frequency+'\nfunction scan_config(data,interface) {'+scan+'}\n'+r'''
function check(value,message) {if(!value)die(message);}
function combo(channels,limits) {return {maxnum:2,num_channels:channels,limits};}
let separate=[{max:1,types:{ap:true}},{max:1,types:{managed:true}}];
function event(up,frequency) {return policy.apsta_state.call({args:{phy:'phy0',radio:-1,up,frequency,csa:true}});}
caps={interface_combinations:[combo(3,separate)]};
check(phy_supports_ap_sta_mcc('phy0.0'),'physical PHY behind radio suffix');
check(!ap_flag({phy:'phy0',ap_start_disabled:true}),'MCC generator must not disable AP while waiting for STA');
let data={phy:'phy0',config:{band:'2g'}};
scan_config(data,{config:{mode:'sta'}});
check(join(',',data.config.scan_list)=='2412,5180','MCC scans both legal bands, omitting disabled 149');
data.config.scan_list=[5180];scan_config(data,{config:{mode:'sta'}});
check(join(',',data.config.scan_list)=='5180','explicit user scan list is preserved');
phyinfo.wiphy_bands[1].freqs[1].disabled=false;
data.config.scan_list=null;scan_config(data,{config:{mode:'sta'}});
check(join(',',data.config.scan_list)=='2412,5180,5745','149 included only when kernel allows it');
check(iface_add('phy0',config,{state:'COMPLETED',frequency:5745}),'AP creation with a connected STA');
check(generated.channel==36 && !generated.disabled,'MCC AP starts on its own configured channel');
for(let upstream in [5180,5745,2412]) {
 check(event(false,0)==0,'scanning or failed authentication');
 check(event(true,upstream)==0,'STA association on same, other or different-band channel');
}
check(!starts && !stops && !switches,'MCC must not stop or retune AP or bypass its country settings');
caps={interface_combinations:[combo(1,separate)]};
check(!phy_supports_ap_sta_mcc('phy0'),'single-channel radio');
check(ap_flag({phy:'phy0',ap_start_disabled:true}),'SCC generator preserves its deferred-start flag');
data.config.scan_list=null;scan_config(data,{config:{mode:'sta'}});
check(join(',',data.config.scan_list)=='2412','SCC retains its configured band');
check(iface_add('phy0',config,{state:'COMPLETED',frequency:5180}),'SCC AP creation');
check(generated.disabled && starts==1,'SCC creation retains existing follow-STA path');
event(false,0);event(true,5180);
check(stops==1 && switches==1,'SCC stop and CSA preserved');
caps={interface_combinations:[combo(3,[{max:1,types:{ap:true,managed:true}}])]};
check(!phy_supports_ap_sta_mcc('phy0'),'one shared slot cannot run both roles');
caps={interface_combinations:[combo(3,[{max:2,types:{ap:true,managed:true}}])]};
check(phy_supports_ap_sta_mcc('phy0'),'two shared slots can run both roles');
caps={interface_combinations:[combo(3,[{max:2,types:{ap:true}}]),combo(3,[{max:2,types:{managed:true}}])]};
check(!phy_supports_ap_sta_mcc('phy0'),'roles must fit the same combination');
caps=null;check(!phy_supports_ap_sta_mcc('phy0'),'missing capability does not enable MCC');
check(!phy_supports_ap_sta_mcc('missing'),'missing PHY does not enable MCC');
print('PASS real APSTA policy: same/other/band channels, missing uplink, MCC creation, SCC behavior and capacity limits\n');
'''
            (folder/'test.uc').write_text(code)
            result = subprocess.run(['docker','run','--rm','--pull','never','--network','none',
                '--platform','linux/arm64','-v',str(ROOT)+':/target','--entrypoint','/bin/sh',
                'mu300-openwrt-base:25.12.5','-ec','chroot /target /usr/bin/ucode /tmp/'+folder.name+'/test.uc'],
                capture_output=True,text=True,timeout=40)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            print(result.stdout,end='')


if __name__ == '__main__':
    unittest.main()
