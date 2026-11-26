"""Compile and run every code sample in a lesson; the real output is what the video shows.

Writes <lesson>/build/code.json: {"code/x.swift": {"source": ..., "output": ..., "verified": true|false}}

- With the channel's runner installed (Swift: `swiftc`), each file is compiled and run; a compile error or crash
  stops the build, so a broken sample can never reach a video.
- Without it, the output is read from code/<name>.expected and marked unverified; make.py refuses to render
  unverified samples unless you pass --allow-unverified (and the video gets a QA warning).
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

RUNNERS = {
    "swift": {"bin": "swiftc", "build": lambda src, exe: ["swiftc", "-O", str(src), "-o", str(exe)]},
}


def check_code(code: str, lang: str = "swift"):
    """Compile and run one snippet. -> {"ok": True/False/None, "output", "error"}; ok None = no compiler here."""
    r = RUNNERS[lang]
    if shutil.which(r["bin"]) is None:
        return {"ok": None, "output": "", "error": f"{r['bin']} is not installed: output not verified"}
    with tempfile.TemporaryDirectory() as td:
        src, exe = Path(td) / "main.swift", Path(td) / "a.out"
        src.write_text(code, encoding="utf-8")
        b = subprocess.run(r["build"](src, exe), capture_output=True, text=True)
        if b.returncode:
            err = "\n".join(l.replace(str(src), "main.swift") for l in b.stderr.splitlines() if "error" in l or "^" in l or l.strip())
            return {"ok": False, "output": "", "error": err[:2000]}
        try:
            p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "", "error": "Program ran for more than 20 seconds (infinite loop?)"}
        if p.returncode:
            return {"ok": False, "output": p.stdout.rstrip(), "error": f"Crashed (exit {p.returncode}): {p.stderr[:800]}"}
        return {"ok": True, "output": p.stdout.rstrip("\n"), "error": ""}


def run(lesson_dir: Path, lang: str):
    lesson = json.loads((lesson_dir / "lesson.json").read_text(encoding="utf-8"))
    files = sorted({s["file"] for ch in lesson["chapters"] for s in ch["scenes"] if s["type"] == "code"})
    r = RUNNERS[lang]
    have = shutil.which(r["bin"]) is not None
    result = {}
    for f in files:
        src = lesson_dir / f
        entry = {"source": src.read_text(encoding="utf-8").rstrip("\n")}
        if have:
            with tempfile.TemporaryDirectory() as td:
                exe = Path(td) / "a.out"
                b = subprocess.run(r["build"](src, exe), capture_output=True, text=True)
                if b.returncode:
                    raise SystemExit(f"{f} does not compile:\n{b.stderr}")
                p = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
                if p.returncode:
                    raise SystemExit(f"{f} crashed (exit {p.returncode}):\n{p.stderr}")
                entry.update(output=p.stdout.rstrip("\n"), verified=True)
                exp = src.with_suffix(".expected")
                if exp.exists() and exp.read_text(encoding="utf-8").rstrip("\n") != entry["output"]:
                    print(f"  note: {f} output differs from {exp.name}; the real output is used")
        else:
            exp = src.with_suffix(".expected")
            if not exp.exists():
                raise SystemExit(f"{r['bin']} is not installed and {exp.name} is missing: cannot show output for {f}")
            entry.update(output=exp.read_text(encoding="utf-8").rstrip("\n"), verified=False)
        result[f] = entry
        print(f"  {f}: {'verified' if entry['verified'] else 'UNVERIFIED (no ' + r['bin'] + ')'}")
    out = lesson_dir / "build"
    out.mkdir(exist_ok=True)
    (out / "code.json").write_text(json.dumps(result, indent=1), encoding="utf-8")
    return result
