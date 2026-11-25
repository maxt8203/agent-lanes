# agent-lanes

Run a small team of Claude Code chats on one project. There's a coordinator, one build chat per area of your app, parallel helper agents ("lanes") doing the work, and a sceptical critic checking it. **You stay in charge.** The rules are enforced by hooks and a small CLI, so they hold even when a chat forgets them.

<p align="center">
  <img width="700" alt="agent-lanes layers" src="https://github.com/user-attachments/assets/5d90811f-079c-4e78-9b7c-17d536165ba7" />
</p>

> **Requirements:** macOS · [Claude Code](https://code.claude.com/docs/en/setup) (needs a paid Claude plan) · Python 3.8+
> **Platform:** built for macOS. Windows isn't supported yet. Linux will probably work, but it isn't tested.
> **Usage:** every chat and lane runs on **Opus**, for quality. That uses up your Claude limits much faster than Sonnet would. See [Use a cheaper model](#use-a-cheaper-model).


## Quick start (3 steps)

**Step 1: Install Claude Code** (skip this if you already have it)
```bash
brew install --cask claude-code && claude
```
Log in when it asks, then quit with `/exit`. Claude Code needs a paid Claude plan. If you don't have Homebrew, see the [official setup guide](https://code.claude.com/docs/en/setup).

**Step 2: Install agent-lanes.** Open Terminal in your project folder and paste:
```bash
curl -fsSL https://raw.githubusercontent.com/maxt8203/agent-lanes/main/get.sh | bash
```
It asks two questions: your name, and your build chats (one per area of your app, e.g. `core,pricing`).

**Just want to see it work?** Paste this instead. It makes a demo folder with a small job ready to go:
```bash
mkdir agent-lanes-demo && cd agent-lanes-demo && curl -fsSL https://raw.githubusercontent.com/maxt8203/agent-lanes/main/get.sh | bash -s -- --demo
```

**Step 3: Start the team**
```bash
./crew up
```
This opens one Terminal window per chat, already running.
- **First time only:** choose **Yes** when Claude Code asks to trust the folder. The other windows open after that.
- **Demo:** the job starts by itself in the `core` window. Watch it go from scope to brief to build to AI test to critic, then do your sign-off.

**Your window:** `./crew board` (everything at a glance) · `./crew inbox` · `./crew test <item> human pass "note"`

> ⚠️ **On a brand-new Mac,** the first time anything uses Python, macOS pops up a box asking to install Apple's free developer tools. Click **Install**, wait 5–10 minutes, then paste the line again. If macOS asks whether Terminal may control Terminal (for `./crew up`), click **OK**.

**Prefer not to pipe scripts into bash?** Click **Code** at the top of this page, choose **Download ZIP**, then run `python3 install.py ~/my-app` from the unzipped folder. You can also start each chat by hand with `./crew start <chat>`.

**Using a chat**
- Type `/scope <what to build>` to list the unknowns and have the critic challenge the plan.
- Type `/brief <lane> <goal>` to hand work to a lane.
- Type `/ship <item>` to run the AI test and critic and get the item ready for you.

---

## How work flows

1. **Scope.** The build chat lists what's unknown. The critic challenges the plan, and the open questions go into a shared Q&A.
2. **Answer.** The coordinator exports the Q&A (`./crew q export`) so people can answer in Word or wherever they work. Each answer is routed to the right chat automatically.
3. **Build.** Lanes work in parallel. A shared, one-user-at-a-time resource (like an app editor) is handed out as a slot.
4. **Check.** Each item passes three gates in order: **AI test, then critic, then you.** It isn't done until all three show ✅ on `./crew board`.
5. **Disputes.** The builder fixes or rebuts each critic finding once. If they still disagree, the coordinator decides and tells you. You aren't pulled in.

## What's enforced, not just written down

| Rule | How |
|---|---|
| Each chat edits only its own files | An edit hook blocks paths owned by another chat (`coord/owners.json`) |
| The coordinator doesn't build | The same hook |
| One user at a time for shared tools | `./crew slot take/release`, with a per-lane lock, auto-timeout and queue |
| Messages reach every chat | A hook adds new messages to every prompt, so nobody has to check |
| Your sign-off comes last | Human test only after an AI pass and a critic pass, and refused from inside Claude Code |
| Standing approvals live in one place | `coord/approvals.json`, which only you can edit |
| The critic earns its place | `./crew board` shows how many of its findings were accepted |

## What's in the box

| Path | What it is |
|---|---|
| `crew` | Launcher and dashboard: `./crew start <chat>`, `./crew board`, `./crew -h` |
| `CLAUDE.md` | Team rules every chat loads (added to yours if you already have one) |
| `.claude/settings.json` | Hooks and permissions (merged into yours if you already have one) |
| `.claude/agents/lane-*.md` | Lanes: coder, editor, data, researcher, tester, critic |
| `.claude/commands/` | `/scope`, `/brief`, `/ship` |
| `coord/owners.json` | Who owns what. Edit it to match your project. |
| `coord/approvals.json` | Standing approvals (yours to edit) |
| `coord/agentctl.py` | The engine: plain Python, no installs |

## Use a cheaper model

- **Chats:** start them with `CREW_MODEL=sonnet ./crew start core`.
- **Lanes:** change `model: opus` to `model: sonnet` in `.claude/agents/lane-*.md`. A good first saving is the tester, data and researcher lanes, while the critic stays on Opus.

## Advanced: one folder per chat (git worktrees)

By default every chat works in one folder, and the edit hook keeps them out of each other's files. To give each chat its own branch:
```bash
git worktree add ../my-app-pricing -b pricing
./crew join pricing --dir ../my-app-pricing    # then run `claude` in that folder
```

## Troubleshooting

- **Rules or messages don't show up:** the folder isn't trusted yet. Run `claude` in it once and choose Yes.
- **`./crew up` waits forever:** accept the trust prompt in the first window. If you missed it, close that window and run `./crew up` again.
- **"AGENT_ID is not set":** start chats with `./crew start <chat>`, not plain `claude`.
- **Anything else:** run `./crew doctor`.

## Tests
```bash
python3 -m unittest discover tests
```
`./crew up` drives Terminal through AppleScript, so it's only exercised on a real Mac.

More detail: [docs/how-it-works.md](docs/how-it-works.md) · MIT licence
