#!/usr/bin/env python3
"""agentctl: coordination for a multi-chat Claude Code setup.

Layers: human > coordinator chat > build chats > lanes (subagents).
Stdlib only, Python 3.8+. State is plain files under AGENTCTL_HOME
(default: the folder this file is in). Run with -h for commands.
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import json
import os
import shutil
import sys
import time
from pathlib import Path

VERSION = "2.0.0"
STATUSES = ("started", "blocked", "milestone", "problem", "done")
BUSY = 3  # exit code when a slot is held by someone else
PROTECTED = ("owners.json", "approvals.json")  # human-only config files

for _s in (sys.stdout, sys.stderr):  # emoji-safe on Windows consoles
    with contextlib.suppress(Exception):
        _s.reconfigure(encoding="utf-8")


# ---------- file helpers ----------
def read_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, p)


def append_line(p: Path, rec: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def read_lines(p: Path) -> list:
    try:
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
    except FileNotFoundError:
        return []


# ---------- identity ----------
def _local_env() -> dict:
    """Inside Claude Code, fall back to .claude/settings.local.json if env wasn't passed."""
    root = os.environ.get("CLAUDE_PROJECT_DIR")
    if not root:
        return {}
    return read_json(Path(root) / ".claude" / "settings.local.json", {}).get("env", {})


_ENV = _local_env()
HOME = Path(os.environ.get("AGENTCTL_HOME") or _ENV.get("AGENTCTL_HOME") or Path(__file__).resolve().parent)
STATE = HOME / ".state"
ME = (os.environ.get("AGENT_ID") or _ENV.get("AGENT_ID") or "").strip()
IN_CLAUDE = bool(os.environ.get("CLAUDECODE") or os.environ.get("CLAUDE_PROJECT_DIR"))


def die(msg: str, code: int = 1):
    print(f"agentctl: {msg}", file=sys.stderr)
    sys.exit(code)


def stamp(t: float | None = None) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(time.time() if t is None else t))


@contextlib.contextmanager
def locked(timeout: float = 10.0):
    """Cross-platform mutex for state writes. Stale locks clear after 30s."""
    STATE.mkdir(parents=True, exist_ok=True)
    lock = STATE / ".lock"
    deadline = time.time() + timeout
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            with contextlib.suppress(FileNotFoundError):
                if time.time() - lock.stat().st_mtime > 30:
                    lock.unlink()
                    continue
            if time.time() > deadline:
                die("state is busy, try again")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()


def config() -> dict:
    c = read_json(HOME / "owners.json", None)
    if c is None:
        die(f"no owners.json in {HOME}")
    c.setdefault("coordinator", "coordinator")
    c.setdefault("human", "human")
    c.setdefault("chats", {})
    return c


def agents(c: dict) -> list:
    return [c["coordinator"], *c["chats"]]


def require_me(c: dict) -> str:
    if not ME:
        die("AGENT_ID is not set. Start chats with: ./crew start <chat>")
    if ME not in agents(c):
        die(f"unknown AGENT_ID '{ME}'. Known: {', '.join(agents(c))}")
    return ME


def sender(c: dict) -> str:
    """Chats act as their AGENT_ID; a terminal with no AGENT_ID is the human."""
    return ME or c["human"]


def log(who: str, kind: str, note: str) -> None:
    append_line(STATE / "events.jsonl", {"t": time.time(), "who": who, "kind": kind, "note": note})


def deliver(frm: str, to: str, msg: str, c: dict) -> None:
    everyone = agents(c) + [c["human"]]
    for t in ([a for a in everyone if a != frm] if to == "all" else [to]):
        append_line(STATE / "inbox" / f"{t}.jsonl", {"t": time.time(), "from": frm, "msg": msg})


def take_unread(who: str, advance: bool = True) -> list:
    box, cur = STATE / "inbox" / f"{who}.jsonl", STATE / "inbox" / f"{who}.cursor"
    msgs = read_lines(box)
    seen = int(read_json(cur, 0))
    if advance and len(msgs) > seen:
        write_json(cur, len(msgs))
    return msgs[seen:]


