# SIH162 Fire Intelligence V3

## Start

```bat
.venv\Scripts\activate
uvicorn app:app --reload
```

Open:

http://127.0.0.1:8000/dashboard

## Simulation

Choose:

- Mixed
- Industrial fire
- Wildfire
- Crop burn

Then click **Run simulation**.

Simulation data is explicitly marked:

`SIMULATION`

## Real NASA FIRMS

Put your existing key in `.env`:

```env
FIRMS_MAP_KEY=YOUR_EXISTING_KEY
```

Then click **Fetch NASA FIRMS**.

Real observations are marked:

`NASA_FIRMS`

The current source-classification layer is a prototype contextual/heuristic inference, not a NASA ground-truth label.
