# Pro WPA3 在四次握手时安装不支持的密钥

## 实机证据

2026-11-20，F50 Pro / MU3356，Linux `6.12.94-u30pro-p1`，
固件 `r20261120.081730-g4b3c497a-s8d8135c9`。电脑还连接了另一个同为
192.168.77.1 的 F50，本次 SSH 明确绑定 F50 Pro 所在本地接口并核对产品标识。

热点为 CN、36 信道、HE80、纯 SAE，要求 PMF。手机完成 SAE 认证和关联，
随后出现 `key setting validation failed` 并断开。临时诊断程序记录：

```text
alg=8 idx=0 key_len=32 seq_len=0 key_flag=0x2c link_id=-1
```

当前 hostapd 的 `alg=8` 为 GCMP-256。实际 wiphy 只报告 WEP、TKIP、
CCMP-128、CMAC、SMS4；没有 GCMP-256。内核在进入驱动的 `add_key` 之前
拒绝该请求，不能把这个错误当成固件安装密钥失败或密码错误。

虽然 hostapd `GET_CONFIG` 显示 CCMP，生成文件还有：

```text
rsn_override_key_mgmt=SAE
rsn_override_pairwise=GCMP-256 CCMP
rsn_override_mfp=2
```

固定 OpenWrt wifi-scripts 的 `parse_encryption()` 仅根据 HE/EHT 自动添加
GCMP-256，没有核对硬件加密能力。支持 RSN Override 的终端可以因此选择
硬件不支持的算法；其他终端正常不代表此配置正确。

发布包的 `CONFIG_WPA_MSG_MIN_PRIORITY=3` 已在编译时裁掉 DEBUG 参数日志。
两次临时日志调级均已恢复 INFO。诊断版仅补充失败请求的算法、索引、长度、
标志和链路编号，不输出密钥；采集结束已恢复并校验原 wpad。

## 修复和交付

`openwrt/patch-hostapd-sae.py` 继续通过原 wifi-scripts 构建路径实施修复：

- 从配置该无线电时已有的 wiphy 数据取得 `cipher_suites`，交给加密配置解析器。
- 只有明确报告 GCMP-256 时，HE/EHT 默认配置才自动增加该算法。
- 保留明确选择的密码套件、WPA3/PMF、密码、频宽、信道及国家码。
- 不按机型、固件版本或哈希决定功能，不增加服务、扫描、轮询或额外能力查询。

`ap.uc`、`iface.uc`、`wifi/hostapd.uc` 均由匹配的 wifi-scripts APK 交付。
`stage-wifi.py` 增加对 `iface.uc` 的文件核对；`wifi/hostapd.uc` 继续在组合
DFS／信道列表补丁之后通过 shared-patches 回执验证，避免用原始 APK 文件覆盖
已生效的信道策略。失败请求的诊断日志随正常 wpad 构建交付。

## 离线验证与实机验收

`tests/test_wpa3_cipher_capabilities.py` 六项通过：真实 AIC 能力重现旧缺陷、
支持 GCMP-256 的无线电行为不变、缺失／无关能力不冒充支持、明确密码套件和
192 位企业配置不被静默替换、100 组认证／PHY／Override 组合、补丁幂等及
已有 wiphy 数据的传递。原 hostapd C AP/STA 生命周期回归也通过。

已核对实际 APK 加上既有信道补丁后的三份文件，逐字节等于对故障机原脚本
应用本修复的结果。U30 Pro 和 F50 Pro 分别通过实际差分生成、应用、回滚，
用户 wireless/network 文件保持不变。测试所需的文件所有者恢复须在 Linux
root 下执行；第一次普通用户运行被 chown 权限拒绝，未为测试放宽更新校验。

日志目录：`out/build-logs/20261120-110404-f50pro-wpa3-cipher-regression-93933/`
和 `out/build-logs/20261120-110653-f50pro-wpa3-delivery-final-94051/`。
这些是离线验证；正式修复的实机部署和连接验收尚待本轮用户授权及验证。