def fmt_msg(m: dict) -> str:
    return f"[{stamp(m['t'])}] {m['from']}: {m['msg']}"


def owner_of(rel: str, c: dict):
    for chat, info in c["chats"].items():
        if any(fnmatch.fnmatch(rel, pat) for pat in info.get("paths", [])):
            return chat
    return None


# ---------- commands ----------
def cmd_join(a):
    c = config()
    if a.id not in agents(c):
        die(f"'{a.id}' is not in owners.json. Known: {', '.join(agents(c))}")
    folder = Path(a.dir).resolve()
    target = folder / ".claude" / "settings.local.json"
    s = read_json(target, {})
    s.setdefault("env", {}).update({"AGENT_ID": a.id, "AGENTCTL_HOME": str(HOME)})
    write_json(target, s)
    print(f"✅ {folder} now runs as '{a.id}'. Start (or restart) Claude Code in that folder.")


def cmd_whoami(a):
    c = config()
    role = "human" if not ME else ("coordinator" if ME == c["coordinator"] else "build chat")
    print(f"{sender(c)} ({role}) · state: {HOME}")


def cmd_status(a):
    c = config()
    who, note = require_me(c), " ".join(a.note)
    with locked():
        log(who, a.state, note)
        if who != c["coordinator"]:
            flag = "⚠️ " if a.state in ("blocked", "problem") else ""
            deliver(who, c["coordinator"], f"{flag}[{a.state}] {note}", c)
    print(f"{who}: {a.state} · {note}")


def cmd_send(a):
    c = config()
    valid = agents(c) + [c["human"], "all"]
    if a.to not in valid:
        die(f"unknown recipient '{a.to}'. Use one of: {', '.join(valid)}")
    with locked():
        deliver(sender(c), a.to, " ".join(a.msg), c)
    print(f"sent to {a.to}")


def cmd_inbox(a):
    c = config()
    with locked():
        msgs = take_unread(sender(c), advance=not a.peek)
    print("\n".join(fmt_msg(m) for m in msgs) if msgs else "No new messages.")


def load_slots():
    slots, expired = read_json(STATE / "slots.json", {}), []
    for name, v in slots.items():
        if v.get("holder") and v["until"] < time.time():
            expired.append((name, v["holder"]))
            v["holder"] = None
    return slots, expired


def cmd_slot(a):
    c = config()
    if a.action == "list":
        slots, _ = load_slots()
        for name, v in slots.items():
            held = f"{v['holder']} until {stamp(v['until'])}" if v["holder"] else "free"
            print(f"{name:<20} {held}" + (f" · queue: {', '.join(v['queue'])}" if v.get("queue") else ""))
        if not slots:
            print("No slots in use.")
        return
    if not a.name:
        die("slot name required, e.g. slot take app-editor --lane editor-1")
    who = require_me(c)
    me = f"{who}/{a.lane}"
    with locked():
        slots, expired = load_slots()
        for name, h in expired:
            log("agentctl", "slot", f"{name} expired from {h}")
        v = slots.setdefault(a.name, {"holder": None, "until": 0, "queue": []})
        if a.action == "take":
            if v["holder"] in (None, me):
                v["holder"], v["until"] = me, time.time() + a.ttl * 60
                if me in v["queue"]:
                    v["queue"].remove(me)
                write_json(STATE / "slots.json", slots)
                log(who, "slot", f"{me} took {a.name}")
                if who != c["coordinator"]:
                    deliver(who, c["coordinator"], f"[slot] {me} took {a.name} for {a.ttl} min", c)
                print(f"✅ {me} holds '{a.name}' until {stamp(v['until'])}. Release it the moment you're done.")
                return
            if me not in v["queue"]:
                v["queue"].append(me)
            write_json(STATE / "slots.json", slots)
            print(f"⛔ '{a.name}' is held by {v['holder']} until {stamp(v['until'])}. "
                  f"You're #{v['queue'].index(me) + 1} in the queue; you'll get an inbox message when it's free.")
            sys.exit(BUSY)
        # release
        forced = a.force and who == c["coordinator"]
        if v["holder"] != me and not forced:
            die(f"'{a.name}' is held by {v['holder'] or 'nobody'}, not {me}")
        prev, v["holder"], v["until"] = v["holder"], None, 0
        nxt = v["queue"][0] if v["queue"] else None
        write_json(STATE / "slots.json", slots)
        log(who, "slot", f"{a.name} released" + (f" (forced from {prev})" if forced and prev != me else ""))
        if who != c["coordinator"]:
            deliver(who, c["coordinator"], f"[slot] {me} freed {a.name}", c)
        if nxt:
            chat, lane = nxt.split("/", 1)
            deliver("agentctl", chat, f"'{a.name}' is free for lane {lane}: slot take {a.name} --lane {lane}", c)
        print(f"🔓 released '{a.name}'" + (f" · next: {nxt}" if nxt else ""))


