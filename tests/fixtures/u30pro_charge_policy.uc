import * as policy from 'mu300.charger-boot';
let count=0;
function check(value) { if (!value) die('charger policy assertion failed: '+count+'\n'); count++; }
for (let model in ['u30pro','f50pro','u30air','mu300',''])
for (let automatic in [null,'0','1'])
for (let failsafe in [false,true])
for (let boot in ['sprdboot.mode=charger','androidboot.mode=charger','sprdboot.mode=normal',
    'not.sprdboot.mode=charger','sprdboot.mode=charger-extra']) {
    let want=model=='u30pro' && automatic!='1' && !failsafe &&
        boot in ['sprdboot.mode=charger','androidboot.mode=charger'];
    check(policy.charging(model,'console=ttyS1\n'+boot+'\x00',automatic,failsafe)==want);
}
for (let i=0;i<10000;i++) {
    check(policy.charging('u30pro','\nmodem=shutdown\nandroidboot.mode=charger\x00','0',false));
    check(policy.outcome(i%4)==(i%4==3 ? 'poweroff' : i%4==0 ? 'boot' : 'unavailable'));
}
print(sprintf('%J\n',{assertions:count,hardware_accessed:false}));
