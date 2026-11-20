/* Host-only fixtures. No hardware registers, power-policy writes or real time. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef int32_t s32;
typedef int64_t s64;
typedef s64 ktime_t;
struct mutex { int held; };
struct work_struct { int unused; };
struct delayed_work { struct work_struct work; };
#define UMP_SOC_PERIOD_MS 2000
#define UMP_RELAX_UA 30000
#define UMP_RELAX_SYNC_MS 60000
#define container_of(p,t,m) ((t *)((char *)(p)-offsetof(t,m)))
#define min_t(t,a,b) ((t)(a)<(t)(b)?(t)(a):(t)(b))
/* FGU_STRUCT */
static struct ump_fgu *live;
static u64 counter;
static int voltage, current, ocv_pct, counter_error, voltage_error, current_error;
static bool charger_present;
static int charger_status, charger_behaviour, charger_error, releases, polls, reads;
static s64 clock_ms;
enum { POWER_SUPPLY_PROP_STATUS, POWER_SUPPLY_PROP_CHARGE_BEHAVIOUR };
enum { POWER_SUPPLY_STATUS_NOT_CHARGING, POWER_SUPPLY_STATUS_CHARGING, POWER_SUPPLY_STATUS_FULL };
enum { POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO, POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE };
union power_supply_propval { int intval; };
struct power_supply { int unused; };
static struct power_supply charger;
static s64 div_s64(s64 n, s32 d) { return n/d; }
static s64 div_s64_rem(s64 n, s32 d, s32 *r) { *r=n%d;return n/d; }
static s64 sign_extend64(u64 v, int bit) { return (s64)(v<<(63-bit))>>(63-bit); }
static ktime_t ktime_get(void) { return clock_ms; }
static s64 ktime_ms_delta(ktime_t a,ktime_t b) { return a-b; }
static void mutex_lock(struct mutex *m) { assert(!m->held);m->held=1; }
static void mutex_unlock(struct mutex *m) { assert(m->held);m->held=0; }
static int ump_voltage_uv(struct ump_fgu *f,int *v) { (void)f;*v=voltage;return voltage_error; }
static int ump_current_ua(struct ump_fgu *f,int *v) { (void)f;*v=current;return current_error; }
static int ump_count_raw(struct ump_fgu *f,u64 *v) { (void)f;reads++;*v=counter;return counter_error; }
static int ump_ocv_uv(struct ump_fgu *f,int v,int a) { (void)f;(void)a;return v; }
static int ump_ocv_to_pct(struct ump_fgu *f,int v) { (void)f;(void)v;return ocv_pct; }
static void schedule_delayed_work(struct delayed_work *w,int ms) { (void)w;assert(ms==2000);polls++; }
static int msecs_to_jiffies(int ms) { return ms; }
static struct power_supply *power_supply_get_by_name(const char *name) {
 assert(!strcmp(name,"u30pro-charger-master"));assert(!live->lock.held);
 return charger_present?&charger:NULL;
}
static int power_supply_get_property(struct power_supply *p,int key,union power_supply_propval *v) {
 assert(p==&charger && !live->lock.held);
 v->intval=key==POWER_SUPPLY_PROP_STATUS?charger_status:charger_behaviour;
 return charger_error;
}
static void power_supply_put(struct power_supply *p) { assert(p==&charger);releases++; }
/* FGU_FUNCTIONS */
static void reset(struct ump_fgu *f) {
 memset(f,0,sizeof(*f));live=f;counter=1000000;current=0;voltage=4200000;ocv_pct=80;
 counter_error=voltage_error=current_error=0;charger_present=true;charger_error=0;
 charger_status=POWER_SUPPLY_STATUS_NOT_CHARGING;
 charger_behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_INHIBIT_CHARGE;
 f->ocv_count=2;f->full_uah=5000000;f->current_gain=1000;
 f->full_ua=120000;f->full_uv=4300000;clock_ms=0;releases=polls=reads=0;
 ump_soc_init(f);assert(f->soc_ready && f->charge_uah==4000000);
}
static void tick(struct ump_fgu *f,s64 delta) {
 counter=(counter+delta)&((1ULL<<36)-1);clock_ms+=2000;
 ump_soc_work(&f->soc_work.work);assert(!f->lock.held);
}
int main(int argc,char **argv) {
 struct ump_fgu f;assert(argc==2);reset(&f);
 switch(atoi(argv[1])) {
 case 1:
  current=40000;for(int i=0;i<1800;i++)tick(&f,0);
  assert(f.charge_uah==4000000);assert(polls==1800);break;
 case 2:
  ocv_pct=98;current=10000;voltage=4250000;
  for(int i=0;i<1800;i++)tick(&f,0);
  assert(f.charge_uah==4000000);break;
 case 3:
  counter=(1ULL<<36)-100;f.soc_ready=false;ump_soc_init(&f);
  tick(&f,200);assert(f.charge_uah==4000001);
  tick(&f,16);assert(f.charge_uah==4000002);
  tick(&f,-216);assert(f.charge_uah==4000000);
  tick(&f,-108);assert(f.charge_uah==3999999);
  tick(&f,108);assert(f.charge_uah==4000000);break;
 case 4:
  counter_error=-5;tick(&f,1080);assert(f.charge_uah==4000000);
  counter_error=0;tick(&f,1080);assert(f.charge_uah==4000020);
  voltage_error=-5;tick(&f,-1080);assert(f.charge_uah==4000020);
  voltage_error=0;current_error=-5;tick(&f,-1080);assert(f.charge_uah==4000020);
  current_error=0;tick(&f,0);assert(f.charge_uah==4000000);break;
 case 5:
  current=40000;voltage=4350000;
  tick(&f,0);assert(f.charge_uah==4000000);
  charger_status=POWER_SUPPLY_STATUS_FULL;tick(&f,0);assert(f.charge_uah==4000000);
  charger_behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO;
  charger_error=-5;tick(&f,0);assert(f.charge_uah==4000000);
  charger_error=0;charger_present=false;tick(&f,0);assert(f.charge_uah==4000000);
  charger_present=true;current=-40000;tick(&f,0);assert(f.charge_uah==4000000);
  current=40000;tick(&f,0);assert(f.charge_uah==5000000);assert(releases==5);break;
 case 6:
  f.soc_ready=false;counter=(1ULL<<35)+987654321;ump_soc_init(&f);
  tick(&f,1080);assert(f.charge_uah==4000010);
  f.soc_ready=false;counter_error=-5;ump_soc_init(&f);assert(!f.soc_ready);
  counter_error=0;tick(&f,0);assert(f.soc_ready && f.charge_uah==4000000);
  tick(&f,-1080);assert(f.charge_uah==3999990);break;
 case 7:
  current=40000;ocv_pct=99;
  for(int i=0;i<43200;i++)tick(&f,-1);
  assert(f.charge_uah==3999600 && polls==43200);break;
 case 8:
  current=1000000;charger_behaviour=POWER_SUPPLY_CHARGE_BEHAVIOUR_AUTO;
  charger_status=POWER_SUPPLY_STATUS_CHARGING;
  tick(&f,108000);assert(f.charge_uah==4001000);
  current=-1000000;tick(&f,-108000);assert(f.charge_uah==4000000);
  f.charge_uah=4999999;tick(&f,1080);assert(f.charge_uah==5000000);
  f.charge_uah=1;tick(&f,-1080);assert(f.charge_uah==0);
  f.charge_uah=1000000;voltage=3200000;tick(&f,0);assert(f.charge_uah==50000);break;
 default:abort();
 }
 printf("PASS production FGU accounting case %s\n",argv[1]);
}
