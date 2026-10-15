# Demo video: script and shot list (about 3 minutes)

Record the screen at https://aml-investigation-agent.onrender.com (open it a minute before so it is awake), 1080p, with your voice. Keep each scene short; the numbers on screen do the work.

## 1. The problem (0:00 to 0:20)

**Show:** the landing page, https://aml-agent-home.onrender.com

**Say:** "Banks' transaction monitoring raises thousands of alerts a day, and most are false alarms. Analysts spend their time gathering evidence before they can even judge a case. I built an AI-assisted case manager that does that groundwork, with every AI claim checked and every decision left to a person. It runs on IBM's synthetic AML dataset."

## 2. Detection and the alert queue (0:20 to 0:50)

**Show:** the Alert queue. Point at the priority band, the "Why flagged" reasons and the filters.

**Say:** "An XGBoost model scores every payment. On IBM's own benchmark split it reaches 71 percent F1, above the best model in IBM's paper. It is tuned to catch about nine in ten laundering accounts at a false-alarm rate typical for banks. Alerts arrive ranked, each with the reasons behind its score."

## 3. The AI review (0:50 to 1:40)

**Show:** open ALR-00001 or another high-priority case.
- Flagged payments tab.
- Network tab: highlight the flagged accounts.
- On the right: Why this alert, Red flags, AI assessment with a verified guidance quote.

**Say:** "Opening an alert starts a LangGraph agent. Code builds the case file first, then the agent checks the account's history and counterparties through read-only tools. It names the pattern, recommends an action and cites public FinCEN or FFIEC guidance. Every transaction it cites is verified against the data, and every quote is checked word for word."

## 4. Copilot (1:40 to 2:05)

**Show:** click "Ask the copilot", choose a suggested question, and let the steps stream.

**Say:** "The analyst can ask follow-up questions. The copilot shows each lookup as it runs and flags any transaction it cannot verify."

## 5. Human decision and four-eyes (2:05 to 2:35)

**Show:** as Analyst, choose Escalate for SAR review and record it. Then switch to Supervisor, confirm, and open the History tab.

**Say:** "The AI never decides. The analyst records an outcome with a reason, and an escalation needs a different supervisor. The server refuses anything else. Every step lands in a tamper-evident audit log."

## 6. Results and honesty (2:35 to 3:00)

**Show:** the README's results table on GitHub, or the landing page.

**Say:** "I evaluated the agent once, on 150 alerts frozen before the run. It escalated real laundering twice as often as false alarms, and every cited transaction verified. But it also closed a third of real laundering, which is exactly why the product keeps a human decision on every case. Code, evaluations and model cards are on GitHub."

## Tips

- Two copilot questions are enough; each visitor has three a day on the demo.
- If a step is slow, cut the wait in editing.
- Upload to YouTube as unlisted and put the link in the README and on the landing page.
