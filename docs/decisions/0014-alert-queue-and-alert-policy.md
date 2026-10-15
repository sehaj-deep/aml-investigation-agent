# 0014 Alert queue with on-demand AI review, and the alert policy

Status: accepted (2026-10-14)

## Why

Owner directions, matching how banks run transaction monitoring:

- The analyst should see every alert with its risk before opening anything, and the AI should describe the case and give its opinion when the analyst opens it. The old platform had two queues (alerts and cases), showed the risk only inside a case, and started the AI only when someone clicked "Open case".
- Monitoring must not leave laundering behind; it is tuned for catching laundering, not for accuracy.
- But the queue must be workable. A first version alerted at 98% validation recall: 105,274 test-period alerts, 97.9% false, close to a third of all active accounts. No team can work that.

## Alert policy (`aml_agent/detection/model.py`)

Banks catch as much laundering as they can at a false-alarm rate a team can staff; in industry about 90 to 95% of alerts are false. Measured on validation:

| Laundering accounts caught | Alerts per day | False alerts |
|---|---|---|
| 98% | about 26,000 | 97.6% |
| 91% | about 15,500 | 96% |
| **84% (chosen)** | **about 8,200** | **93%** |
| 72% | about 4,700 | 90% |
| 58% | about 2,100 | 82% |

- The alert threshold is the score that catches 84% of laundering accounts in validation (score 0.293). An account is alerted when any of its payments reaches it.
- Priority bands only order the work, and no alert is dropped. High and medium are the scores at which at least 90% and 50% of flagged validation transactions were laundering. Every other alert is low.
- Below-the-line testing: a seeded random sample of 250 accounts from the zone just under the threshold (down to the score that would catch 95% in validation, 0.033) goes into the queue, marked as samples. They are reviewed like alerts to measure what the threshold misses.

This dataset launders far more than reality (about 0.6% of active accounts within two days), so even a perfect detector raises hundreds of alerts a day here.

Test period (Sep 8 16:12 to Sep 18): 31,518 of 356,396 active accounts alerted. They include 1,968 of the 2,201 laundering accounts (89.4%) and 88.7% of laundering payments; 93.8% of alerts are false.

| Priority | Alerts | Laundering | Share real |
|---|---|---|---|
| High | 1,224 | 1,095 | 89.5% |
| Medium | 1,151 | 252 | 21.9% |
| Low | 29,143 | 621 | 2.1% |
| Below-the-line zone (not alerted) | 68,332 | 225 | 0.33% |

The below-the-line sample of 250 found 2 laundering accounts (0.8%), a rough estimate of the zone's true 0.33%, as expected from a sample this small. Eight laundering accounts score below the zone.

## Workflow

- `scripts/train_detection.py` writes the queue to `data/alert_queue/alerts.jsonl` (no labels; the model and labels stay in `data/detection`). The API streams it into a Postgres `alerts` table at startup when the table is empty (`scripts/load_alerts.py` reloads it), and serves it page by page, highest score first.
- Each alert carries its priority, score, rank, triggering payments (up to 25) and the top three reasons in plain words. Its work status comes from its case: new, AI review in progress, ready for review, closed.
- Opening an alert (`POST /alerts/{id}/open`) creates its case once (an advisory lock makes concurrent opens share one case) and queues the AI review. The worker saves the code-built case file (flagged payments, network, red flags, patterns) as soon as it exists, so the analyst sees the facts within seconds. The AI's assessment follows.
- Quota is spent only on alerts someone opens.
- The case file starts with why the alert was raised. The prompt (p8) says monitoring reasons are leads, not proof, that most alerts are false alarms, and that "close" is only for clearly ordinary activity.
- The UI has one alert queue. The case screen uses plain language: no model or prompt names, token counts, rule codes or internal labels; the history reads as sentences, with technical details on request. Model and instruction versions stay on the Governance page.

## Evaluation sample

`evals/alerts/detection/` holds 50 alerts from each band (seeded), 55 of 150 real. Sampling by band keeps the false alarms of the low band in the test without making the sample almost all benign.

## Limits

The low band is still large (29,143 alerts, 2.1% real); AI triage of low alerts is the obvious next step. Alert volume in the test period is about twice the validation figure because the test period is longer (it runs to Sep 18).
