from pathlib import Path
import numpy as np,pandas as pd
raw=Path("data/raw_firms.csv"); out=Path("data/training_ready.csv")
if not raw.exists(): raise SystemExit("Run fetch_firms.py first")
df=pd.read_csv(raw); df.columns=[c.strip().lower() for c in df.columns]
for c in ["latitude","longitude","frp"]: df[c]=pd.to_numeric(df[c],errors="coerce")
mp={"low":30,"nominal":60,"high":90}
df["confidence_score"]=df["confidence"].astype(str).str.lower().map(mp).fillna(pd.to_numeric(df["confidence"],errors="coerce")).fillna(50)
t=pd.to_datetime(df["acq_date"].astype(str)+" "+df["acq_time"].astype(str).str.zfill(4),errors="coerce",utc=True)
df["hour_utc"]=t.dt.hour.fillna(12); df["is_night"]=((df.hour_utc<6)|(df.hour_utc>=18)).astype(int)
df["hotspot_density"]=df.groupby([df.latitude.round(2),df.longitude.round(2)]).latitude.transform("size"); df["persistence_count"]=df.hotspot_density
hi=df.persistence_count>=3; hf=df.frp>=df.frp.quantile(.75); night=df.is_night.eq(1)
y=np.full(len(df),"other_thermal",object); y[hi&hf&night]="industrial_persistent"; y[(~hi)&hf]="vegetation_fire"; y[(~hi)&(~hf)]="agricultural_burn"; df["weak_label"]=y
df[["latitude","longitude","frp","confidence_score","hour_utc","is_night","hotspot_density","persistence_count","weak_label"]].dropna().to_csv(out,index=False)
print(out)
