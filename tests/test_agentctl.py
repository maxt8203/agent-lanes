"""End-to-end tests: run agentctl as a subprocess against a temp state folder.

    python3 -m unittest discover tests
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "template"


class AgentctlTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.proj = self.tmp / "proj"
        subprocess.run([sys.executable, str(ROOT / "install.py"), str(self.proj), "--python", sys.executable,
                        "--name", "sam", "--chats", "core,pricing,reports"],
                       check=True, capture_output=True, stdin=subprocess.DEVNULL)
        self.ctl = self.proj / "coord" / "agentctl.py"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_ac(self, *args, who=None, stdin=None, claude=False):
        env = {k: v for k, v in os.environ.items()
               if k not in ("AGENT_ID", "AGENTCTL_HOME", "CLAUDECODE", "CLAUDE_PROJECT_DIR")}
        if who:
            env["AGENT_ID"] = who
        if claude:
            env["CLAUDE_PROJECT_DIR"] = str(self.proj)
        return subprocess.run([sys.executable, str(self.ctl), *args], env=env, cwd=self.proj,
                              input=stdin, capture_output=True, text=True)

    def inbox(self, who=None):
        return self.run_ac("inbox", who=who).stdout

    # --- slots ---
    def test_slot_is_exclusive_across_lanes_and_chats(self):
        self.assertEqual(self.run_ac("slot", "take", "app-editor", "--lane", "ed1", who="core").returncode, 0)
        r = self.run_ac("slot", "take", "app-editor", "--lane", "ed2", who="core")
        self.assertEqual(r.returncode, 3, "second lane of same chat must be blocked")
        r = self.run_ac("slot", "take", "app-editor", "--lane", "ed1", who="pricing")
        self.assertEqual(r.returncode, 3)
        self.assertIn("#2", r.stdout)
        self.assertNotEqual(self.run_ac("slot", "release", "app-editor", "--lane", "ed1", who="pricing").returncode, 0)
        self.assertEqual(self.run_ac("slot", "release", "app-editor", "--lane", "ed1", who="core").returncode, 0)
        self.assertIn("free for lane ed2", self.inbox("core"))
        self.assertEqual(self.run_ac("slot", "take", "app-editor", "--lane", "ed2", who="core").returncode, 0)

    def test_slot_expires(self):
        self.run_ac("slot", "take", "app-editor", "--ttl", "0", who="core")
        self.assertEqual(self.run_ac("slot", "take", "app-editor", who="pricing").returncode, 0)

    def test_coordinator_force_release(self):
        self.run_ac("slot", "take", "app-editor", who="core")
        self.assertNotEqual(self.run_ac("slot", "release", "app-editor", "--force", who="pricing").returncode, 0)
        self.assertEqual(self.run_ac("slot", "release", "app-editor", "--force", who="coordinator").returncode, 0)

    # --- ownership hook ---
    def hook(self, who, path):
        payload = json.dumps({"tool_name": "Edit", "tool_input": {"file_path": path}})
        return self.run_ac("hook", "owner", who=who, stdin=payload, claude=True)

    def test_owner_hook(self):
        self.assertEqual(self.hook("pricing", "src/pricing/calc.py").returncode, 0)
        r = self.hook("pricing", str(self.proj / "src/core/form.py"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("owned by 'core'", r.stderr)
        self.assertEqual(self.hook("pricing", "README.md").returncode, 0, "unowned files are open")
        self.assertEqual(self.hook("coordinator", "src/core/form.py").returncode, 2, "coordinator doesn't build")
        self.assertEqual(self.hook("core", "coord/approvals.json").returncode, 2, "approvals are human-only")
        self.assertEqual(self.hook(None, "src/core/form.py").returncode, 0, "human mode is unrestricted")

    # --- Q&A ---
    def test_questions_route_and_export(self):
        self.assertIn("P1", self.run_ac("q", "add", "pricing", "VAT", "included?", who="pricing").stdout)
        self.assertIn("P2", self.run_ac("q", "add", "pricing", "Round", "to", "£1?", "--phase", "after", who="pricing").stdout)
        self.assertIn("New question P1", self.inbox("coordinator"))
        self.run_ac("q", "answer", "p1", "Yes,", "20%", who="coordinator")
        self.assertIn("Answer to P1", self.inbox("pricing"))
        self.run_ac("q", "export")
        qa = (self.proj / "coord" / "QA.md").read_text(encoding="utf-8")
        self.assertIn("## Pricing [Partly answered]", qa)
        self.assertIn("### Before building [Answered]", qa)
        self.assertIn("### After building [Open]", qa)
        board = self.run_ac("board").stdout
        self.assertIn("pricing        0 / 1", board)  # only the 'after' question is still open
        self.assertNotIn("blocks building", board)

    # --- test gate: AI -> critic -> human ---
    def test_gate_order(self):
        self.assertNotEqual(self.run_ac("test", "quote-form", "human", "pass").returncode, 0, "AI must pass first")
        self.run_ac("test", "quote-form", "ai", "pass", who="core")
        r = self.run_ac("test", "quote-form", "human", "pass")
        self.assertNotEqual(r.returncode, 0, "critic must pass first")
        self.assertIn("critic", r.stderr)
        self.run_ac("review", "quote-form", "ship", "pass", "solid", who="core")
        self.assertIn("passed the AI test and the critic", self.inbox())
        self.assertNotEqual(self.run_ac("test", "quote-form", "human", "pass", who="core").returncode, 0)
        self.assertNotEqual(self.run_ac("test", "quote-form", "human", "pass", claude=True).returncode, 0)
        self.assertIn("TESTED", self.run_ac("test", "quote-form", "human", "pass", "looks", "good").stdout)
        r = self.run_ac("test", "quote-form", "ai", "pass", who="core")
        self.assertNotIn("TESTED", r.stdout, "new AI run resets critic + human")
        self.assertIn("critic -", r.stdout)

    def test_ship_review_needs_ai_pass(self):
        self.assertNotEqual(self.run_ac("review", "x", "ship", "pass", who="core").returncode, 0)
        self.assertEqual(self.run_ac("review", "x", "scope", "fix", "--findings", "2", who="core").returncode, 0)

    def test_critic_dispute_goes_to_coordinator(self):
        self.run_ac("test", "x", "ai", "pass", who="core")
        self.run_ac("review", "x", "ship", "fix", "--findings", "3", who="core")
        self.inbox("coordinator")  # clear
        self.run_ac("test", "x", "ai", "pass", who="core")
        self.run_ac("review", "x", "ship", "block", "still", "broken", "--findings", "1", who="core")
        self.assertIn("Dispute on x", self.inbox("coordinator"))
        self.assertNotEqual(self.run_ac("review", "x", "ship", "pass", "--override", "nope", who="core").returncode, 0)
        self.assertEqual(self.run_ac("review", "x", "ship", "pass", "--override", "ok", who="coordinator").returncode, 0)
        self.assertIn("critic pass", self.run_ac("board").stdout)

    def test_findings_stats(self):
        self.run_ac("review", "x", "scope", "fix", "--findings", "4", who="core")
        out = self.run_ac("findings", "3", "1", who="core").stdout
        self.assertIn("4 findings", out)
        self.assertIn("75% accepted", out)

    # --- messaging + hooks ---
    def test_status_and_inbox_hook(self):
        self.run_ac("status", "blocked", "need", "price", "list", who="pricing")
        r = self.run_ac("hook", "inbox", who="coordinator")
        self.assertIn("⚠️ [blocked] need price list", r.stdout)
        self.assertEqual(self.run_ac("hook", "inbox", who="coordinator").stdout, "", "delivered once")

    def test_session_hook_and_join(self):
        self.assertIn("human mode", self.run_ac("hook", "session").stdout)
        self.run_ac("join", "pricing", "--dir", str(self.proj))
        local = json.loads((self.proj / ".claude" / "settings.local.json").read_text())
        self.assertEqual(local["env"]["AGENT_ID"], "pricing")
        out = self.run_ac("hook", "session", claude=True).stdout  # picks identity from settings.local.json
        self.assertIn("You are 'pricing'", out)
        self.assertIn("Your role: build chat", out)

    def test_doctor_passes_on_fresh_install(self):
        r = self.run_ac("doctor", "--dir", str(self.proj))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_crew_launcher(self):
        crew = self.proj / "crew"
        self.assertTrue(os.access(crew, os.X_OK))
        env = {k: v for k, v in os.environ.items() if k not in ("AGENT_ID", "CLAUDECODE", "CLAUDE_PROJECT_DIR")}
        r = subprocess.run([str(crew)], capture_output=True, text=True, env=env)
        self.assertIn("coordinator core pricing reports", r.stdout)
        r = subprocess.run([str(crew), "board"], capture_output=True, text=True, env=env)
        self.assertIn("CHATS", r.stdout)
        r = subprocess.run([str(crew), "start", "nobody"], capture_output=True, text=True, env=env)
        self.assertNotEqual(r.returncode, 0)

    def test_crew_up_needs_macos(self):
        if sys.platform == "darwin":
            self.skipTest("opens real Terminal windows on macOS")
        r = subprocess.run([str(self.proj / "crew"), "up"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("needs macOS", r.stderr)

    def test_get_sh_one_liner(self):
        proj = self.tmp / "via-get"
        proj.mkdir()
        env = dict(os.environ, AGENT_LANES_SRC=str(ROOT))
        r = subprocess.run(["bash", str(ROOT / "get.sh"), "--demo"], cwd=proj, env=env,
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue((proj / "crew").exists())
        self.assertTrue((proj / "src/core/greet.py").exists(), "demo job seeded")
        self.assertIn("greet-name", (proj / "coord/.state/first-prompt-core.txt").read_text())
        demo_test = subprocess.run([sys.executable, str(proj / "tests/core/test_greet.py")], capture_output=True)
        self.assertEqual(demo_test.returncode, 0, "demo starts green")

    def test_get_sh_refuses_home_folder(self):
        home = self.tmp / "home"
        home.mkdir()
        env = dict(os.environ, HOME=str(home), AGENT_LANES_SRC=str(ROOT))
        r = subprocess.run(["bash", str(ROOT / "get.sh")], cwd=home, env=env, capture_output=True, text=True,
                           stdin=subprocess.DEVNULL)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("home folder", r.stderr)

    def test_owners_generated(self):
        o = json.loads((self.proj / "coord" / "owners.json").read_text())
        self.assertEqual(o["human"], "sam")
        self.assertEqual([o["chats"][c]["prefix"] for c in ("core", "pricing", "reports")], ["C", "P", "R"])
        self.assertIn("./crew send sam", (self.proj / "coord/roles/coordinator.md").read_text())

    def test_installer_merges_existing_project(self):
        proj = self.tmp / "existing"
        (proj / ".claude").mkdir(parents=True)
        (proj / "CLAUDE.md").write_text("# My rules\nKeep it tidy.\n")
        (proj / ".claude" / "settings.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(npm test:*)"]}, "hooks": {"Stop": [{"hooks": []}]}}))
        for _ in range(2):  # running twice must not duplicate anything
            subprocess.run([sys.executable, str(ROOT / "install.py"), str(proj), "--demo"],
                           check=True, capture_output=True, stdin=subprocess.DEVNULL)
        md = (proj / "CLAUDE.md").read_text()
        self.assertIn("Keep it tidy.", md)
        self.assertEqual(md.count("<!-- agent-lanes -->"), 1)
        st = json.loads((proj / ".claude" / "settings.json").read_text())
        self.assertIn("Bash(npm test:*)", st["permissions"]["allow"])
        self.assertIn("Stop", st["hooks"])
        self.assertEqual(len(st["hooks"]["PreToolUse"]), 1)

    def test_installer_sets_python_and_gitignore(self):
        settings = (self.proj / ".claude" / "settings.json").read_text()
        self.assertNotIn("{{PY}}", settings)
        json.loads(settings)
        self.assertIn("coord/.state/", (self.proj / ".gitignore").read_text())


if __name__ == "__main__":
    unittest.main()
