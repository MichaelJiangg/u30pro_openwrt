#!/usr/bin/ucode
// JSON stdin keeps credentials out of process arguments and shell expansion.
import { cursor } from 'uci';
import { connect } from 'ubus';
import { readfile } from 'fs';
import * as native from 'mu300.wifi-native';
try {
    let request=json(readfile('/dev/stdin')), bus=connect(null,request.action=='scan'?15:2);
    if(!bus)die('ubus unavailable');
    let result=native.dispatch(cursor(),bus,request.action,
        [request.ssid,request.password,request.encryption]);
    bus.disconnect();print(sprintf('%J\n',result));
} catch(e) {print(sprintf('%J\n',{ok:false,error:''+e}));exit(1);}