def load_q() -> dict:
    return read_json(HOME / "questions.json", {"questions": []})


def find_q(d: dict, qid: str) -> dict:
    for q in d["questions"]:
        if q["id"].lower() == qid.lower():
            return q
    die(f"no question {qid}")


def cmd_q_add(a):
    c = config()
    if a.owner not in c["chats"]:
        die(f"owner must be a build chat: {', '.join(c['chats'])}")
    who, text = sender(c), " ".join(a.text)
    with locked():
        d = load_q()
        pre = c["chats"][a.owner].get("prefix") or a.owner[:1].upper()
        nums = [int(q["id"][len(pre):]) for q in d["questions"]
                if q["id"].startswith(pre) and q["id"][len(pre):].isdigit()]
        q = {"id": f"{pre}{max(nums, default=0) + 1}", "owner": a.owner, "phase": a.phase, "kind": a.kind,
             "text": text, "status": "open", "answer": "", "asked_by": who, "asked": stamp()}
        d["questions"].append(q)
        write_json(HOME / "questions.json", d)
        log(who, "question", f"{q['id']} added")
        if who != c["coordinator"]:
            deliver(who, c["coordinator"], f"New {q['kind']} {q['id']} for {a.owner} ({a.phase} building): {text}", c)
    print(f"{q['id']} added")


def cmd_q_answer(a):
    c = config()
    who, text = sender(c), " ".join(a.text)
    with locked():
        d = load_q()
        q = find_q(d, a.id)
        q.update(answer=text, status="partly" if a.partial else "answered", answered=stamp())
        write_json(HOME / "questions.json", d)
        log(who, "answer", q["id"])
        if q["owner"] != who:
            deliver(who, q["owner"], f"Answer to {q['id']} ({q['text']}): {text}" + (" [partial]" if a.partial else ""), c)
    print(f"{q['id']} → {q['status']} (sent to {q['owner']})")


def cmd_q_list(a):
    qs = [q for q in load_q()["questions"]
          if (not a.owner or q["owner"] == a.owner) and (not a.open or q["status"] != "answered")]
    for q in qs:
        print(f"{q['id']:<6} {q['status']:<9} {q['phase']:<7} {q['owner']:<12} {q['text']}")
        if q["answer"]:
            print(f"{'':6} ↳ {q['answer']}")
    if not qs:
        print("No matching questions.")


def section_tag(qs: list) -> str:
    st = {q["status"] for q in qs}
    return "Answered" if st == {"answered"} else "Open" if st == {"open"} else "Partly answered"


def render_qa(d: dict, c: dict) -> str:
    out = ["# Shared Q&A", "",
           f"_Updated {stamp()}. Type your answer under any question; the coordinator picks it up._", ""]
    for owner, info in c["chats"].items():
        qs = [q for q in d["questions"] if q["owner"] == owner]
        if not qs:
            continue
        out += [f"## {info.get('area', owner)} [{section_tag(qs)}]", ""]
        for phase, title in (("before", "Before building"), ("after", "After building")):
            pq = [q for q in qs if q["phase"] == phase]
            if pq:
                out += [f"### {title} [{section_tag(pq)}]", ""]
                for q in pq:
                    label = "Decision to check" if q["kind"] == "decision" else "Question"
                    out += [f"**{q['id']}** ({label}): {q['text']}", "", f"> Answer: {q['answer']}", ""]
    return "\n".join(out)


