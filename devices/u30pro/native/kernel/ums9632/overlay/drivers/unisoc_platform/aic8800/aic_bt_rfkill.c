// SPDX-License-Identifier: GPL-2.0-only
/*
 * UMS9632 AIC UART transport power owner.
 * Follows MU3356 Android 15 aic8800_btlpm/rfkill.c: use the BSP's shared
 * subsystem bitmap, never toggle combo-chip GPIOs or reset the Wi-Fi owner.
 * Its return value is the resulting aggregate power state, not an errno.
 */
#include <linux/err.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/platform_device.h>
#include <linux/rfkill.h>
#include "aic8800_bsp/aic_bsp_export.h"

static struct platform_device *bt_device;
static struct rfkill *bt_rfkill;
static DEFINE_MUTEX(bt_lock);
static bool bt_enabled;

static int aic_bt_block(void *data, bool blocked)
{
	int ret = 0;

	mutex_lock(&bt_lock);
	if (bt_enabled == !blocked)
		goto out;
	ret = aicbsp_set_subsys(AIC_BLUETOOTH, blocked ? AIC_PWR_OFF : AIC_PWR_ON);
	if (ret < 0) {
		ret = -EIO;
		goto out;
	}
	bt_enabled = !blocked;
	ret = 0;
out:
	mutex_unlock(&bt_lock);
	return ret;
}

static const struct rfkill_ops aic_bt_ops = {
	.set_block = aic_bt_block,
};

static int __init aic_bt_init(void)
{
	int ret;

	bt_device = platform_device_register_simple("aic-bt", -1, NULL, 0);
	if (IS_ERR(bt_device))
		return PTR_ERR(bt_device);
	bt_rfkill = rfkill_alloc("bluetooth", &bt_device->dev,
				RFKILL_TYPE_BLUETOOTH, &aic_bt_ops, NULL);
	if (!bt_rfkill) {
		ret = -ENOMEM;
		goto device_out;
	}
	rfkill_init_sw_state(bt_rfkill, true);
	ret = rfkill_register(bt_rfkill);
	if (!ret)
		return 0;
	rfkill_destroy(bt_rfkill);
device_out:
	platform_device_unregister(bt_device);
	return ret;
}

static void __exit aic_bt_exit(void)
{
	rfkill_unregister(bt_rfkill);
	aic_bt_block(NULL, true);
	rfkill_destroy(bt_rfkill);
	platform_device_unregister(bt_device);
}

module_init(aic_bt_init);
module_exit(aic_bt_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("UMS9632 AIC UART Bluetooth shared-subsystem power");
