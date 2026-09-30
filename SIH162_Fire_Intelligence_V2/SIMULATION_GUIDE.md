# Simulation Guide

## Goal

Demonstrate the entire upgraded pipeline without waiting for live satellite observations.

## 1. Start API

Terminal 1:

```bash
uvicorn app:app --reload
```

Open:

```text
http://127.0.0.1:8000/dashboard
```

## 2. Industrial scenario

```bash
python simulation.py --scenario industrial --events 8 --delay 0.8
```

Expected pattern:
- high FRP
- repeated detections
- close to industrial facility
- industrial land-cover context
- high industrial-source probability
- higher severity

## 3. Wildfire scenario

```bash
python simulation.py --scenario wildfire --events 8 --delay 0.8
```

Expected pattern:
- forest context
- expanding event
- high wind
- low humidity
- higher spread risk

## 4. Crop-burn scenario

```bash
python simulation.py --scenario crop_burn --events 8 --delay 0.8
```

Expected pattern:
- cropland context
- lower persistence
- localized thermal activity

## 5. Final mixed demonstration

```bash
python simulation.py --scenario mixed --events 20 --delay 0.5
```

Then:
1. Select a high-risk event on the map.
2. Show source probability.
3. Show severity and urgency.
4. Show FRP, persistence and industrial distance.
5. Explain the "Why?" factors.
6. Click Confirm, Uncertain or Reject.
7. Explain that human verification becomes future training data.

## Suggested judging narration

"Satellite detections are observations, not incidents. We first cluster observations into a spatial-temporal fire event. We then enrich the event with industrial proximity, land-cover and weather context. The AI estimates the likely source, while a separate risk layer estimates severity and urgency. Finally, the operator can verify the event, creating a human-in-the-loop learning cycle."

## Important

The simulation is synthetic. It demonstrates architecture and behavior; it is not evidence of satellite-model accuracy. Weak labels are also not ground truth. A final scientific system needs verified incident labels and geographic validation.