def cmd_q_export(a):
    c = config()
    out = Path(a.out) if a.out else HOME / "QA.md"
    out.write_text(render_qa(load_q(), c), encoding="utf-8")
    hint = " (Word: pandoc QA.md -o QA.docx)" if shutil.which("pandoc") else ""
    print(f"wrote {out}{hint}")


def item_rec(t: dict, item: str) -> dict:
    return t.setdefault(item, {"owner": None, "ai": None, "critic": None, "human": None})


def is_tested(it: dict) -> bool:
    return it.get("ai") == "pass" and it.get("critic") == "pass" and it.get("human") == "pass"


def item_line(item: str, it: dict) -> str:
    return (f"{item}: AI {it.get('ai') or '-'} · critic {it.get('critic') or '-'} · human {it.get('human') or '-'}"
            + (" · ✅ TESTED" if is_tested(it) else ""))


def cmd_test(a):
    """Gate order: AI test pass -> critic (ship) pass -> human pass."""
    c = config()
    note = " ".join(a.note)
    if a.kind == "human":
        if ME or IN_CLAUDE:
            die(f"human results are recorded by {c['human']} from their own terminal, not by a chat.")
        who = c["human"]
    else:
        who = require_me(c)
    with locked():
        t = read_json(STATE / "tests.json", {})
        it = item_rec(t, a.item)
        if a.kind == "ai":
            # a new AI run means the work changed: earlier critic and human verdicts no longer apply
            it.update(owner=it["owner"] or who, ai=a.result, ai_note=note, ai_at=stamp(), critic=None, human=None)
        else:
            if it["ai"] != "pass":
                die(f"{a.item}: the AI test hasn't passed yet")
            if it.get("critic") != "pass":
                die(f"{a.item}: the critic hasn't passed it yet (ship review)")
            it.update(human=a.result, human_note=note, human_at=stamp())
            if it["owner"]:
                deliver(who, it["owner"], f"Human test {a.result.upper()} for {a.item}. {note}".strip(), c)
        write_json(STATE / "tests.json", t)
        log(who, "test", f"{a.item} {a.kind} {a.result}")
    print(item_line(a.item, it))


def cmd_review(a):
    """Record a critic verdict. Ship gate sits between the AI test and the human test."""
    c = config()
    who, note = require_me(c), a.override or " ".join(a.note)
    if a.override and who != c["coordinator"]:
        die("only the coordinator can override a critic verdict")
    if a.override and a.verdict != "pass":
        die("--override is for settling a dispute with a pass")
    key, rounds = ("critic", "critic_rounds") if a.gate == "ship" else ("scope_review", "scope_rounds")
    with locked():
        t = read_json(STATE / "tests.json", {})
        it = item_rec(t, a.item)
        if a.gate == "ship" and it["ai"] != "pass":
            die(f"{a.item}: ship review comes after the AI test passes")
        if not a.override:
            it[rounds] = it.get(rounds, 0) + 1
            stats = read_json(STATE / "critic.json", {"findings": 0, "accepted": 0, "rejected": 0, "reviews": 0})
            stats["findings"] += a.findings
            stats["reviews"] += 1
            write_json(STATE / "critic.json", stats)
        it.update({key: a.verdict, f"{key}_note": note, f"{key}_at": stamp(),
                   f"{key}_by": who + (" (override)" if a.override else "")})
        if a.gate == "ship":
            it["human"] = None
        it["owner"] = it["owner"] or (who if who != c["coordinator"] else None)
        write_json(STATE / "tests.json", t)
        log(who, "review", f"{a.item} {a.gate} {a.verdict}" + (" (override)" if a.override else ""))
        if a.gate == "ship" and a.verdict == "pass":
            deliver(who, c["human"], f"{a.item} passed the AI test and the critic. Run the human checklist, then: "
                                     f"./crew test {a.item} human pass|fail", c)
        elif a.verdict != "pass" and it[rounds] >= 2:
            deliver(who, c["coordinator"],
                    f"⚠️ Dispute on {a.item} ({a.gate} gate): the critic still says {a.verdict.upper()} after one fix round. "
                    f"Decide: ./crew review {a.item} {a.gate} pass --override \"<reason>\", or tell "
                    f"{it['owner'] or 'the owner'} exactly what to change. Critic: {note}", c)
    print(f"{a.item} {a.gate} review: {a.verdict} (round {it.get(rounds, 0)})"
          + ("" if a.gate == "scope" else f"\n{item_line(a.item, it)}"))


