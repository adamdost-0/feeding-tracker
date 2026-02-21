# Wet Diaper Tracker (local, mobile-first)

## Run
```bash
docker compose up --build
```

Open: http://localhost:8080

## Features
- Log wet diaper events with start + end time
- “Now” shortcuts
- Last 7 days summary (count + total minutes)
- Recent events list + delete

## Data
- SQLite stored in Docker volume `diaper-data`

## Notes
- No auth (local use)
- Uses device local time
