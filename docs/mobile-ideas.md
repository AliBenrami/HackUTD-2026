# GolfAR mobile — ideas worth building

Nothing here is implemented. This is the list to pick from.

Tracks this is aimed at, from the Devpost and MLH pages for HackUTD 2026:

- **Best Use of MongoDB Atlas** (MLH). Prize is an M5Stack kit per person. The prompt is only “build a hack using MongoDB Atlas,” so the win is Atlas doing work the app cannot do without it.
- **Best Use of Gemini API** (MLH). Swag. The prompt’s examples are chatbots and summaries. A golf card that calls tools and returns a checked JSON object is a stronger use of the API than a chat box.
- MLH tracks can all be entered. Sponsor tracks are capped at three, plus one HackUTD track. NVIDIA is not part of this plan.

Supabase stays. Auth, rounds, hole scores, and swing video files already have row-level security and a working client. Atlas takes the data that is nested, personal, and currently stuck on the phone.

## What is already good

Leave the scoring math alone. Saved holes drive the averages. Penalties are stored for display and are already inside the stroke count. Par 3s are left out of fairways. Unfinished rounds are left out of “best round.” That behavior is tested.

The swing screen is the other real product. A clip can be recorded or imported, sent to the analysis server, and reviewed with pose, club boxes, a ball trace, and a comparison against a reference model. The comparison already builds a small packet for a future model (`buildLlmInsightRequest`) and refuses to send video, joint coordinates, or club boxes. `LlmSwingNarrator` is the empty slot. The template narrator is the fallback and should stay the fallback.

The visor screen is honest about being a simulation. Distance, elevation, score, and wind are preferences. Only the score snapshot has a payload (`ScoreSyncPayload`), and `MockARDeviceBridge` accepts it when the fake link is on. Elevation and wind are saved and never read by a screen.

Three courses exist, each with four tees, a rating, a slope, and a stroke index per hole. None of those rating numbers are used after the course page. The contour map is generated from the course id and hole number. It is a sketch, and it should keep being labeled as one until a hole has a real shape.

## Atlas, as the store the new features read

One database, `golfar`, four collections. The phone never holds the connection string. A small HTTP service (the existing swing server is the natural place) reads and writes Atlas.

**`swings`** — one document per analyzed clip. This replaces `AsyncStorage` key `golfar.swingMeasurements.v1`. Today a reinstall drops every measured swing, and a second phone never sees them. The document is the analysis response as it already exists: fps, size, model names, frames, cues, disclaimer, plus `userId`, `videoId`, `club`, and `createdAt`.

Add one field the phone computes before insert, `angleVector`: sixteen numbers, lead and trail elbow at the eight comparison phases, using `null` only when that phase was unusable. Atlas Vector Search indexes that field. “Swings like this one” is a cosine search over those numbers. No embedding model. The vector is the measurement.

**`bags`** — one document per player. A list of clubs with a carry in yards, the unit the player picked in settings. Seed it with a normal amateur bag the player can edit: driver 230, 3-wood 215, 5-iron 175, 7-iron 155, 9-iron 135, pitching wedge 120, sand wedge 90. Those numbers are a starting bag, shown as such, and every recommendation says they are the player’s entered carries.

**`hole_notes`** — one document per saved hole, written in the same action as `saveHoleScore`. It holds what the score table does not: miss (`left`, `right`, `short`, `long`, or absent), green in regulation, pin (`front`, `middle`, `back`), club intended, and the id of the caddie card that was showing. Strokes and par are copied so the tendency query does not join to Postgres.

**`caddie_runs`** — one document per card. The trigger, every tool call with its arguments and result, the model id, the validated card, and the time. This is the thing to open in Compass during judging. If the collection is empty, Gemini was a caption.

Tendencies are an aggregation on `hole_notes`, not a stored guess:

- average score against par, grouped by par
- miss counts among holes where a miss was entered
- greens in regulation among holes where the toggle was touched
- putts stay in Supabase; the card can receive them from the snapshot the app already has

Run that pipeline when a hole is saved, and cache the result on the bag document under `tendencies` with `updatedAt`. The card reads the cache. The pipeline is what you show.

