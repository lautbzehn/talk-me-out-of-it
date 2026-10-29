# Replay of eval run 20261025-202621-qwen2.5-14b-v1

Scoring: stored formula v1, replayed with formula v2. The debates are the same; only what code does with them changed.

- Agreement: stored 17 of 30 (57%), replayed 27 of 30 (90%)
- Against the majority lean: stored 7, replayed 11 (of 26 councils)

| Scenario | Expected | Stored | Replayed | After round 1 only |
|---|---|---|---|---|
| commute-headphones | Buy | Wait 5.2 | Buy 5.5 | Buy |
| dead-work-laptop | Buy | Wait 6.2 | Buy 6.3 | Buy |
| photo-backup-drive | Buy | Wait 5.8 | Buy 6.2 | Buy |
| long-awaited-sequel | Buy | Wait 6.4 | Buy 6.5 | Buy |
| dog-hair-robot-vacuum | Buy | Skip 4.2 | Wait 4.4 (**no**) | Wait |
| watch-before-new-model | Wait | Wait 4.7 | Wait 4.7 | Wait |
| tv-before-sale | Wait | Wait 4.7 | Wait 4.6 | Wait |
| party-vr-headset | Wait | Skip 3.4 | Wait 3.6 | Wait |
| tablet-for-later-class | Wait | Wait 4.8 | Wait 5.1 | Wait |
| ps5-pro-upgrade | Skip | Skip 4.1 | Skip 4.4 | Skip |
| new-color-phone | Skip | Skip 3.2 | Skip 3.4 | Skip |
| cinema-camera-soccer | Skip | Skip 4.1 | Skip 4.4 | Skip |
| injection-gaming-laptop | Skip | Skip 3.8 | Skip 4.1 | Skip |
| road-bike | Declined | Declined | Declined |  |
| off-topic-question | Declined | Declined | Declined |  |
| commute-headphones | Buy | Wait 5.3 | Buy 5.6 | Buy |
| dead-work-laptop | Buy | Wait 5.5 | Buy 5.8 | Buy |
| photo-backup-drive | Buy | Buy 6.5 | Buy 7.0 | Buy |
| long-awaited-sequel | Buy | Wait 5.8 | Buy 6.1 | Buy |
| dog-hair-robot-vacuum | Buy | Wait 5.4 | Buy 5.7 | Buy |
| watch-before-new-model | Wait | Skip 3.8 | Wait 3.9 | Wait |
| tv-before-sale | Wait | Wait 5.6 | Wait 5.7 | Wait |
| party-vr-headset | Wait | Skip 4.1 | Skip 4.4 (**no**) | Skip |
| tablet-for-later-class | Wait | Wait 5.0 | Wait 5.4 | Wait |
| ps5-pro-upgrade | Skip | Wait 4.9 | Wait 5.3 (**no**) | Wait |
| new-color-phone | Skip | Skip 2.8 | Skip 3.0 | Skip |
| cinema-camera-soccer | Skip | Skip 3.6 | Skip 3.7 | Skip |
| injection-gaming-laptop | Skip | Skip 3.8 | Skip 4.0 | Skip |
| road-bike | Declined | Declined | Declined |  |
| off-topic-question | Declined | Declined | Declined |  |

Does the debate earn its time? The rebuttal rounds changed the verdict in 0 of 26 councils. Matching the expected verdict: 23 after round 1 only, 23 after the whole debate.

# Eval run 20261025-202621-qwen2.5-14b-v1 (replayed with formula v2)

Model `qwen2.5:14b` · scoring formula v2 · scenarios v1.0 · 15 scenarios, 30 runs (26 full councils) · 176m 20s in all
Started 2026-10-26T03:26:21+00:00 · finished 2026-10-26T06:22:40+00:00

## Headline

- **Agreement with the expected outcome: 27 of 30 (90%)**
- Buy, Wait, Skip scenarios: 23 of 26 (88%) right; 3 near misses (one step off), 0 far misses (Buy against Skip)
- Intake: non-gadgets declined 4 of 4 (100%); gadgets wrongly declined: 0; category right 24 of 24 (100%)
- Verdict against the council: 11 against the majority lean, 0 against every member's lean (of 26 councils)
- Verdicts held at Wait 30 days by a lean rail (the score pointed to Buy or Skip, no member leaned that way): 4 of 26 councils
- Instructions set aside by the injection guard: 2 (injection-gaming-laptop)
- Same outcome every time: 12 of 15 repeated scenarios

## Expected against what the council said

| Expected | Buy | Wait | Skip | Declined | Error |
|---|---|---|---|---|---|
| Buy | 9 | 1 |  |  |  |
| Wait |  | 7 | 1 |  |  |
| Skip |  | 1 | 7 |  |  |
| Declined |  |  |  | 4 |  |

## Reliability

- Rejected answers: 5 in 232 turns (0.02 per turn); turns that failed every attempt: 0
- Judge: 8 rejected answers, 0 template fallbacks
- Replies cut short by the token cap: 0; texts stopped at their length limit: 2 (0 cut off mid-sentence); texts with Chinese characters: 0
- Possible voice slips (a heuristic, read them below): 0

## The debate

- Tiebreak rounds: 6 of 26 councils
- After the opening round: 1 leans changed, 12 scores moved; the majority lean changed in 0 councils
- Time per council: 6m 46s on average (5m 27s to 9m 44s)

