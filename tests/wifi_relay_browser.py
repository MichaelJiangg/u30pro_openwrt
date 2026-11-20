"""Actual LuCI view: manual scans, safe SSIDs, responsive layout and permissions."""
from pathlib import Path
from playwright.sync_api import sync_playwright

TOP=Path(__file__).resolve().parents[1]
common=(TOP/'openwrt/luci-app-mu300/htdocs/luci-static/resources/mu300/common.js').read_text(encoding='utf-8')
source=(TOP/'devices/u30pro/overlay/www/luci-static/resources/view/mu300/wifi-relay.js').read_text(encoding='utf-8')
css=(TOP/'devices/u30pro/overlay/www/luci-static/resources/mu300/wifi-relay.css').read_text(encoding='utf-8')
out=TOP/'work/wifi-relay-preview';out.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe')
    for lang in ('zh','en','tr'):
        for width in (360,1280):
            page=browser.new_page(viewport=dict(width=width,height=1000));errors=[]
            page.route('https://relay.test/resources/mu300/wifi-relay.css',lambda route:route.fulfill(content_type='text/css',body=css))
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.set_content('<style>:root{--surface:#151922;--surface-sunken:#0b1018;--text:#e3e8ef;--text-muted:#929baa;--text-subtle:#7d8795;--hairline:#303642;--brand:#00b9b0;--success:#32c48d;--hover-faint:#202733}body{background:#080b11;color:#ddd;font:14px sans-serif;margin:24px}button,input,select{font:inherit;color:inherit;background:#10151d;border:1px solid #333946;border-radius:8px;padding:9px}.mud-card{background:#151922;border:1px solid #30343e;border-radius:16px}.mud-note{color:#9098a6;line-height:1.65}a{color:#11b6ad}</style><main></main>')
            page.evaluate('''({common,source,lang})=>{
                window.L={env:{lang},url:p=>'/'+p,resource:p=>'https://relay.test/resources/'+p,hasViewPermission:()=>!window.readonly};
                window.operations=[];window.ticks=[];
                window.reply={ok:true,state:{configured:true,enabled:false,cfg:'Home Wi-Fi',state:0},job:{}};
                const rpc={declare:o=>(...args)=>{
                    if(o.method==='status')return Promise.resolve(structuredClone(reply));
                    operations.push(args);
                    if(args[0]==='scan')reply.job={ok:true,pending:false,action:'scan',results:[
                        {ssid:'<img src=x onerror=alert(1)>',bssid:'02:01:02:03:04:05',signal:-45,encryption:{enabled:true,wpa:[2],authentication:['psk']}},
                        {ssid:'Enterprise',bssid:'02:01:02:03:04:06',signal:-60,encryption:{enabled:true,wpa:[2],authentication:['eap']}}
                    ]};
                    else if(args[0]==='connect'){reply.state.enabled=true;reply.state.cfg=args[1];reply.job={ok:true,pending:false,action:'connect'};}
                    return Promise.resolve({ok:true,pending:true});
                }};
                window.M=new Function('rpc','baseclass','L',common)(rpc,{extend:x=>x},L);
                window.widget=new Function('view','rpc','poll','M','L',source)({extend:x=>x},rpc,{add:f=>ticks.push(f)},M,L);
                document.querySelector('main').append(widget.render(reply));
            }''',dict(common=common,source=source,lang=lang))
            assert page.evaluate('operations.length')==0
            page.evaluate('ticks[0]()');page.wait_for_timeout(20)
            assert page.evaluate('operations.length')==0  # status refresh never scans
            page.locator('[data-action=scan]').click()  # explicit scan
            page.wait_for_selector('.relay-network')
            assert page.locator('.relay-network').count()==2
            assert page.locator('img').count()==0
            assert page.locator('.relay-network button').nth(1).is_disabled()
            page.locator('.relay-network button').first.click()
            assert page.locator('input').first.input_value().startswith('<img')
            page.locator('input[type=password]').fill('valid-passphrase')
            page.locator('[data-action=connect]').click()
            page.wait_for_function('operations.length===2')
            assert page.evaluate('operations[1].slice(0,2)')==['connect','<img src=x onerror=alert(1)>']
            assert page.locator('input[type=password]').input_value()==''
            page.wait_for_function("getComputedStyle(document.querySelector('.relay')).maxWidth==='1000px'")
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            assert page.locator('.relay-header').evaluate("e=>getComputedStyle(e).position")=='static'
            assert page.locator('.relay-grid').evaluate("e=>getComputedStyle(e).gridTemplateColumns.split(' ').length")==(1 if width==360 else 2)
            if lang!='zh':assert not page.locator('main').evaluate('e=>/[\u4e00-\u9fff]/.test(e.textContent)')
            if lang=='zh':
                page.evaluate("""()=>{reply.state={configured:true,enabled:true,cfg:'Home Wi-Fi',state:2,address:'192.0.2.3'};reply.job={ok:true,pending:false,action:'scan',results:[{ssid:'Home Wi-Fi',bssid:'02:01:02:03:04:05',signal:-45,encryption:{enabled:true,wpa:[2],authentication:['psk']}},{ssid:'Guest Wi-Fi',bssid:'02:01:02:03:04:06',signal:-68,encryption:{enabled:false}}]};document.querySelector('main').replaceChildren(widget.render(reply));}""")
                page.screenshot(path=str(out/('web-mobile.png' if width==360 else 'web-desktop.png')),full_page=True)
            page.evaluate("reply.job={pending:true,action:'scan'};ticks[ticks.length-1]()")
            page.wait_for_timeout(20)
            assert page.locator('[data-action=scan]').is_disabled()
            assert page.locator('[data-action=connect]').is_disabled()
            page.evaluate("reply.job={};ticks[ticks.length-1]()")
            page.wait_for_timeout(20)
            page.evaluate("readonly=true;document.querySelector('main').replaceChildren(widget.render(reply))")
            assert page.locator('input').first.is_disabled()
            assert page.locator('[data-action=scan]').is_disabled()
            assert not errors,errors
            page.close()
    browser.close()
print('PASS relay view: zh/en/tr desktop/mobile, explicit scans only, safe SSIDs, security choices and read-only access')