Indexes worth creating in front of a judge: vector index on `swings.angleVector`, and a normal index on `hole_notes` by `userId` and `savedAt`.

## Gemini, as a card rather than a chat

Use a Gemini 3 model from AI Studio. Google’s docs limit “tools and structured JSON in one request” to Gemini 3. On an older model, split it: one call with tools, then a second call with the tool results and a JSON schema and no tools. Copy the model id out of the picker when you build it. `gemini-2.5-pro` and `gemini-2.5-flash` are already on a deprecation path.

The key stays on the server. The phone asks for a card and gets a card.

### Hole card

The round screen asks for a card when the hole opens, and again when the pin, the bag, or the wind toggle changes. There is no text field.

Tools, all implemented by the server, all reading Atlas or a public weather API:

1. `get_hole` — par, yards for the selected tee, stroke index, course, tee name. From the catalog the app already ships.
2. `get_bag` — clubs and carries.
3. `get_tendencies` — the aggregation cache. Empty is a legal result.
4. `get_weather` — Open-Meteo, no key, using a fixed coordinate per course (Dallas, Scottsdale, Galveston are already the three locations). Return wind speed, gust, and direction. Skip the call when the wind preference is off, and tell the model wind was not requested.
5. `get_latest_swing` — the latest `angleVector` gaps for the club the bag would pick. Reuse the comparison packet. Omit it when that club has never been filmed.

After the tools return, Gemini fills this object and nothing else:

```json
{
  "club": "7-iron",
  "carryYards": 155,
  "adjustedYards": 160,
  "aim": "center",
  "missTo": "left",
  "windNote": "Into a light breeze, so the target is a club longer than the card yardage.",
  "reasons": ["string", "string"],
  "assumptions": ["Carries are the bag you entered."],
  "confidence": "limited"
}
```

`reasons` is capped at three. `confidence` is `limited` or `fair`. Fair requires a bag, a completed hole count you are willing to name in the prompt (ten is enough), and a weather reading if wind is on. Anything thinner is `limited`.

The server checks the JSON before it is stored or shown. The club must be in the bag. The carry must match that club. Adjusted yards must be within a sane band of the hole yardage. On any failure, or if the API errors, the phone shows the deterministic card: the club whose carry is closest to the hole yardage, aim center, miss taken from the most common miss in the aggregation, confidence `limited`, and a line that says the model was not used. The round is still playable with the network down.

The card sits under the hole header on the round screen. Club, carry, aim, one miss, and the wind line if wind is on. Reasons open on a tap. The disclaimer is one line and stays visible: this is a suggestion from the bag and the saved holes, and it is not a measurement of the shot.

Write the run to `caddie_runs` either way, including fallback runs, with `source: "gemini"` or `source: "fallback"`.

### Swing lines

Point `LlmSwingNarrator` at Gemini. The input is the object `buildLlmInsightRequest` already builds. The output is validated back into `SwingInsight`: same phase, same metric, the degrees preserved, the existing disclaimer kept, no promise of a score, no medical advice. If validation fails, the template sentences render. The screen copy does not need a new layout.

### Round recap

When a round is finished, one Gemini call with no tools. The input is the saved hole notes, the score summary the app already computes, and the cards that were shown. The output is four lines: what the score was, where the misses clustered, which club kept coming up, and one thing to film next. Store it on a `rounds` document in Atlas keyed by the Supabase round id. Show it at the top of that round’s scorecard. Same rule as the card: if the call fails, the scorecard stays as it is.

## Features that make the card true

These are the product. Atlas and Gemini are how they are stored and worded.

**Bag.** A screen under settings. Add, remove, and edit a carry. The record screen currently opens as Driver unless a query param says otherwise. The record button should ask for a club from this bag first.

**Miss and green.** On the hole, next to fairway: Left, Right, Short, Long, Skip. A second toggle, Green in regulation, with Skip as the default so old rounds stay honest. Par 3s keep the fairway rule they have now. Both fields live on `hole_notes`. The stats screen can show miss direction and greens once a handful of holes have them. Until then it says they have not been entered, the same way putts already does.

