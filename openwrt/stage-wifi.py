#!/usr/bin/env python3
"""Stage the matching hostapd/wifi-scripts APKs without starting services."""
import hashlib
import json
from pathlib import Path
import runpy
import subprocess

TOP = Path(__file__).resolve().parents[1]
STATE = runpy.run_path(str(TOP/'openwrt/wifi-sae-state.py'))
RECEIPT = 'usr/share/mu300/wifi-userspace.json'
FILES = ('usr/sbin/wpad', 'usr/share/hostap/hostapd.uc', 'usr/share/hostap/common.uc',
         'usr/share/hostap/wpa_supplicant.uc', 'usr/share/ucode/wifi/ap.uc',
         'usr/share/ucode/wifi/supplicant.uc', 'usr/share/ucode/wifi/iface.uc')
# wifi/hostapd.uc is verified by the separate shared-patches receipt after the
# reviewed DFS and channel-list contributions have been composed into it.


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(root):
    root = Path(root)
    record = json.loads((root/RECEIPT).read_text())
    if record['build_id'] != STATE['build_id']():
        raise ValueError('Wi-Fi userspace is stale; rebuild and stage the matching APKs')
    if set(record['files']) != set(FILES):
        raise ValueError('Wi-Fi userspace receipt is incomplete')
    for name, wanted in record['files'].items():
        if digest(root/name) != wanted:
            raise ValueError('Staged Wi-Fi userspace differs from its receipt: '+name)
    return record


def install(root, artifacts, image):
    root, artifacts = Path(root).resolve(), Path(artifacts).resolve()
    info = STATE['inspect'](artifacts)
    if root == Path('/') or not root.is_dir():
        raise ValueError('Select an existing prepared root')
    receipt = root/RECEIPT
    if receipt.is_file() and json.loads(receipt.read_text())['build_id'] == info['build_id']:
        return audit(root)

    # Replacing wifi-scripts replaces the base of the composed DFS/band patch.
    # Verify its old owned result before retiring only those patch receipts.
    patches = runpy.run_path(str(TOP/'tools/stage-wifi-patches.py'))
    path = root.parent/'shared-patches.json'
    records = json.loads(path.read_text()) if path.is_file() else {}
    for name in patches['PATCHES']:
        if name in records and records[name] != {
                'patch': digest(TOP/'openwrt/patches'/name),
                'result': digest(root/patches['RELATIVE'])}:
            raise ValueError('Existing composed Wi-Fi patch differs: '+name)
    subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--platform', 'linux/arm64',
                    '-v', str(root)+':/target', '-v', str(artifacts)+':/wifi:ro',
                    '--entrypoint', '/usr/bin/apk', image,
                    '--root', '/target', '--no-network', 'add', '--allow-untrusted',
                    '--scripts=no', '--commit-hooks=no', '--force-reinstall',
                    *('/wifi/'+name for name in sorted(info['apks']))], check=True)
    for name in patches['PATCHES']:
        records.pop(name, None)
    if path.is_file():
        path.write_text(json.dumps(records, indent=2)+'\n')
    record = dict(info, files={name:digest(root/name) for name in FILES})
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(record, indent=2)+'\n')
    return audit(root)
