<!-- agent-lanes -->
# Team rules (every chat)

Several Claude chats build this project at once. Hooks tell you who you are at session start and deliver new messages with each prompt. Coordination runs through `./crew`, which is pre-approved, so no prompt appears. Never run `./crew start` yourself.

## Always
- **Scope before code.** Log open questions before building: `./crew q add <owner> "<question>" --phase before`. Don't build on a guess.
- **Stay in your lane.** Only edit what you own (`coord/owners.json`). An edit hook blocks everything else. Message the owner instead: `./crew send <owner> "..."`.
- **One user per shared resource.** Run `./crew slot take <name> --lane <lane>` before touching it, then `./crew slot release <name> --lane <lane>` the moment you're done, even on failure. Exit code 3 means busy: wait for the inbox message and don't retry in a loop.
- **Status at key moments:** `./crew status <started|blocked|milestone|problem|done> "<one line>"`.
- **Least code that works.** Keep files and functions small. Aim for PRs of about 500–1,000 lines, each with a short review guide.
- **Done means three passes:** AI test, then critic, then human. All three must show on `./crew board`.

## Human only (never do these yourself)
- Deploying, sharing, adding users, deleting data, entering credentials, spending money.
- Anything sent outside the team, such as messages to a client or changes to a client's live systems.
- Editing `coord/owners.json` or `coord/approvals.json`.
- Exception: a standing approval in `./crew approvals` that covers the action exactly. If you use one, name its ID.
