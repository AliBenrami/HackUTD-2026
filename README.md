# GolfAR

Mobile companion for real rounds: course selection, hole-by-hole scoring, a scorecard, and statistics calculated from saved holes. Swing analysis and the AR visor settings are separate from scoring.

The arcade AR course is not part of this app.

## Run

```bash
cd mobile
npm install
cp .env.example .env
npx expo start
```

Set `EXPO_PUBLIC_SUPABASE_URL` and `EXPO_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in `mobile/.env`. Those values stay local.

Real courses open on a satellite map. Shot marks and the path sit on that imagery. A phone uses Apple Maps or Google Maps. The web app uses Esri imagery, or MapTiler when `EXPO_PUBLIC_MAPTILER_KEY` is set. Fictional courses keep the sketch map. Mapped courses still need the rows in `mobile/supabase/mapped_courses.sql` applied in the Supabase SQL editor before a round can start on them. The phone keeps score in Supabase and sends bags, shot marks, and caddie cards to the swing server.

```bash
cd backend
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# optional: MONGODB_URI and GEMINI_API_KEY
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Without `MONGODB_URI`, the server keeps the same documents in `backend/data/golfar.json`. Without `GEMINI_API_KEY`, the hole card is the bag fallback and says the model was not used.

Unit tests for scoring and the sample course data:

```bash
cd mobile
npm test
```
