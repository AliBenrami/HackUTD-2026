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

Unit tests for scoring and the sample course data:

```bash
cd mobile
npm test
```
