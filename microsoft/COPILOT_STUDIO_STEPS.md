# Copilot Studio: Program Rules Assistant (about 20 minutes)

**What you build:** a Copilot Studio agent that answers account managers' questions about the sales programs (what happens when an agency misses its target, how attainment is defined, AAdvantage Business crediting), grounded only on the four synthetic program documents in `docs/program_docs/`. It's the Microsoft-side version of the Sales Copilot's `search_program_docs` tool (notebook 13).

**What it isn't:** connected to live Databricks data. That needs the Azure Databricks connector or a managed MCP server in the same Microsoft Entra tenant; this project's Databricks workspace is Free Edition on AWS. Say that plainly.

**Stop rule:** if the Copilot Studio trial won't start within 15 minutes, stop.

## 1 · Start the trial

1. Go to `copilotstudio.microsoft.com` and sign in with the **same work account** you used for Fabric.
2. If asked, start the free trial and pick your country. The trial lets you build and test agents in the test chat pane; publishing to Teams needs a paid license, which is fine for this demo.

## 2 · Create the agent

1. **Create → New agent**, then switch to **Configure** (skip the chat-style setup).
2. **Name:** `Program Rules Assistant`
3. **Description:** `Answers account managers' questions about corporate contract, agency incentive and AAdvantage Business program rules. Synthetic demo documents.`
4. **Instructions** (paste):

```
You help airline account managers understand sales program rules.
Answer only from the uploaded program documents. If the documents don't cover the question, say so and suggest asking the sales operations team.
Quote thresholds and steps exactly as the documents state them (for example "below 90%", "within 30 days").
Keep answers under 120 words, in plain language, and name the document you used.
For account-specific numbers (an account's attainment or share), say that those come from the Deal Desk app or the Genie Agent, not from these documents.
These are synthetic demo documents, not any airline's actual policy.
```

5. **Knowledge → Add knowledge → Files** → upload the four files from `Documents/agency-performance-copilot/docs/program_docs/`.
6. If there's a setting to use general knowledge or web search, **turn it off**, so answers come only from the documents.
7. **Create**. Wait until the files show as ready (a minute or two).

## 3 · Test it (the demo)

In the **Test** pane, ask:

| Question | A good answer mentions |
| --- | --- |
| What happens when an agency misses its incentive target? | First Red quarter: review and an action plan; second consecutive Red quarter: incentive rate reviewed |
| How is contract attainment calculated? | Actual passengers in eligible markets ÷ target passengers; QSI + points capped at 95%; eligible = QSI ≥ 5% |
| An account is at 85% attainment. What should I do? | At risk (below 90%): recovery plan within 30 days |
| What is Zhang PLC's attainment? | It should say that comes from the Deal Desk app or Genie, not these documents |

The last question is the guardrail test: the agent should **not** invent a number. Screenshot the test pane with two answers.

## What to say

> "I built the program-rules part in Copilot Studio, grounded only on the program documents, with instructions to quote thresholds exactly and to send account-specific numbers to the governed tools. In production it would also call the Genie Agent through the Azure Databricks connector in Teams, so an account manager gets rules and numbers in one place. That needs Azure Databricks in the same tenant, which my Free Edition workspace isn't."