def cmd_findings(a):
    """Builder records how many critic findings it accepted vs rejected (to measure if the critic earns its place)."""
    c = config()
    require_me(c)
    with locked():
        stats = read_json(STATE / "critic.json", {"findings": 0, "accepted": 0, "rejected": 0, "reviews": 0})
        stats["accepted"] += a.accepted
        stats["rejected"] += a.rejected
        write_json(STATE / "critic.json", stats)
    print(critic_summary(stats))


def critic_summary(s: dict) -> str:
    judged = s["accepted"] + s["rejected"]
    rate = f"{100 * s['accepted'] // judged}% accepted" if judged else "none judged yet"
    tip = "  ← mostly rejected: tune .claude/agents/lane-critic.md" if judged >= 10 and s["rejected"] > s["accepted"] else ""
    return f"{s['reviews']} reviews · {s['findings']} findings · {rate}{tip}"


def cmd_chats(a):
    print("\n".join(agents(config())))


def active_approvals() -> list:
    today = time.strftime("%Y-%m-%d")
    return [x for x in read_json(HOME / "approvals.json", {}).get("standing", [])
            if not x.get("expires") or x["expires"] >= today]


def fmt_approval(x: dict) -> str:
    return f"{x['id']}: {x.get('who', 'any chat')} may {x['action']}, only if {x['condition']} (expires {x.get('expires') or 'never'})"


def cmd_approvals(a):
    ap = active_approvals()
    print("\n".join(map(fmt_approval, ap)) if ap else "No standing approvals: every human-only action needs the human each time.")


def cmd_board(a):
    c = config()
    last = {}
    for e in read_lines(STATE / "events.jsonl"):
        if e["kind"] in STATUSES:
            last[e["who"]] = e
    print("CHATS")
    for ag in agents(c):
        e = last.get(ag)
        print(f"  {ag:<14} " + (f"{e['kind']:<10} {stamp(e['t'])}  {e['note']}" if e else "-"))
    print("SLOTS")
    slots, _ = load_slots()
    for name, v in slots.items():
        print(f"  {name:<14} " + (f"{v['holder']} until {stamp(v['until'])}" if v["holder"] else "free")
              + (f" · queue {len(v['queue'])}" if v.get("queue") else ""))
    if not slots:
        print("  none")
    print("OPEN QUESTIONS (before / after building)")
    qs = load_q()["questions"]
    for ag in c["chats"]:
        mine = [q for q in qs if q["owner"] == ag and q["status"] != "answered"]
        if mine:
            b = sum(q["phase"] == "before" for q in mine)
            print(f"  {ag:<14} {b} / {len(mine) - b}" + ("  ← blocks building" if b else ""))
    if not any(q["status"] != "answered" for q in qs):
        print("  none")
    print("ITEMS (AI test → critic → human)")
    tests = read_json(STATE / "tests.json", {})
    for item, it in tests.items():
        print(f"  {'✅' if is_tested(it) else '··'} {item:<20} AI {it.get('ai') or '-':<5} "
              f"critic {it.get('critic') or '-':<6} human {it.get('human') or '-':<5} ({it.get('owner') or '?'})")
    if not tests:
        print("  none")
    stats = read_json(STATE / "critic.json", None)
    if stats:
        print("CRITIC\n  " + critic_summary(stats))
    n = len(take_unread(sender(c), advance=False))
    if n:
        print(f"\n📬 {n} unread for {sender(c)}: agentctl inbox")


