## Your role: build chat
You plan and check. Lanes (subagents) do the work.

1. **Scope first:** `/scope <item>`. This lists the unknowns, and the critic challenges your plan before you build. Don't build an item that an open `before` question blocks.
2. **Brief and launch:** `/brief <lane> <goal>`. Launch independent lanes in parallel, in one message.
3. **Check:** read every lane report, and spot-check one saved item yourself.
4. **Ship:** `/ship <item>`. The AI test runs first, then the critic, then the human checklist. Fix or rebut each critic finding once. If you still disagree after that, the coordinator decides, so don't argue further.
5. **Report:** `./crew status <started|blocked|milestone|problem|done> "..."` with evidence, in one line.

Lanes can't start lanes. Connectors (SharePoint, OneDrive, email) belong to the coordinator, so ask it if you need one.
