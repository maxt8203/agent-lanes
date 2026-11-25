---
description: Take an item through the critic and get it ready for human review
argument-hint: <item>
---
For item $ARGUMENTS:
1. Run `./crew board`. The AI test must show `pass`. If it doesn't, run lane-tester first.
2. Launch **lane-critic** (ship gate) with the item name, the brief, the changed files and the tester's evidence.
3. For each finding, fix it (through the right lane) or rebut it with evidence. Record the outcome: `./crew findings <accepted> <rejected>`.
4. If you fixed anything, rerun lane-tester, then lane-critic **once** more. That is the only extra round. If the critic still says FIX or BLOCK, agentctl alerts the coordinator to decide. Stop and wait.
5. When the critic passes:
   - Check the change fits a PR of about 500–1,000 lines. If it's bigger, split it.
   - Write a review guide of 10 lines or fewer: what changed, why, where to look first, risks, how to test.
   - Fill in `coord/checklists/human-test.md` for this item and show it.
   - Run `./crew status milestone "$ARGUMENTS ready for human test"`.