def cmd_doctor(a):
    ok = True

    def check(cond, good, bad):
        nonlocal ok
        print(("✅ " + good) if cond else ("❌ " + bad))
        ok = ok and bool(cond)

    check(sys.version_info >= (3, 8), f"Python {sys.version.split()[0]}", "Python 3.8+ needed")
    raw = read_json(HOME / "owners.json", None)
    check(raw is not None, f"owners.json found in {HOME}", f"owners.json missing in {HOME}")
    if raw is None:
        sys.exit(1)
    c = config()
    if ME:
        check(ME in agents(c), f"AGENT_ID={ME}", f"AGENT_ID '{ME}' is not in owners.json")
    else:
        print(f"ℹ️  No AGENT_ID: this terminal acts as {c['human']} (human)")
    seen = {}
    for chat, info in c["chats"].items():
        for pat in info.get("paths", []):
            check(pat not in seen, f"{pat} → {chat}", f"{pat} is owned by both {seen.get(pat)} and {chat}")
            seen[pat] = chat
    try:
        with locked(timeout=2):
            pass
        check(True, "state folder writable", "")
    except SystemExit:
        check(False, "", f"can't write to {STATE}")
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or a.dir).resolve()
    hooks = read_json(root / ".claude" / "settings.json", {}).get("hooks", {})
    for h in ("SessionStart", "UserPromptSubmit", "PreToolUse"):
        check(h in hooks, f"{h} hook set in {root / '.claude/settings.json'}", f"{h} hook missing (rerun install.py)")
    check(shutil.which("git"), "git available", "git not found (needed for worktrees and PRs)")
    sys.exit(0 if ok else 1)


# ---------- Claude Code hooks ----------
def hook_session():
    c = config()
    if not ME:
        print("[agentctl] No AGENT_ID for this folder, so this session is in human mode. "
              "To start a coordinator or build chat, run in Terminal: ./crew start <chat>")
        return
    role = "coordinator" if ME == c["coordinator"] else "build-chat"
    print(f"[agentctl] You are '{ME}' ({role.replace('-', ' ')}). Human in charge: {c['human']}.")
    info = c["chats"].get(ME, {})
    if info:
        print("Files you own (edit hook enforced): " + (", ".join(info.get("paths", [])) or "none yet"))
        if info.get("also_owns"):
            print("Also yours (not hook enforced, honour it): " + ", ".join(info["also_owns"]))
    rf = HOME / "roles" / f"{role}.md"
    if rf.exists():
        print(rf.read_text(encoding="utf-8"))
    ap = active_approvals()
    print("Standing approvals: " + ("; ".join(map(fmt_approval, ap)) if ap
                                    else f"none. Every human-only action needs {c['human']}."))
    n = len(take_unread(ME, advance=False))
    if n:
        print(f"You have {n} unread message(s); they arrive with the next prompt.")


def hook_inbox():
    if not ME:
        return
    with locked():
        msgs = take_unread(ME)
    if msgs:
        print("[agentctl inbox] New messages for you:\n" + "\n".join(fmt_msg(m) for m in msgs))


def hook_owner():
    data = json.load(sys.stdin)
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp or not ME:
        return
    c = config()
    root = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()).resolve()
    p = Path(fp) if Path(fp).is_absolute() else root / fp
    p = p.resolve()
    if p.name in PROTECTED and (p.parent.name == "coord" or p.parent == HOME.resolve()):
        print(f"Blocked: {p.name} belongs to {c['human']}. Ask them: ./crew send {c['human']} \"<change needed>\"",
              file=sys.stderr)
        sys.exit(2)
    try:
        rel = p.relative_to(root).as_posix()
    except ValueError:
        return  # outside the project: not ours to police
    owner = owner_of(rel, c)
    if owner and owner != ME:
        why = "The coordinator doesn't build." if ME == c["coordinator"] else "Stay in your lane."
        print(f"Blocked: {rel} is owned by '{owner}'. {why} Message the owner instead: "
              f"./crew send {owner} \"<what you need>\"", file=sys.stderr)
        sys.exit(2)


def cmd_hook(a):
    try:
        {"session": hook_session, "inbox": hook_inbox, "owner": hook_owner}[a.which]()
    except SystemExit:
        raise
    except Exception as e:  # a hook bug must never break the session
        print(f"agentctl hook {a.which} error: {e}", file=sys.stderr)


