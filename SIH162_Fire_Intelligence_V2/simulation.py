import argparse,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from app import init_db,generate,process

p=argparse.ArgumentParser()
p.add_argument("--scenario",choices=["industrial","wildfire","crop_burn","mixed"],default="mixed")
p.add_argument("--events",type=int,default=10)
p.add_argument("--detections-per-event",type=int,default=8)
p.add_argument("--delay",type=float,default=.5)
a=p.parse_args()
init_db()
print("Open http://127.0.0.1:8000/dashboard")
for i in range(a.events):
    s=["industrial","wildfire","crop_burn"][i%3] if a.scenario=="mixed" else a.scenario
    for e in process(generate(s,a.detections_per_event,500+i)):
        print(e["event_id"],e["source_class"],e["urgency"],e["severity"])
    time.sleep(a.delay)
