# Pro 板载蓝牙适配依据

本轮开发针对 U30 Pro / MU5358 和 F50 Pro / MU3356 的同一 UMS9632 平台。
用户确认原厂 Android 实际配对成功；这证明用户使用的 Pro 硬件具备蓝牙，
不能仅凭设备树的通用 Marlin 节点选择 SC2355 初始化流程。

## 已核对的源码和本地原厂资料

1. 现有 UMS9632 AIC BSP：
   `aic8800_bsp/aic_bsp_driver.h` 的默认值是 UART、1500000 baud、硬件流控；
   已纳入公开构建输入的 `fw_adid_8800d80x2_u05.bin`、
   `fw_patch_8800d80x2_u05.bin`、`fw_patch_table_8800d80x2_u05.bin`
   由已有 SDIO BSP 下载。没有新增私有 firmware 输入。
2. `aic8800_bsp/aicsdio.c::aicbsp_set_subsys` 使用带锁的 BT / Wi-Fi 电源位图，
   仅在整体电源状态变化时开关组合芯片。蓝牙模块应取得自己的位，不能直接拉
   Wi-Fi 电源 GPIO，也不能为初始化蓝牙卸载 Wi-Fi。
3. 本机保留的原厂 B16 兼容库，来自此前 B19 / LTYB05 蓝牙恢复记录：
   `U30Pro_B19_LTYB05_Bluetooth_Fix_CallBase_v1.5.2/compat/odm/lib64/libbt-vendor.so`，
   SHA-256 `af887edf8927b7e176443504abe9c4d052902e74a90336bff2692da883cd0090`。
   库标识为 Aicsemi UART，包含 `/dev/ttyS0` 和
   `/sys/devices/platform/aic-bt/rfkill`；同批日志的系统控制台是 ttyS1。
   导出函数 `hw_config_set_bdaddr` 在 0x163c0，0x16420 起装载 FC70、长度 6，
   参数为反序的蓝牙地址。新实现只在 HCI owner 附着之前设置这个易失地址，
   不写校准或基带 NV；没有旧配置时生成并保留本机独立地址。
4. 本地 MU3356 Android 15 / 6.6.46 归档中的
   `aic8800_btlpm/rfkill.c` 同样调用 `aicbsp_set_subsys`，没有直接控制 GPIO。
   提取文本 SHA-256 `8b6e636f93446b2ddfcbc7d3a312f4559092a8688bda4202ac8cf8b03cde0bac`。
   注意整个本地 tar.gz 遍历结束报截断，不能视为完整、可重建的原厂源码包；
   该文本仅作旁证，不作为正式构建输入。新小模块为独立实现。

## 本轮修改和验收边界

- 原内核关闭 CONFIG_BT；现启用双模核心、H4、RFCOMM / TTY 和 btusb。
- `aic_bt_rfkill.ko` 是独立加载的 power owner，使用现有 BSP API，正常启动
  默认不加载；仅用户手动开启蓝牙，或明确勾选开机开启后启动。保存网关配置
  不会绕过开机关闭策略。
- 独立平台配置 `u30pro-aic-uart` 固定在 Pro 的构建入口，不根据探测失败切到
  MU300，也不调用继承的 `/opt/mu300/bin/bluetooth-start`。
- 注册失败、UART 无应答和 vendor command 拒绝均返回错误，不重置 Wi-Fi
  或强行修改省电策略。网页和密钥、ACL、SSE 见
  [公共说明](BLUETOOTH-GATEWAY.zh-CN.md)。

2026-11-17 已在用户的 U30 Pro 上完成 Linux A 槽配套内核／253 个模块更新，
实际确认 UART H4 初始化、蓝牙开启／关闭、BLE 发现 5 台设备、厂商／服务
广播资料、经典扫描启动／停止、6 实例能力及双广播的注册／到期／停止。
Wi-Fi、USB 网络和蜂窝连接保持正常；详细范围和保留项见
[实机记录](BLUETOOTH-GATEWAY.zh-CN.md)。

真实配对、BLE GATT／RFCOMM 外设收发、长期共存与系统挂起仍待实测，
F50 Pro 本轮未接入验证，不能将 U30 Pro 一台机器的结果当成两个产品全批次支持。
