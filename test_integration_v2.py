"""test_integration_v2.py - Tests des modules V2."""
from __future__ import annotations
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from conversation import Conversation
from codebase_index import CodebaseIndex
from tool_use import Tool, ToolRegistry, parse_tool_calls, make_standard_tools

PASS, FAIL = [], []

def ok(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" +
          (f" :: {detail}" if detail else ""))


def main() -> int:
    print("=" * 72)
    print("INTEGRATION V2 - conversation + index + tools")
    print("=" * 72)
    tmp = Path(tempfile.mkdtemp(prefix="memolib-v2-"))
    try:
        print("\n[C] conversation")
        db = tmp / "conv.db"
        c = Conversation(db)
        c.add("user", "bonjour")
        c.add("assistant", "salut")
        ok("C1 tour ajoute", len(c.turns) == 2)
        c2 = Conversation(db, conversation_id=c.conversation_id)
        ok("C2 persistance", len(c2.turns) == 2)
        ok("C3 to_messages", len(c2.to_messages()) == 2)
        ok("C4 summary", "bonjour" in c2.summary_for_context())

        print("\n[I] codebase_index")
        src_dir = tmp / "proj"
        src_dir.mkdir()
        (src_dir / "a.py").write_text(
            "import os\nclass Foo:\n    pass\n"
            "def bar():\n    pass\n", encoding="utf-8")
        (src_dir / "b.py").write_text(
            "from a import Foo\ndef baz():\n    pass\n", encoding="utf-8")
        idx = CodebaseIndex(src_dir)
        n = idx.build()
        ok("I1 fichiers indexes", n == 2, f"n={n}")
        ok("I2 find_symbol Foo", len(idx.find_symbol("Foo")) == 1)
        ok("I3 find_symbol bar", len(idx.find_symbol("bar")) == 1)
        ok("I4 search baz", any(r["name"] == "baz" for r in idx.search("baz")))
        st = idx.stats()
        ok("I5 stats", st["files"] == 2 and st["symbols"] >= 3, str(st))

        print("\n[P] persistence index")
        out = tmp / "index.json"
        idx.save(out)
        idx2 = CodebaseIndex.load(out)
        ok("P1 reload", idx2.stats()["files"] == 2)

        print("\n[T] tool_use")
        reg = ToolRegistry()
        reg.register(Tool("echo", "echo", {"type": "object"}, lambda msg: msg))
        ok("T1 execute blocked", "BLOQUE" in reg.execute("echo", {"msg": "hi"}))
        ok("T2 unknown blocked", "BLOQUE" in reg.execute("nope", {}))
        ok("T3 schemas", len(reg.schemas()) == 0)

        print("\n[TC] parse_tool_calls")
        text = 'bla <tool_call>{"name": "read_file", "args": {"path": "a.py"}}</tool_call>'
        calls = parse_tool_calls(text)
        ok("TC1 parsed", len(calls) == 1 and calls[0][0] == "read_file")

        print("\n[ST] standard tools")
        reg2 = ToolRegistry()
        make_standard_tools(src_dir, reg2, idx)
        ok("ST1 read_file", "class Foo" in reg2.execute("read_file", {"path": "a.py"}))
        ok("ST2 list_files", len(reg2.execute("list_files", {})) >= 2)
        ok("ST3 find_symbol", "Foo" in reg2.execute("find_symbol", {"name": "Foo"}))

        print("\n" + "=" * 72)
        print(f"RESULTAT V2 : {len(PASS)} PASS / {len(FAIL)} FAIL")
        if FAIL:
            print("ECHECS :", ", ".join(FAIL))
        print("=" * 72)
        return 0 if not FAIL else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
