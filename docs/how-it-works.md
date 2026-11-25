# How it works

Several Claude Code chats build one app at once, in layers. One human stays in charge. One coordinator chat keeps everything joined up. Each build chat owns one area and runs short-lived helpers ("lanes") in parallel. A critic lane with a fresh context challenges plans and tries to break finished work.

## The four layers

| Layer | Who | What it does |
|---|---|---|
| 0. Human | You | Decides, approves anything risky, gives the final test sign-off |
| 1. Coordinator | One Claude Code chat | Talks to the human and every chat, owns connectors (SharePoint, email), publishes the Q&A, settles critic disputes. Doesn't build. |
| 2. Build chats | One per area | Scope, write briefs, check lane work, own their files |
| 3. Lanes | Subagents in `.claude/agents/` | Coder, editor, data, researcher, tester and critic. They do one brief and report. They can't start lanes. |

## How a piece of work flows

1. **Scope (`/scope`).** The build chat lists unknowns and writes a plan. The critic challenges both. Open questions go into the registry (`./crew q add`), and the coordinator is told automatically.
2. **Answer.** The coordinator publishes the Q&A (`./crew q export`). People type their answers. The coordinator records each one (`./crew q answer`), and it is routed to the owning chat.
3. **Brief (`/brief`).** Every lane gets a goal, scope, slot, rules, a stop condition and a fixed report format.
4. **Build.** Lanes run in parallel. A lane that needs a one-user resource takes its slot first.
5. **Ship (`/ship`).** AI test, then critic, then the human checklist. Any new AI test run resets the later gates.
6. **Disputes.** There is one fix-or-rebut round. After that, agentctl alerts the coordinator, which decides (`--override "reason"` or a specific change) and tells the human.

## The critic

- **Where it runs:** at exactly two gates, after scope and before ship. It doesn't review every lane: that would add noise, cost and loops.
- **What it can do:** it's read-only. It has no edit or write tools, so it can't drift into building.
- **What a finding needs:** evidence (file:line or exact failing steps), a severity (blocker, fix or nit) and the smallest fix. Five findings at most. Nits never block, and clean work gets PASS. Padding counts as failure.
- **How it's measured:** builders record how many findings they accepted or rejected (`./crew findings`). If most are rejected, `./crew board` tells you to tune `lane-critic.md`.

## What enforces what

| Rule | Enforced by |
|---|---|
| One owner per file | `PreToolUse` hook on Edit/Write (`coord/owners.json`) |
| Coordinator doesn't build | Same hook |
| One editor at a time | `./crew slot`, with a per-lane lock, a timeout (30 minutes by default), a queue and a coordinator force-release |
| Messages reach chats | `UserPromptSubmit` hook |
| Who you are and what you own | `SessionStart` hook |
| Human-only config | Permission deny and the hook protect `owners.json` and `approvals.json` |
| Gate order | `./crew test` and `./crew review` refuse steps out of order |

## Limits

- **Claude Code only.** Plain claude.ai chats can't run hooks.
- **macOS only for now.** Linux likely works but is untested. Windows isn't supported.
- **The edit hook only sees Claude's Edit and Write tools.** Changes made in a browser (e.g. an app builder's tables) or through shell commands aren't policed. List those under `also_owns` in `owners.json`: each chat sees them at start, but they're enforced by convention.
- **Guarded, not tamper-proof.** The human sign-off is refused from inside Claude Code, and every result is logged with who recorded it.
- **Opus everywhere costs more usage.** See the README for switching to a cheaper model.
