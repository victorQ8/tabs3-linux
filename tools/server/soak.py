#!/usr/bin/env python3
"""Bounded CPU/memory check with independent temperature and power guards."""
import pathlib,subprocess,time,json,sys,signal
root=pathlib.Path('/run/tabs3-server-soak');root.mkdir(exist_ok=True)
start=time.monotonic()
boot=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip()
args=['stress-ng','--cpu','4','--cpu-method','int64','--verify','--vm','1','--vm-bytes','256M','--vm-keep','--timeout','600s','--metrics-brief']
f=(root/'stress.txt').open('w')
p=subprocess.Popen(args,stdout=f,stderr=subprocess.STDOUT)
reason='completed'
samples=[]
try:
 while p.poll() is None:
  temps={}
  for z in pathlib.Path('/sys/class/thermal').glob('thermal_zone*'):
   try:temps[(z/'type').read_text().strip()]=int((z/'temp').read_text())
   except (OSError,ValueError):pass
  battery=pathlib.Path('/sys/class/power_supply/sm5705-battery')
  sample={'elapsed_s':round(time.monotonic()-start,1),'temperatures_mc':temps,'battery_percent':int((battery/'capacity').read_text()),'battery_temp_deci_c':int((battery/'temp').read_text()),'battery_current_ua':int((battery/'current_now').read_text()),'frequencies_khz':{p.parent.name:int(p.read_text()) for p in pathlib.Path('/sys/devices/system/cpu/cpufreq').glob('policy*/scaling_cur_freq')}}
  samples.append(sample)
  with (root/'samples.jsonl').open('a') as out:out.write(json.dumps(sample)+'\n')
  if max(temps.values(),default=999999)>=95000 or sample['battery_temp_deci_c']>=380 or sample['battery_percent']<40:
   reason='temperature or battery guard';p.terminate();break
  if time.monotonic()-start>630:
   reason='supervisor time limit';p.terminate();break
  time.sleep(5)
 p.wait(timeout=10)
finally:
 if p.poll() is None:p.kill();p.wait()
 f.close()
result={'boot_id':boot,'reason':reason,'exit_code':p.returncode,'elapsed_s':round(time.monotonic()-start,1),'sample_count':len(samples),'kernel':subprocess.check_output(['uname','-a'],text=True).strip()}
(root/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
sys.exit(0 if reason=='completed' and p.returncode==0 else 1)
