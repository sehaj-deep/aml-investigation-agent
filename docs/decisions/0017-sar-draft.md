# 0017 Suspicious activity report (SAR) draft

Status: accepted (2026-10-14)

## Why

An escalation ends in a suspicious activity report. Writing its narrative is a large part of an investigator's time, and it must be exact: wrong amounts, invented parties or a claim that the report was filed are serious errors.

## Choice (`aml_agent/agent/sar.py`)

- **When:** available once a supervisor confirms an escalation. The analyst asks for the draft, so quota is spent only when needed (at most 5 AI drafts per case).
- **Code builds every fact:**
  - the subject and parties;
  - the review period;
  - the evidence transactions in time order, with exact amounts;
  - totals per currency (never added across currencies);
  - the red flags, with a note that they cover all activity in the period;
  - the decision trail;
  - the filing due date: 30 days after the confirmed escalation, the usual US limit.
- **The AI writes only the narrative,** in one call with no tools, in five sections: introduction, subjects (who), activity (what, when, where, how), why it is suspicious, conclusion.
- **Checks before anyone sees it.** Warnings are raised for:
  - every cited transaction that is not in the evidence;
  - every amount that matches no evidence amount or per-currency total (times and dates are not mistaken for amounts);
  - a long dash;
  - any claim that the report was filed or submitted.
- **Review and approval:**
  - the analyst edits and saves; every save is a new version and is checked again;
  - an unedited AI draft cannot be approved;
  - a supervisor who is not the last editor approves it (four-eyes);
  - an approved report is final.
- **Export:** the report downloads as a Markdown document, marked as sandbox output.
- **Audit:** drafting, edits and approval go to the audit log.

## Measured (live, gpt-oss:20b-cloud)

Two drafts for one escalated case: 18 seconds and about 2,600 to 3,200 tokens each. In both drafts, every transaction and amount matched the evidence. The first draft surfaced two checker false alarms (fractional seconds of decision times read as amounts) and a "has been filed" claim; both were fixed (prompt s2, timestamps to the minute, a filed-claim check). The second draft still said the report was filed, and the check flagged it for the analyst.

## Limits

No customer data exists in this dataset, so names, addresses, occupations and account-opening details are absent; a real SAR needs them. Nothing is filed with any authority.