**Pin.** Front, middle, back. Front subtracts 8 yards from the target, back adds 8, middle changes nothing. Say that on the card. It is a convention, not a laser.

**Wind.** Open-Meteo into the card, and into the round screen when the existing wind switch is on. Show speed and direction in words (“8 mph into you”). Leave elevation off the card until a hole has a real elevation change. The switch can stay in settings.

**Similar swing.** On a measured swing, one row: the closest other swing by `angleVector`, with the club and the date. If the nearest neighbor is far, say so and show nothing else. This is the Atlas Vector Search demo, and it is also useful on the range.

**Hole rail.** Eighteen marks under the hole title, colored with the same result colors the scorecard uses, blank when the hole is blank. Tapping one goes through the save-or-discard prompt the arrows already use.

**Course handicap, optional.** A handicap index on the player. Course handicap for a full round is index × (slope / 113) + (rating − par), rounded to the nearest integer. Par, slope, and rating are already on the tee. Show it on the course page and as a net column on the scorecard only after an index is entered. Nine-hole rounding can wait.

**Putts one tap away.** The stats page already explains itself when putts are missing. The stepper is behind “Putts, penalties, fairway.” Put the putt stepper on the hole, and leave penalties and fairway in the disclosure.

## Polish that is worth the time

- The all-rounds bar chart draws every saved hole in a row, so hole 18 of one round sits next to hole 1 of the next. A better chart is the average against par for hole number 1, hole number 2, and so on, across finished rounds at that course. One course filter is enough.
- The contour stays. Add the word “Sketch” on the map until a hole has a drawn shape. A drawn shape is a later Atlas document (`fairway` as a polyline, green as a point). The generator you have can keep filling holes that have no shape.
- Settings should keep saying the visor link is simulated. When a real payload exists, the row can say “score and card ready to send” without claiming a radio connection.
- Sample rounds stay labeled. The card should ignore them when it builds tendencies. They are a demo of the scorecard, and they are a bad model of the person holding the phone.

## AR, later, and only the version the glasses can actually show

The visor is a Viture Luma Ultra on the Linux app. The panel is about 52 degrees on the diagonal, mono is the path that has been seen on the hardware, and black is clear on the combiner. A full hole map in the glasses will feel like a small monitor. A few words will not.

The phone remains the computer. Gemini and Atlas stay on the server. The glasses draw the card the phone already validated.

**The first real link** is an extension of `ScoreSyncPayload`: club, adjusted yards, wind line, score relative to par. The AR app draws that as a single block in the lower third. `MockARDeviceBridge` can start writing the payload to a file the AR process reads, which is a real handoff and still an honest substitute for a socket.

**The range ghost.** A measured swing already has a pose per frame. Playing that skeleton in the glasses, locked to a printed marker on the floor, uses the ArUco table lock that is already in the AR app. The player stands beside it and looks at their own positions at the top and at impact. This fits the hardware better than a yardage graphic on a fairway, because the marker work is done and the range does not ask for survey-grade registration.

**A paper yardage card.** The same marker printer can put a marker on a card. The glasses lock the club and the wind line to that card. The phone has the data. The card is the anchor. That is the on-course version that does not pretend the glasses know where the pin is.

**A look-down-the-hole distance** needs the phone’s GPS and compass, and it should be described as good for the distance to the center of the green. It is the wrong tool for a four-yard pin read. Build it after the card is good on the phone.

Skip a live swing coach in the glasses. The pose server, the model call, and a 52-degree display will not land in one weekend, and the phone already shows the filmed swing well.

## Order, if we build any of this

1. Atlas collections and the swing-document write, so measured swings survive.
2. Bag, miss, green, pin. The card is fiction without them.
3. Gemini hole card with the fallback, and the run log.
4. Wind switch wired to Open-Meteo.
5. Similar-swing search.
6. Swing lines through the narrator slot.
7. Recap on the finished scorecard.
8. Hole rail, putts, the chart, the sketch label.

1 through 4 is a demo. 5 is the Atlas feature a judge can tell from a plain insert. 6 and 7 are the rest of the Gemini track. 8 is the round screen feeling finished.
