# Pro 默认 AP 接口名修正（2026-11-15）

用户反馈 F50 Pro 新版 Wi-Fi 灯不亮、重启信道回到 36，并提供临时修复：
设置 wireless.default_radio0.ifname=wlan0 后提交并重载 radio0。

## 已确认

Pro 的 devices/u30pro/overlay/etc/config/wireless 默认 AP 原先未写 ifname；
F50 Pro LED 服务默认查询 hostapd.wlan0，并按 wlan0 的链路通知刷新。
两款 Pro 共用默认配置，E5 默认的 default_radio0、MU300 默认的 ap0 已指定 wlan0。
原生参考中的 wireless-defaults.uc 不是本项目启动时的迁移入口，未修改该文件。

默认配置补入 ifname=wlan0。新增 u30pro-wifi-ifname，由现有 mu300-hw 的 boot
在启动无线前调用，覆盖更新后仍缺少绑定的已保存配置。只处理本项目的
radio0/default_radio0 AP；已有接口名、其他模式、用户设置不改写。
wlan0 被另一接口明确占用或存在未提交修改时，不代用户提交，不覆盖配置，
记录失败后继续现有无线启动流程。没有新增无线重载、轮询或运行期改名。

## 信道边界

改 ifname 本身没有信道写入。共享 openwrt-wifi-config 会将已保存的、不支持的
DFS 信道回退到 36，且保留带宽，这是原有策略。
目前只收到型号 F50 Pro，没有用户原先选择的信道和启动日志；
不能认定回到 36 与灯不亮一定是同一个缺陷，也未删除 DFS/国家码约束。

## 验证和发布边界

tests/u30pro_wifi_ifname.py 在现有 ARM OpenWrt 目标根和隔离 Docker 容器内，
使用真实 ucode/uci 执行生产检查器；只替换配置目录和注入未提交修改。
覆盖 44/149 信道、密码和 HE80 保留、自定义接口名、STA 模式、
名称冲突、未提交修改、重复运行和新装默认值。
任务：20261115-084037-pro-wifi-ifname-regression-56359，全部通过。
未连接设备、热部署、重载实机无线或重新打包；之前的 ZIP 不包含本次修正。