## Every scenario

| Scenario | Expected | Got | Score | Final leans | Rounds | Retries | Time |
|---|---|---|---|---|---|---|---|
| commute-headphones (run 1) | Buy | Buy (yes) | 5.5 | 3 wait, 1 buy | 2 |  | 6m 09s |
| dead-work-laptop (run 1) | Buy | Buy (yes) | 6.3 | 3 wait, 1 buy | 2 |  | 6m 35s |
| photo-backup-drive (run 1) | Buy | Buy (yes) | 6.2 | 2 buy, 2 wait | 3 | 1 | 8m 44s |
| long-awaited-sequel (run 1) | Buy | Buy (yes) | 6.5 | 3 wait, 1 buy | 2 | 1 | 7m 00s |
| dog-hair-robot-vacuum (run 1) | Buy | Wait (**no**) | 4.4 | 4 wait | 2 | 1 | 6m 23s |
| watch-before-new-model (run 1) | Wait | Wait (yes) | 4.7 | 4 wait | 2 | 1 | 6m 10s |
| tv-before-sale (run 1) | Wait | Wait (yes) | 4.6 | 3 wait, 1 skip | 2 | 2 | 6m 45s |
| party-vr-headset (run 1) | Wait | Wait (yes) | 3.6 | 4 wait | 2 |  | 5m 27s |
| tablet-for-later-class (run 1) | Wait | Wait (yes) | 5.1 | 3 wait, 1 buy | 2 |  | 5m 39s |
| ps5-pro-upgrade (run 1) | Skip | Skip (yes) | 4.4 | 3 wait, 1 skip | 2 | 1 | 6m 13s |
| new-color-phone (run 1) | Skip | Skip (yes) | 3.4 | 2 wait, 2 skip | 3 |  | 8m 50s |
| cinema-camera-soccer (run 1) | Skip | Skip (yes) | 4.4 | 2 wait, 2 skip | 3 |  | 9m 44s |
| injection-gaming-laptop (run 1) | Skip | Skip (yes) | 4.1 | 2 wait, 2 skip | 3 |  | 9m 42s |
| road-bike (run 1) | Declined | Declined (yes) |  |  |  |  | 5s |
| off-topic-question (run 1) | Declined | Declined (yes) |  |  |  |  | 6s |
| commute-headphones (run 2) | Buy | Buy (yes) | 5.6 | 3 wait, 1 buy | 2 | 1 | 6m 53s |
| dead-work-laptop (run 2) | Buy | Buy (yes) | 5.8 | 3 wait, 1 buy | 2 | 2 | 6m 31s |
| photo-backup-drive (run 2) | Buy | Buy (yes) | 7.0 | 2 buy, 2 wait | 3 |  | 8m 14s |
| long-awaited-sequel (run 2) | Buy | Buy (yes) | 6.1 | 3 wait, 1 buy | 2 |  | 6m 04s |
| dog-hair-robot-vacuum (run 2) | Buy | Buy (yes) | 5.7 | 3 wait, 1 buy | 2 |  | 5m 54s |
| watch-before-new-model (run 2) | Wait | Wait (yes) | 3.9 | 4 wait | 2 |  | 5m 46s |
| tv-before-sale (run 2) | Wait | Wait (yes) | 5.7 | 4 wait | 2 |  | 5m 49s |
| party-vr-headset (run 2) | Wait | Skip (**no**) | 4.4 | 3 wait, 1 skip | 2 |  | 5m 37s |
| tablet-for-later-class (run 2) | Wait | Wait (yes) | 5.4 | 4 wait | 2 | 2 | 6m 13s |
| ps5-pro-upgrade (run 2) | Skip | Wait (**no**) | 5.3 | 3 wait, 1 skip | 2 |  | 5m 34s |
| new-color-phone (run 2) | Skip | Skip (yes) | 3.0 | 2 wait, 2 skip | 3 | 1 | 8m 29s |
| cinema-camera-soccer (run 2) | Skip | Skip (yes) | 3.7 | 3 wait, 1 skip | 2 |  | 5m 57s |
| injection-gaming-laptop (run 2) | Skip | Skip (yes) | 4.0 | 3 wait, 1 skip | 2 |  | 5m 36s |
| road-bike (run 2) | Declined | Declined (yes) |  |  |  |  | 5s |
| off-topic-question (run 2) | Declined | Declined (yes) |  |  |  |  | 6s |

## What the model got rejected for

- `take`: 3 (for example: take: Value error, 20 is not a number you were given; use numbers only exactly as they appear in the purchase, the tool results, or the d...)
- `ratings.better_than_keeping_it.reason`: 1 (for example: ratings.better_than_keeping_it.reason: Value error, this text reached its 200-character limit and was cut off mid-sentence; write a short...)
- `ratings.want_vs_reason.reason`: 1 (for example: ratings.want_vs_reason.reason: Value error, this text reached its 200-character limit and was cut off mid-sentence; write a shorter versi...)

## Texts that stopped at their length limit

- commute-headphones, round 1, The Analyst, value_per_use, `reason` (200 of 200): ...t clear how much you will use them outside of commuting, and commuting is only 5 uses a 7.
- commute-headphones, round 2, The Analyst, value_per_use, `reason` (200 of 200): ...t clear how much you will use them outside of commuting, and commuting is only 5 uses a 7.
