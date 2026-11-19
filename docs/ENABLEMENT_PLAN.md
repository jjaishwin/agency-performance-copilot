# Enablement plan: getting account managers to use it

A sales AI tool succeeds when account managers use it before calls and trust what it says. This plan takes the copilot from a working prototype to a tool a sales team relies on, in four phases, with a measure that decides each step.

## 1 · Pilot (weeks 1–6)

- **Who:** 5–8 account managers in one region, plus their sales director. Include one sceptic.
- **What they get:** the Deal Desk app (what-if, Ask Genie), the pre-call brief, and the dashboard. Nothing else.
- **Kick-off (45 minutes):** start from their week, not the tool. "Which accounts are you calling this week?" Then show the answer for their accounts.
- **Support:** a one-page "how to ask Genie" guide with good and bad questions, 30-minute office hours twice a week, and a named champion in the region.

## 2 · Measure

| Measure | Why | Pilot target |
| --- | --- | --- |
| Weekly active account managers | Are they using it at all? | 6 of 8 by week 4 |
| Time to prepare a key-account call | The time saved is the business case | Down from about an hour to 15 minutes |
| Genie core benchmark accuracy | Is it still right as questions change? | At or above the 90% gate every release |
| Thumbs-down rate on answers | What users think is wrong | Below 10%, every one reviewed |
| Accounts flagged At risk that get a recovery plan | Does insight turn into action? | Most flagged accounts within 30 days |

Time-saved figures are estimates to validate in the pilot, not results.

## 3 · Feedback loop

1. **Every week,** review the questions people actually asked (Genie monitoring) and every thumbs-down.
2. **Root cause first:** wrong data, missing definition, ambiguous question, or a real model mistake. Fix it in the right place (see `docs/EVAL_REPORT.md` for how this was done during the build).
3. **New kind of question → new benchmark.** The release gate grows with real usage.
4. **Tell the pilot group what changed.** People keep using a tool that visibly listens.

## 4 · Expand

Move region by region once two conditions hold for four weeks: weekly use at the pilot target, and accuracy at or above the gate. Each new region gets its own champion and its own region mapping in Unity Catalog, so access follows the same rule.

## Guardrails that make trust possible

- **Every number comes from certified data,** defined once in metric views; Power BI, Genie and the app agree.
- **People see only their region,** enforced in Unity Catalog for every tool.
- **Accuracy is published,** not assumed: the monitoring page shows the benchmark history, including what still fails.
- **Clear limits:** questions Genie can't yet answer reliably (for example month-over-month windows) stay with an analyst, and the guide says so.

## Change management

- **Sales leadership sponsor** opens the pilot and uses the dashboard in a team meeting.
- **Analysts are partners, not replaced:** they own the benchmark set and the hard questions.
- **No forced switch:** existing reports keep running until the pilot shows the new path is faster and trusted.
