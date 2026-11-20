'use strict';
'require view';
'require rpc';
'require poll';
'require mu300.common as M';

var status=rpc.declare({object:'u30pro-wifi-relay',method:'status',nobatch:true,expect:{'':{}}});
var start=rpc.declare({object:'u30pro-wifi-relay',method:'start',params:['action','ssid','password','encryption'],nobatch:true,expect:{'':{}}});
var words={
 'Wi-Fi 中继':['Wi-Fi uplink','Wi-Fi bağlantısı'],
 '连接其他 Wi-Fi，同时保留本机热点。屏幕与网页共用设置，无需重启。':['Connect to another Wi-Fi network while keeping this hotspot. The screen and web page share settings; no reboot is needed.','Bu erişim noktasını koruyarak başka bir Wi-Fi ağına bağlanın. Ekran ve web aynı ayarları kullanır; yeniden başlatma gerekmez.'],
 '连接状态':['Connection','Bağlantı'], '未配置':['Not configured','Yapılandırılmadı'],
 '已停用':['Disabled','Devre dışı'], '正在连接':['Connecting','Bağlanıyor'], '已连接':['Connected','Bağlandı'],
 '扫描网络':['Scan networks','Ağları tara'], '刷新状态':['Refresh status','Durumu yenile'],
 '已保存网络':['Saved network','Kayıtlı ağ'], '未保存':['None','Yok'],
 '连接已保存网络':['Connect saved network','Kayıtlı ağa bağlan'], '断开':['Disconnect','Bağlantıyı kes'],
 '忘记网络':['Forget network','Ağı unut'], '连接网络':['Connect to a network','Bir ağa bağlan'],
 '网络名称':['Network name','Ağ adı'], '密码':['Password','Parola'], '加密方式':['Security','Güvenlik'],
 '开放网络':['Open network','Açık ağ'], '保存并连接':['Save and connect','Kaydet ve bağlan'],
 '操作中…':['Working…','İşleniyor…'], '配置已应用，等待网络连接。':['Settings applied; waiting for connection.','Ayarlar uygulandı; bağlantı bekleniyor.'],
 '操作完成':['Done','Tamamlandı'], '操作失败':['Operation failed','İşlem başarısız'],
 '仅在点击时扫描。热点保留已设信道，由驱动协调并发；扫描或重新连接可能短暂影响无线性能。':['Scanning runs only when requested. The hotspot keeps its configured channel; the driver coordinates concurrent connections. Scanning or reconnecting may briefly affect wireless performance.','Tarama yalnızca istendiğinde yapılır. Erişim noktası ayarlı kanalını korur; sürücü eşzamanlı bağlantıları koordine eder. Tarama veya yeniden bağlanma kablosuz performansını kısa süreli etkileyebilir.'],
 '未找到网络，可手动输入隐藏网络。':['No networks found. You can enter a hidden network manually.','Ağ bulunamadı. Gizli ağı elle girebilirsiniz.'],
 '选择':['Choose','Seç'], '隐藏网络':['Hidden network','Gizli ağ'], '不支持企业认证':['Enterprise authentication is not supported','Kurumsal kimlik doğrulama desteklenmiyor'],
 '与蜂窝网络同时连接时，沿用网络接口的路由优先级；需要调整时请到网络接口设置。':['When cellular and Wi-Fi are both connected, interface route priorities apply. Change them in network interface settings.','Hücresel ve Wi-Fi bağlıyken arayüz yönlendirme öncelikleri kullanılır. Ağ arayüzü ayarlarından değiştirilebilir.'],
 '网络接口设置':['Network interface settings','Ağ arayüzü ayarları'],
 '可用网络':['Available networks','Kullanılabilir ağlar'],
 '尚未扫描网络':['No scan results yet','Henüz tarama sonucu yok'],
 '点击扫描查找附近 Wi-Fi，也可以在右侧手动输入网络。':['Scan for nearby Wi-Fi networks or enter a network manually.','Yakındaki Wi-Fi ağlarını tarayın veya ağı elle girin.'],
 '手动连接':['Manual connection','Elle bağlantı'],
 '选择扫描结果后，网络名称和加密方式会自动填入。':['Choosing a scan result fills in its network name and security.','Bir tarama sonucu seçildiğinde ağ adı ve güvenlik otomatik doldurulur.'],
 '上游地址':['Uplink address','Üst ağ adresi'],
 '请填写网络名称和有效密码。':['Enter a network name and valid password.','Ağ adını ve geçerli parolayı girin.'],
 '只读权限':['Read-only access','Salt okunur erişim'],
 '已有操作正在进行，请稍后重试。':['Another operation is running. Please retry shortly.','Başka bir işlem sürüyor. Biraz sonra tekrar deneyin.'],
 '上次操作被中断，请重试。':['The last operation was interrupted. Please retry.','Son işlem kesildi. Tekrar deneyin.']
};
function t(s){var lang=M.uiLanguage();return lang==='zh'?s:(words[s]||[s,s])[lang==='tr'?1:0];}
function node(tag,text,cls){var e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e;}
function signalIcon(signal){
 var ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('class','relay-signal');svg.setAttribute('aria-hidden','true');
 ['M3 8a14 14 0 0 1 18 0','M6 12a9 9 0 0 1 12 0','M9 16a4 4 0 0 1 6 0','M12 20h0'].forEach(function(d,i){var p=document.createElementNS(ns,'path');p.setAttribute('d',d);p.setAttribute('fill','none');p.setAttribute('stroke','currentColor');p.setAttribute('stroke-width','2');p.setAttribute('stroke-linecap','round');p.setAttribute('opacity',signal!=null&&signal<[-60,-72,-85,-100][i]?'.2':'1');svg.append(p);});return svg;
}
function securityLabel(mode){return {none:t('开放网络'),owe:'OWE',psk2:'WPA2',sae:'WPA3','sae-mixed':'WPA2/WPA3'}[mode]||t('不支持企业认证');}
function security(ap){var e=ap.encryption||{};if(!e.enabled)return 'none';var auth=e.authentication||[],wpa=e.wpa||[];if(auth.includes('eap'))return null;if(auth.includes('owe'))return 'owe';if(auth.includes('sae'))return wpa.includes(2)?'sae-mixed':'sae';return auth.includes('psk')||wpa.includes(2)?'psk2':null;}
function errorText(error){return t({relay_busy:'已有操作正在进行，请稍后重试。',relay_job_interrupted:'上次操作被中断，请重试。',invalid_relay_ssid:'请填写网络名称和有效密码。',invalid_relay_key:'请填写网络名称和有效密码。'}[error]||'操作失败')+(error?' · '+error:'');}
return view.extend({
 load:function(){return status();},
 render:function(initial){
  M.injectCss();
  var root=node('div',null,'relay'),writable=L.hasViewPermission(),busy=false,current={},loading=false,lastJob='';
  var css=node('link');css.rel='stylesheet';css.href=L.resource('mu300/wifi-relay.css');root.append(css);
  var header=node('div',null,'relay-header'),copy=node('div');copy.append(node('h2',t('Wi-Fi 中继')),node('p',t('连接其他 Wi-Fi，同时保留本机热点。屏幕与网页共用设置，无需重启。'),'relay-note'));header.append(copy);root.append(header);
  var connection=node('section',null,'relay-panel relay-connection'),grid=node('div',null,'relay-grid'),left=node('section',null,'relay-panel'),right=node('section',null,'relay-panel');root.append(connection,grid);grid.append(left,right);
  var state=node('span',null,'relay-state'),saved=node('strong',null,'relay-saved'),address=node('div',null,'relay-address'),message=node('p',null,'relay-message');message.setAttribute('role','status');message.hidden=true;
  var buttons=[];
  function button(text,fn,write){var b=node('button',t(text));b.type='button';b.onclick=fn;b.needsWrite=write;buttons.push(b);return b;}
  function controls(){buttons.forEach(function(b){b.disabled=busy||b.unavailable||(b.needsWrite&&!writable);});resume.disabled=busy||!writable||!current.configured||current.enabled;disconnect.disabled=busy||!writable||!current.enabled;forget.disabled=busy||!writable||!current.configured;}
  var resume=button('连接已保存网络',()=>operate('up'),true),disconnect=button('断开',()=>operate('disconnect'),true),forget=button('忘记网络',()=>operate('forget'),true);
  var actions=node('div',null,'relay-actions');actions.append(resume,disconnect,forget);header.append(button('刷新状态',()=>refresh(false),false));
  var connectionCopy=node('div',null,'relay-connection-copy'),stateRow=node('div',null,'relay-state-row');stateRow.append(node('h3',t('连接状态')),state);connectionCopy.append(stateRow,saved,address);connection.append(connectionCopy,actions,message);
  var scanHead=node('div',null,'relay-section-head'),list=node('div',null,'relay-list'),scanButton=button('扫描网络',()=>operate('scan'),true);scanButton.dataset.action='scan';
  scanHead.append(node('h3',t('可用网络')),scanButton);var empty=node('div',null,'relay-empty');empty.append(node('strong',t('尚未扫描网络')),node('p',t('点击扫描查找附近 Wi-Fi，也可以在右侧手动输入网络。'),'relay-note'));list.append(empty);
  left.append(scanHead,node('p',t('仅在点击时扫描。热点保留已设信道，由驱动协调并发；扫描或重新连接可能短暂影响无线性能。'),'relay-note'),list);
  var fields=node('div',null,'relay-fields'),ssid=node('input'),password=node('input'),encryption=node('select');
  ssid.autocomplete='off';ssid.maxLength=32;password.type='password';password.autocomplete='new-password';password.maxLength=64;
  [['psk2','WPA2-PSK'],['sae-mixed','WPA2/WPA3'],['sae','WPA3-SAE'],['none',t('开放网络')],['owe','OWE']].forEach(function(pair){var o=node('option',pair[1]);o.value=pair[0];encryption.append(o);});
  function field(label,control){var l=node('label');l.append(node('span',t(label)),control);fields.append(l);return l;}
  field('网络名称',ssid);field('加密方式',encryption);var passField=field('密码',password);
  encryption.onchange=function(){passField.hidden=['none','owe'].includes(encryption.value);if(passField.hidden)password.value='';};
  var connect=button('保存并连接',function(){
   var key=password.value,open=['none','owe'].includes(encryption.value),hex=/^[a-f0-9]{64}$/i.test(key);
   if(!ssid.value||new TextEncoder().encode(ssid.value).length>32||/[\x00\r\n]/.test(ssid.value)||(!open&&!(key.length>=8&&key.length<=63||encryption.value==='psk2'&&hex))){notify(t('请填写网络名称和有效密码。'));return;}
   operate('connect',ssid.value,open?'':key,encryption.value);
  },true);
  connect.className='relay-primary';connect.dataset.action='connect';
  right.append(node('h3',t('手动连接')),node('p',t('选择扫描结果后，网络名称和加密方式会自动填入。'),'relay-note'),fields,node('div',null,'relay-actions'));right.lastChild.append(connect);
  var routing=node('div',null,'relay-routing'),link=node('a',t('网络接口设置'));link.href=L.url('admin/network/network');routing.append(node('p',t('与蜂窝网络同时连接时，沿用网络接口的路由优先级；需要调整时请到网络接口设置。'),'relay-note'),link);right.append(routing);
  if(!writable){right.append(node('p',t('只读权限'),'relay-note'));ssid.disabled=password.disabled=encryption.disabled=true;}
  function notify(text){message.textContent=text;message.hidden=!text;}
  function paint(reply){
   if(!reply||!reply.ok)throw Error(errorText(reply&&reply.error));
   current=reply.state||{};if(current.ok===false)throw Error(errorText(current.error));
   state.textContent=t(!current.configured?'未配置':!current.enabled?'已停用':current.state===2?'已连接':'正在连接');state.dataset.state=!current.enabled?'disabled':current.state===2?'connected':'connecting';saved.textContent=current.cfg||t('未保存');address.replaceChildren();if(current.address)address.append(node('span',t('上游地址')),node('span',current.address));address.hidden=!current.address;
   var job=reply.job||{};busy=!!job.pending;
   if(busy)notify(t('操作中…'));
   var fingerprint=JSON.stringify(job);
   if(!busy&&job.action&&lastJob!==fingerprint){
    lastJob=fingerprint;notify(job.ok===false?errorText(job.error):t(job.action==='connect'||job.action==='up'?'配置已应用，等待网络连接。':'操作完成'));
    if(job.action==='scan'&&job.ok!==false){
     buttons=buttons.filter(b=>!b.scanChoice);list.replaceChildren();var results=(job.results||[]).slice().sort((a,b)=>(b.signal||-100)-(a.signal||-100));
     if(!results.length)list.append(node('p',t('未找到网络，可手动输入隐藏网络。'),'relay-empty relay-note'));
     results.forEach(function(ap){var row=node('div',null,'relay-network'),info=node('div',null,'relay-network-info'),mode=security(ap),choose=button('选择',function(){ssid.value=ap.ssid||'';encryption.value=mode||'psk2';encryption.onchange();if(!passField.hidden)password.focus();else ssid.focus();},true);choose.scanChoice=true;choose.unavailable=mode==null;choose.disabled=!writable||choose.unavailable;info.append(node('strong',ap.ssid||t('隐藏网络')),node('small',securityLabel(mode)+' · '+(ap.signal==null?'--':ap.signal)+' dBm'));info.title=ap.bssid||'';row.append(signalIcon(ap.signal),info,choose);list.append(row);});
    }
   }
   if(!ssid.value&&current.cfg)ssid.value=current.cfg;controls();
  }
  function refresh(silent){if(loading||document.hidden)return Promise.resolve();loading=true;return status().then(paint).catch(function(e){if(!silent)notify(e.message);}).finally(function(){loading=false;});}
  function operate(action,name,key,mode){if(busy||!writable)return;busy=true;controls();notify(t('操作中…'));return start(action,name||'',key||'',mode||'').then(function(r){if(!r||!r.ok)throw Error(errorText(r&&r.error));if(action==='connect')password.value='';return refresh(false);}).catch(function(e){busy=false;notify(e.message);controls();});}
  paint(initial);poll.add(()=>refresh(true),4);return root;
 },handleSaveApply:null,handleSave:null,handleReset:null
});
