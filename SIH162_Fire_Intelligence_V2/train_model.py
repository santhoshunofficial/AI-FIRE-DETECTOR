from pathlib import Path
import joblib,pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder
D=Path("data/training_ready.csv"); F=["latitude","longitude","frp","confidence_score","hour_utc","is_night","hotspot_density","persistence_count"]
if not D.exists(): raise SystemExit("Run prepare_training.py")
df=pd.read_csv(D).dropna(); enc=LabelEncoder(); y=enc.fit_transform(df.weak_label.astype(str)); X=df[F]
xt,xv,yt,yv=train_test_split(X,y,test_size=.2,random_state=42,stratify=y)
m=RandomForestClassifier(n_estimators=400,max_depth=14,class_weight="balanced_subsample",random_state=42,n_jobs=-1,min_samples_leaf=2)
m.fit(xt,yt); print(classification_report(yv,m.predict(xv),zero_division=0))
Path("models").mkdir(exist_ok=True); joblib.dump({"model":m,"encoder":enc,"features":F,"warning":"weak labels"}, "models/fire_source_model.joblib")
