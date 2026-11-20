"""RPC jobs: no credentials in argv/results, mutual exclusion and recovery."""
import importlib.machinery
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TOP = Path(__file__).resolve().parents[1]
SOURCE = TOP/'devices/u30pro/overlay/usr/libexec/unisoc-modem/wifi-relay'


@unittest.skipUnless(os.name == 'posix', 'production flock and inherited descriptors')
class RelayJobs(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = importlib.machinery.SourceFileLoader('relay_jobs', str(SOURCE)).load_module()
        self.module.RUN = Path(self.temp.name)

    def test_start_does_not_wait_for_scan_or_expose_password(self):
        request = dict(action='connect', ssid="AP ' with $shell", password='test-password', encryption='psk2')
        with patch.object(self.module.subprocess, 'Popen') as popen:
            reply = self.module.start(request)
        self.assertTrue(reply['pending'])
        self.assertNotIn('test-password', repr(popen.call_args))
        self.assertEqual(popen.call_args.kwargs['stdout'], subprocess.DEVNULL)
        self.assertEqual(popen.call_args.kwargs['stderr'], subprocess.DEVNULL)
        self.assertEqual(len(popen.call_args.kwargs['pass_fds']), 1)
        self.assertNotIn('test-password', (self.module.RUN/'job.json').read_text())
        self.assertEqual(json.loads((self.module.RUN/'request.json').read_text()), request)

    def test_second_start_is_rejected_while_worker_owns_lock(self):
        import fcntl
        with (self.module.RUN/'lock').open('a') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError, 'relay_busy'):
                self.module.start(dict(action='scan'))

    def test_worker_removes_secret_request_before_backend_and_records_failure(self):
        self.module.write('request.json', dict(action='connect', password='test-password'))
        lock = os.open(self.module.RUN/'lock', os.O_CREAT | os.O_RDWR, 0o600)
        def run(request):
            self.assertFalse((self.module.RUN/'request.json').exists())
            return dict(ok=False, error='Wi-Fi key invalid')
        with patch.object(self.module, 'native', side_effect=run):
            self.module.worker(lock)
        result = json.loads((self.module.RUN/'job.json').read_text())
        self.assertFalse(result['pending'])
        self.assertFalse(result['ok'])
        self.assertNotIn('test-password', json.dumps(result))

    def test_launch_failure_is_not_permanently_pending(self):
        with patch.object(self.module.subprocess, 'Popen', side_effect=OSError('test')):
            with self.assertRaises(OSError):
                self.module.start(dict(action='scan'))
        self.assertFalse(json.loads((self.module.RUN/'job.json').read_text())['pending'])
        self.assertFalse((self.module.RUN/'request.json').exists())

    def test_invalid_inputs_are_rejected_before_launch(self):
        base = dict(action='connect', ssid='Wi-Fi', password='valid-password', encryption='psk2')
        for changed in ({'ssid':'汉'*11}, {'ssid':'bad\nname'}, {'password':'bad\0key'},
                        {'encryption':'wpa-enterprise'}, {'action':'shell'}, {'command':'reboot'}):
            with self.subTest(changed=changed), patch.object(self.module.subprocess, 'Popen') as popen:
                with self.assertRaises(ValueError):
                    self.module.start(dict(base, **changed))
                popen.assert_not_called()

    def test_read_only_acl_cannot_scan_or_reconfigure(self):
        rules=json.loads((TOP/'devices/u30pro/overlay/usr/share/rpcd/acl.d/u30pro-wifi-relay.json').read_text())['u30pro-wifi-relay']
        self.assertEqual(rules['read']['ubus']['u30pro-wifi-relay'], ['status'])
        self.assertEqual(rules['write']['ubus']['u30pro-wifi-relay'], ['start'])


if __name__ == '__main__':
    unittest.main()
