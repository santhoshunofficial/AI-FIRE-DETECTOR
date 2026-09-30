# Architecture

## V2 logical pipeline

```text
NASA FIRMS / Simulation
          |
          v
Spatial-temporal clustering
          |
          v
Fire Event
   |      |       |
Facility Land   Weather
Context  Cover   Context
   \      |       /
        Features
           |
    +------+------+
    |             |
Source model   Anomaly model
    |             |
    +------+------+
           |
      Risk Engine
           |
     +-----+------+
     |            |
 Dashboard      Alerts
     |
Human verification
     |
Retraining dataset
```

## Production target

FastAPI + PostgreSQL/PostGIS + background workers + WebSockets + model registry + monitoring.

## Design rule

Keep detection, event formation, source classification, severity, and alert state as separate concepts.
