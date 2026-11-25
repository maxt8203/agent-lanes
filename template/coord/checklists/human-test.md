# Human test checklist: <item>

Run this only after the AI test and the critic have both passed. Record the result from your own Terminal tab:
`./crew test <item> human pass|fail "<note>"`

- [ ] Open the app as a normal user (not in the editor)
- [ ] Do the main task end to end with realistic data
- [ ] The saved record (sheet or database) matches what you entered
- [ ] One wrong input (blank, too big, wrong type) is rejected with a clear message
- [ ] Nothing outside the brief changed (spot-check one neighbouring screen)
- [ ] Looks right on phone and desktop

Notes:
