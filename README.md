# Breastfeeding Tracker (local, mobile-first)

## Run
```bash
docker compose up --build
```

Open: http://localhost:8081

## Features
- Log breastfeeding sessions with breast side (**L/R**) + start + end time
- “Now” shortcuts
- Last 7 days summary split by L/R (count + total minutes)
- Recent feedings list + delete

## Data
- SQLite stored in Docker volume `diaper-data`

## Notes
- No auth (local use)
- Uses device local time
