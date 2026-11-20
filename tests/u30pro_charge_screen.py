"""Run the actual renderer without DRM; charging cannot invoke normal actions."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TOP = Path(__file__).resolve().parents[1]
NATIVE = TOP/'devices/u30pro/native/tools'


@unittest.skipUnless(os.name == 'posix', 'POSIX C host simulator')
class ChargeScreen(unittest.TestCase):
    def test_render_animation_full_charge_and_key_isolation(self):
        source = r'''#define UI_HOST
#define UI_RUN "TEST_RUN"
#define UI_SYSFS "."
#define main simulator_main
#include "u30pro_ui.c"
#undef main
#include <assert.h>
int main(int argc,char **argv) {
 assert(argc==2);ui_init_canvases();charger_only=1;
 charger_refresh();assert(!D.bat_ok && D.bat_pct==-1);
 assert(!rename("TEST_RUN/later-battery","TEST_RUN/sys/class/power_supply/u30pro-battery"));
 const char add[]="add@/devices/fgu\0ACTION=add\0SUBSYSTEM=power_supply\0POWER_SUPPLY_NAME=u30pro-battery";
 assert(power_uevent(add,sizeof add,0,0));
 assert(D.bat_ok && D.bat_pct==48 && D.charging);
 assert(!power_uevent(add,sizeof add,9,0));
 D.bat_ok=1;D.bat_pct=65;D.charging=1;D.full=0;
 g_ms=vclock=200;nhits=4;compose();assert(nhits==0);
 assert(scr.p[0]==0 && scr.p[239]==0);
 size_t size=240*240*sizeof(uint32_t);void *frame=malloc(size);
 memcpy(frame,scr.p,size);g_ms=vclock=1200;compose();assert(memcmp(frame,scr.p,size));
 D.charging=0;D.full=1;D.bat_pct=100;compose();memcpy(frame,scr.p,size);
 g_ms=vclock=2000;compose();assert(!memcmp(frame,scr.p,size));
 for(int i=-1;i<=100;i++){D.bat_pct=i;compose();assert(nhits==0);}
 key_double=KA_CUSTOM;key_power_double=KA_CUSTOM;
 ui_key_event(102,100);ui_key_event(102,3000);ui_key_event(116,3000);ui_key_event(116,-1);
 assert(!power_menu && !sheet && !anim_on && !incoming_visible());
 D.bat_pct=65;D.charging=1;D.full=0;g_ms=vclock=1000;compose();
 FILE *f=fopen(argv[1],"wb");assert(f);fprintf(f,"P6\n240 240\n255\n");
 for(int i=0;i<240*240;i++){unsigned char p[3]={scr.p[i]>>16,scr.p[i]>>8,scr.p[i]};fwrite(p,1,3,f);}
 fclose(f);free(frame);return 0;
}'''
        with tempfile.TemporaryDirectory(prefix='pro-charge-screen-') as directory:
            root=Path(directory);c=root/'test.c'
            (root/'sys/class/power_supply/u30pro-charger-master').mkdir(parents=True)
            (root/'sys/class/power_supply/u30pro-charger-master/status').write_text('Charging\n')
            (root/'sys/class/power_supply/u30pro-charger-master/online').write_text('1\n')
            (root/'later-battery').mkdir()
            (root/'later-battery/type').write_text('Battery\n')
            (root/'later-battery/capacity').write_text('48\n')
            c.write_text(source.replace('TEST_RUN',directory))
            subprocess.run(['gcc','-std=gnu11','-O1','-Wno-unused-function','-I',str(NATIVE),
                            str(c),'-lm','-o',str(root/'test')],check=True,capture_output=True)
            output=TOP/'out/screenshots/u30pro-charge-mode.ppm';output.parent.mkdir(parents=True,exist_ok=True)
            p=subprocess.run([str(root/'test'),str(output)],cwd=root,capture_output=True,text=True,timeout=20)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            self.assertNotIn('RUN ',p.stdout)


if __name__=='__main__': unittest.main()
