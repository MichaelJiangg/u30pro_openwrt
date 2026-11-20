"""Execute production FGU SOC code against counter/charger/fault fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
DRIVER = TOP/'devices/u30pro/native/kernel/ums9632/overlay/drivers/power/supply/u30pro-ump965x-fgu.c'


def declaration(source, name):
    match = re.search(r'^static [^\n]+\b'+name+r'\([^;{}]*\)\s*\{', source, re.M)
    if not match:
        return ''
    end = source.index('{', match.start()) + 1
    depth = 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[match.start():end]+'\n'


@unittest.skipUnless(os.name == 'posix', 'host C compiler')
class Accounting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        source = Path(os.environ.get('U30PRO_FGU_TEST_SOURCE', DRIVER)).read_text()
        struct = re.search(r'struct ump_fgu \{.*?^\};', source, re.S | re.M)[0]
        functions = ''.join(declaration(source, name) for name in (
            'ump_soc_clamp', 'ump_soc_init', 'ump_count_uah', 'ump_charger_full', 'ump_soc_work'))
        fixture = (TOP/'tests/fixtures/u30pro_fgu_accounting.c').read_text()
        fixture = fixture.replace('/* FGU_STRUCT */', struct).replace('/* FGU_FUNCTIONS */', functions)
        root = Path(cls.temp.name)
        (root/'test.c').write_text(fixture)
        cls.binary = root/'fgu'
        subprocess.run(['gcc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                        '-Wno-unused-function', '-Wno-sign-compare', str(root/'test.c'), '-o', str(cls.binary)], check=True)

    def case(self, n):
        result = subprocess.run([str(self.binary), str(n)], timeout=8)
        self.assertEqual(result.returncode, 0, 'production FGU accounting case '+str(n))

    def test_paused_small_positive_current_never_creates_charge(self): self.case(1)
    def test_relaxed_terminal_voltage_does_not_rewrite_accumulated_charge(self): self.case(2)
    def test_signed_counter_wrap_and_fraction_are_continuous(self): self.case(3)
    def test_failed_reads_preserve_counter_baseline_until_recovery(self): self.case(4)
    def test_full_requires_real_unpaused_completion_and_no_lock_inversion(self): self.case(5)
    def test_startup_anchors_to_existing_counter_without_resetting_it(self): self.case(6)
    def test_sustained_bursty_load_follows_counter_instead_of_sample_alias(self): self.case(7)
    def test_charge_discharge_and_physical_endpoint_bounds(self): self.case(8)


if __name__ == '__main__': unittest.main(verbosity=2)