# ---------- CLI ----------
def main(argv=None):
    p = argparse.ArgumentParser(prog="agentctl", description="Coordination for a multi-chat Claude Code setup.")
    p.add_argument("--version", action="version", version=VERSION)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("join", help="make a folder run as a chat (writes .claude/settings.local.json)")
    s.add_argument("id")
    s.add_argument("--dir", default=".")
    s.set_defaults(fn=cmd_join)

    sub.add_parser("whoami", help="who this terminal/chat is").set_defaults(fn=cmd_whoami)

    s = sub.add_parser("status", help="report: " + ", ".join(STATUSES))
    s.add_argument("state", choices=STATUSES)
    s.add_argument("note", nargs="+")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("send", help="message a chat, the human, or all")
    s.add_argument("to")
    s.add_argument("msg", nargs="+")
    s.set_defaults(fn=cmd_send)

    s = sub.add_parser("inbox", help="read new messages")
    s.add_argument("--peek", action="store_true", help="don't mark as read")
    s.set_defaults(fn=cmd_inbox)

    s = sub.add_parser("slot", help="one-user-at-a-time resources, e.g. the app editor")
    s.add_argument("action", choices=("take", "release", "list"))
    s.add_argument("name", nargs="?")
    s.add_argument("--lane", default="main", help="lane name, so two lanes of one chat can't both hold it")
    s.add_argument("--ttl", type=int, default=30, help="minutes before it auto-frees (default 30)")
    s.add_argument("--force", action="store_true", help="coordinator only: free a stuck slot")
    s.set_defaults(fn=cmd_slot)

    q = sub.add_parser("q", help="shared Q&A registry")
    qs = q.add_subparsers(dest="qcmd", required=True)
    x = qs.add_parser("add", help="add a question for a build chat")
    x.add_argument("owner")
    x.add_argument("text", nargs="+")
    x.add_argument("--phase", choices=("before", "after"), default="before")
    x.add_argument("--kind", choices=("question", "decision"), default="question")
    x.set_defaults(fn=cmd_q_add)
    x = qs.add_parser("answer", help="record an answer (auto-sent to the owning chat)")
    x.add_argument("id")
    x.add_argument("text", nargs="+")
    x.add_argument("--partial", action="store_true")
    x.set_defaults(fn=cmd_q_answer)
    x = qs.add_parser("list")
    x.add_argument("--owner")
    x.add_argument("--open", action="store_true", help="hide fully answered")
    x.set_defaults(fn=cmd_q_list)
    x = qs.add_parser("export", help="write the shared Q&A doc (markdown)")
    x.add_argument("out", nargs="?")
    x.set_defaults(fn=cmd_q_export)

    s = sub.add_parser("test", help="record a test result (human only after AI + critic pass)")
    s.add_argument("item")
    s.add_argument("kind", choices=("ai", "human"))
    s.add_argument("result", choices=("pass", "fail"))
    s.add_argument("note", nargs="*")
    s.set_defaults(fn=cmd_test)

    s = sub.add_parser("review", help="record a critic verdict (scope or ship gate)")
    s.add_argument("item")
    s.add_argument("gate", choices=("scope", "ship"))
    s.add_argument("verdict", choices=("pass", "fix", "block"))
    s.add_argument("note", nargs="*")
    s.add_argument("--findings", type=int, default=0, help="how many findings the critic reported")
    s.add_argument("--override", metavar="REASON", help="coordinator only: settle a dispute with a pass")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("findings", help="builder: how many critic findings you accepted / rejected")
    s.add_argument("accepted", type=int)
    s.add_argument("rejected", type=int)
    s.set_defaults(fn=cmd_findings)

    sub.add_parser("chats", help="list chat ids").set_defaults(fn=cmd_chats)

    sub.add_parser("board", help="everything at a glance").set_defaults(fn=cmd_board)
    sub.add_parser("approvals", help="standing approvals in force").set_defaults(fn=cmd_approvals)
    s = sub.add_parser("doctor", help="preflight checks")
    s.add_argument("--dir", default=".", help="project folder to check")
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("hook", help="called by Claude Code hooks")
    s.add_argument("which", choices=("session", "inbox", "owner"))
    s.set_defaults(fn=cmd_hook)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
