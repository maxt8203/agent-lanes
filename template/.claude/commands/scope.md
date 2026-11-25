---
description: List what's still unknown for an item, then have the critic challenge the plan
argument-hint: <item>
---
For $ARGUMENTS:
1. Show open questions: `./crew q list --owner <you> --open`.
2. Read the relevant code, data or screens. List every decision the client or human must make before building: data rules, edge cases, who sees what, wording, prices. Then write a short build plan.
3. Launch **lane-critic** (scope gate) with the item name, your plan and your list. Tell it to record `./crew review <item> scope ...`.
4. For each critic finding, either log it as a question (`./crew q add <you> "<question>" --phase before`, or `--kind decision` for "we assumed X, please confirm"), change the plan, or rebut it with evidence. Record the outcome: `./crew findings <accepted> <rejected>`.
5. Say which items can be built now and which are blocked.
