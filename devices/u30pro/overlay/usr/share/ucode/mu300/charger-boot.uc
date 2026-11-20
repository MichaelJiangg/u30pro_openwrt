// Boot policy only. Charging never rewrites RF, Wi-Fi, Bluetooth or boot intent.
export function charging(model, args, automatic, failsafe) {
    return model == 'u30pro' && !failsafe && automatic != '1' &&
        !!match(join(' ', split(args, '\x00')),
            /(^|[[:space:]])(sprdboot|androidboot)\.mode=charger([[:space:]]|$)/);
};

export function outcome(code) {
    return code == 3 ? 'poweroff' : code == 0 ? 'boot' : 'unavailable';
};
