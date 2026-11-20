// U30 Pro STA integration. netifd/wpad own interfaces, DHCP, DNS and routing.
// No direct wpa_supplicant process, SC2355 workaround or second setting store.
import { error as bus_error } from 'ubus';
function interfaces(c) {
    let rows=[];
    c.foreach('wireless','wifi-iface',s=>{if(s.mode=='sta')push(rows,s);});
    return rows;
}
function selected(c) {
    let rows=interfaces(c), chosen=c.get('unisoc_modem','main','wifi_client_iface');
    if(chosen) {
        let found=filter(rows,s=>s['.name']==chosen);
        if(length(found)!=1)die('Selected client interface is unavailable / 所选客户端接口不存在');
        return found[0];
    }
    if(length(rows)>1)die('Select the client interface first / 存在多个客户端接口，请先选择');
    return rows[0];
}
export function status(c,bus) {
    let s=selected(c), configured=length(s?.ssid || '')>0;
    let result={configured,section:s?.['.name'],enabled:configured && s.disabled!='1' && c.get('wireless',s.device,'disabled')!='1',
        cfg:s?.ssid || '',ssid:'',state:0,device:s?.ifname || 'wlan1',address:null};
    if(!result.enabled)return result;
    result.state=1;
    let radio=bus.call('network.wireless','status',{})?.[s.device];
    for(let i in radio?.interfaces || [])if(i.section==s['.name'])result.device=i.ifname;
    let network=s.network;
    if(type(network)=='array')network=network[0];
    let association=bus.call('iwinfo','info',{device:result.device});
    if(association?.ssid!=s.ssid || !association.bssid || association.bssid=='00:00:00:00:00:00')return result;
    if(type(network)=='string' && match(network,/^[A-Za-z0-9_]+$/)) {
        let link=bus.call('network.interface.'+network,'status',{}) || {};
        let addresses=[...(link['ipv4-address'] || []),...(link['ipv6-address'] || [])];
        if(link.up && length(addresses)) {
            result.state=2;result.ssid=s.ssid;result.address=addresses[0].address;
        }
    }
    return result;
};
function check_pending(c) {
    for(let config in ['wireless','network','firewall'])
        if(length(c.changes(config) || {}))die('Resolve unsaved network changes first / 请先保存或撤销网络页面的更改');
}
function apply(c,bus) {
    for(let config in ['network','firewall','wireless'])
        if(length(c.changes(config) || {}) && !c.commit(config))die('Cannot save network settings / 无法保存网络配置');
    bus.call('network','reload',{});
    // A successful reload is allowed to return no body; the ubus error is
    // authoritative, as in the shared APN reconnect implementation.
    if(bus_error(true))die('Settings saved; network reload failed / 配置已保存，但网络应用失败');
    return {ok:true,pending:true};
}
export function dispatch(c,bus,action,args) {
    if(action=='status')return status(c,bus);
    if(action=='scan') {
        let iface=c.get('unisoc_modem','main','wifi_device') || 'wlan0';
        let found=bus.call('iwinfo','scan',{device:iface});
        if(found==null)die('Wireless scan failed / 无线扫描失败');
        return {ok:true,results:found.results || []};
    }
    let s=selected(c);
    check_pending(c);
    if(action=='connect') {
        let ssid=args[0], password=args[1] || '', encryption=args[2] || (password==''?'none':match(password,/^[0-9A-Fa-f]{64}$/)?'psk2':'sae-mixed');
        if(type(ssid)!='string' || length(ssid)<1 || length(ssid)>32 || index(ssid,'\x00')>=0 || match(ssid,/[\r\n]/))
            die('Invalid SSID / 热点名称无效');
        if(type(password)!='string' || (password!='' &&
            !((length(password)>=8 && length(password)<=63 && index(password,'\x00')<0 && !match(password,/[\r\n]/)) || match(password,/^[0-9A-Fa-f]{64}$/))))
            die('Invalid Wi-Fi key / Wi-Fi 密码无效');
        if(!(encryption in ['none','psk2','sae','sae-mixed','owe']) ||
            ((encryption=='none' || encryption=='owe') && password!='') ||
            ((encryption=='psk2' || encryption=='sae' || encryption=='sae-mixed') && password=='') ||
            (encryption!='psk2' && length(password)==64))die('Invalid Wi-Fi security / Wi-Fi 加密设置无效');
        let radio=c.get('unisoc_modem','main','wifi_radio') || 'radio0';
        if(c.get('wireless',radio)!='wifi-device')die('Wireless radio unavailable / 无线电不存在');
        if(!s) {
            if(c.get('wireless','wwan')!=null)die('The wwan section is already used / wwan 配置节已被占用');
            if(c.get('network','wwan')==null) {
                c.set('network','wwan','interface');c.set('network','wwan','proto','dhcp');c.set('network','wwan','metric','40');
            } else if(c.get('network','wwan')!='interface')die('Client uplink is unavailable / 客户端上行接口不存在');
            let zone=null;
            c.foreach('firewall','zone',z=>{if(z.name=='wan')zone=z;});
            if(!zone)die('WAN firewall zone unavailable / WAN 防火墙区域不存在');
            let networks=zone.network || [];
            if(type(networks)=='string')networks=split(networks,' ');
            if(index(networks,'wwan')<0)c.set('firewall',zone['.name'],'network',[...networks,'wwan']);
            c.set('wireless','wwan','wifi-iface');
            c.set('wireless','wwan','mode','sta');
            c.set('wireless','wwan','device',radio);
            c.set('wireless','wwan','network','wwan');
            c.set('wireless','wwan','ifname','wlan1');
            s=c.get_all('wireless','wwan');
        }
        c.set('wireless',s['.name'],'ssid',ssid);
        c.set('wireless',s['.name'],'encryption',encryption);
        if(password=='')c.delete('wireless',s['.name'],'key');
        else c.set('wireless',s['.name'],'key',password);
        c.set('wireless',s['.name'],'disabled','0');
    } else if(action=='up') {
        if(!length(s?.ssid || ''))die('No saved Wi-Fi network / 没有已保存的 Wi-Fi 网络');
        c.set('wireless',s['.name'],'disabled','0');
    } else if(action=='disconnect') {
        if(!s)return {ok:true,unchanged:true};
        c.set('wireless',s['.name'],'disabled','1');
    } else if(action=='forget') {
        if(!s)return {ok:true,unchanged:true};
        c.delete('wireless',s['.name']);
    } else die('Unknown Wi-Fi action / 未知 Wi-Fi 操作');
    return apply(c,bus);
};
