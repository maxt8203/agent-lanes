#!/usr/bin/env python3
"""agent-lanes installer (macOS).

    python3 install.py ~/my-app                      # asks your name and your build chats
    python3 install.py ~/my-app --name Sam --chats core,pricing
    python3 install.py ~/agent-lanes-demo --demo     # try it: no questions

Safe on existing projects: CLAUDE.md and .claude/settings.json are merged, not
overwritten, and other existing files are left alone unless you pass --force.
"""
import argparse
import getpass
import json
import os
import platform
import re
import shutil
import stat
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "template"
MARK = "<!-- agent-lanes -->"
IGNORE = ["coord/.state/", "coord/QA.md", ".claude/settings.local.json", ".env", ".env.*", "!.env.example"]
RESERVED = {"coordinator", "all", "human"}


def slug(s: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "", s.strip().lower().replace(" ", "-"))).strip("-")


def ask(prompt: str, default: str) -> str:
    if not sys.stdin.isatty():
        return default
    v = input(f"{prompt} [{default}]: ").strip()
    return v or default


def make_owners(human: str, chats: list) -> dict:
    out, used = {}, set()
    for ch in chats:
        n, pre = 1, ch[:1].upper()
        while pre in used and n < len(ch):
            n += 1
            pre = ch[:n].upper().replace("-", "")
        used.add(pre)
        out[ch] = {"area": ch.replace("-", " ").title(), "prefix": pre,
                   "paths": [f"src/{ch}/*", f"tests/{ch}/*"], "also_owns": []}
    return {
        "human": human,
        "coordinator": "coordinator",
        "chats": out,
        "shared_resources": {
            "app-editor": "Only one lane across all chats may use the app editor at a time (it saves the whole app)."
        },
    }


def merge_settings(old: dict, new: dict) -> dict:
    perms = old.setdefault("permissions", {})
    for k, vals in new.get("permissions", {}).items():
        lst = perms.setdefault(k, [])
        lst += [v for v in vals if v not in lst]
    hooks = old.setdefault("hooks", {})
    for event, entries in new.get("hooks", {}).items():
        cur = hooks.setdefault(event, [])
        if "agentctl.py" not in json.dumps(cur):
            cur += entries
    return old


DEMO_CODE = '''def greet(name="world"):
    return f"Hello, {name}!"


if __name__ == "__main__":
    print(greet())
'''

DEMO_TEST = '''import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src" / "core"))
from greet import greet  # noqa: E402


class GreetTest(unittest.TestCase):
    def test_default(self):
        self.assertEqual(greet(), "Hello, world!")


if __name__ == "__main__":
    unittest.main()
'''

DEMO_PROMPT = (
    "This is the agent-lanes demo, so show me how the team works. Item 'greet-name': add a --name option so "
    "`python3 src/core/greet.py --name Sam` prints 'Hello, Sam!' (and the default stays 'Hello, world!'). "
    "Work through it the team way: follow .claude/commands/scope.md, then .claude/commands/brief.md using lane-coder, "
    "then .claude/commands/ship.md. If a question comes up, log it with --kind decision, pick a sensible default and "
    "carry on (this is a demo). Say what each step is doing in one line. Stop when it's ready for my human test and "
    "give me the exact commands to try it and to sign it off."
)


def seed_demo(dst: Path) -> None:
    """A tiny real job so the first run shows the whole flow: scope -> lanes -> AI test -> critic -> you."""
    for rel, text in (("src/core/greet.py", DEMO_CODE), ("tests/core/test_greet.py", DEMO_TEST),
                      ("coord/.state/first-prompt-core.txt", DEMO_PROMPT)):
        p = dst / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--name", help="your name (the human in charge)")
    ap.add_argument("--chats", help="comma-separated build chats, e.g. core,pricing,reports")
    ap.add_argument("--demo", action="store_true", help="no questions: you + coordinator + core, pricing")
    ap.add_argument("--force", action="store_true", help="overwrite existing kit files (not your CLAUDE.md/settings)")
    ap.add_argument("--python", default="python3", help="Python command for hooks (default: python3)")
    a = ap.parse_args()

    if platform.system() == "Windows":
        sys.exit("agent-lanes supports macOS for now. Windows isn't supported yet.")
    if sys.version_info < (3, 8):
        sys.exit("Python 3.8+ needed.")

    default_name = slug(getpass.getuser()) or "me"
    human = slug(a.name or (default_name if a.demo else ask("Your name (you approve the risky stuff)", default_name)))
    raw = a.chats or ("core,pricing" if a.demo else ask("Build chats, one per area of your app (comma-separated)", "core,pricing"))
    chats = [c for c in dict.fromkeys(slug(x) for x in raw.split(",")) if c]
    bad = [c for c in chats if c in RESERVED | {human}]
    if not human or not chats or bad:
        sys.exit(f"Need a name and at least one build chat; these names are reserved: {', '.join(sorted(RESERVED | set(bad)))}")

    dst = Path(a.project).expanduser().resolve()
    dst.mkdir(parents=True, exist_ok=True)
    done, skipped = [], []

    def render(f: Path) -> str:
        return f.read_text(encoding="utf-8").replace("{{PY}}", a.python).replace("{{HUMAN}}", human)

    for f in sorted(SRC.rglob("*")):
        if f.is_dir() or "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        rel = f.relative_to(SRC)
        out = dst / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == ".claude/settings.json" and out.exists():
            merged = merge_settings(json.loads(out.read_text(encoding="utf-8")), json.loads(render(f)))
            out.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
            done.append(f"{rel} (merged)")
        elif rel.as_posix() == "CLAUDE.md" and out.exists():
            cur = out.read_text(encoding="utf-8")
            if MARK not in cur:
                out.write_text(cur.rstrip() + "\n\n" + render(f), encoding="utf-8")
                done.append(f"{rel} (appended)")
        elif out.exists() and not a.force:
            skipped.append(rel)
        else:
            out.write_text(render(f), encoding="utf-8")
            if rel.name == "crew":
                out.chmod(out.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            done.append(str(rel))

    owners = dst / "coord" / "owners.json"
    if owners.exists() and not a.force:
        skipped.append(owners.relative_to(dst))
    else:
        owners.write_text(json.dumps(make_owners(human, chats), indent=2) + "\n", encoding="utf-8")
        done.append("coord/owners.json")

    if a.demo and "core" in chats:
        seed_demo(dst)
        done.append("demo job (src/core/greet.py)")

    gi = dst / ".gitignore"
    have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [x for x in IGNORE if x not in have]
    if add:
        gi.write_text("\n".join(have + ["", "# agent-lanes"] + add).lstrip() + "\n", encoding="utf-8")

    print(f"✅ agent-lanes installed in {dst} ({len(done)} files)")
    for s in skipped:
        print(f"   kept your existing {s} (use --force to replace)")
    if not shutil.which("claude"):
        print("⚠️  Claude Code not found. Install it first: https://code.claude.com/docs/en/setup")
    here = Path.cwd().resolve() == dst
    go = "./crew up" if here else f"cd {dst} && ./crew up"
    job = ("The demo job starts by itself in the 'core' window. Just watch." if a.demo and "core" in chats
           else f"In the '{chats[0]}' window, try:  /scope <something to build>")
    print(f"""
Next:
  {go}

That opens one Terminal window per chat. First time only: choose Yes when Claude Code asks to trust the folder.
{job}
This window is yours:  ./crew board  ·  ./crew inbox  ·  ./crew test <item> human pass
Who owns what lives in coord/owners.json (starts as src/<chat>/*).
""")


if __name__ == "__main__":
    main()
