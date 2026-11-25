---
description: Write a lane brief and launch the lane
argument-hint: <lane-type> <goal>
---
Work: $ARGUMENTS

1. Check scope first: `./crew q list --owner <you> --open`. If a `before` question covers this work, don't launch. Say which question blocks it.
2. Write the brief in this shape, in under 15 lines:
   - GOAL: one sentence
   - SCOPE: exact files, tables, columns or screens, plus what is out of scope
   - SLOT: shared resource name, lane name and TTL in minutes, or "none"
   - RULES: only the ones that matter here (owned paths, human-only actions)
   - STOP WHEN: the done condition, and when to stop early and report
   - REPORT: STATUS / CHANGED / EVIDENCE / QUESTIONS
3. Launch the matching subagent (lane-editor, lane-tester, lane-data, lane-coder, lane-researcher) with the brief. If you have several independent briefs, launch them all in one message so they run in parallel.
