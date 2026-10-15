# 0015 Analyst outcomes and a server-enforced four-eyes rule

Status: accepted (2026-10-14)

## Why

The decision buttons asked the analyst to "accept" or "override" the AI. An analyst resolves an alert; the AI's opinion is one input. The four-eyes rule for escalations was enforced only by the screen, so the API accepted an escalation from anyone.

## Choice

- **Analyst outcomes** on a case ready for review:
  - close as a false alarm;
  - escalate for SAR review;
  - needs more information (the AI investigates again, at most two rounds).
- **An escalation waits for a supervisor:** confirm it (the case closes as escalated) or return it to the analyst with a reason.
- **The four-eyes rule is checked in two places:**
  - the API (`store.record_decision`) refuses a confirmation from a reviewer without the supervisor role, or from the person who escalated (HTTP 409);
  - the workflow's supervisor step checks the same rule again and stops the case instead of escalating (fail-safe).
- **Every decision records the reviewer's name and role** in the audit log. The screen shows whether the outcome agrees with the AI recommendation, for later measurement.
- **Statuses:**
  - Final: closed, escalated.
  - Waiting: ready for review, awaiting supervisor approval.

## Limits

There is no login, by design (an open sandbox). Names and roles are self-declared, so the rule is a checked and audited workflow control, not authentication. A real deployment would take identities from the bank's single sign-on.
