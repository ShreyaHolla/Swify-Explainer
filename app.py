"""Swify Studio: topic -> script (you review) -> lesson plan -> video, in your browser.

  streamlit run app.py        (opens http://localhost:8501)

Every lesson is saved in lessons/<slug>/draft.json, so you can stop at any step and come back.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "pipeline"))
import code_check  # noqa: E402
import script_to_lesson as s2l  # noqa: E402
import sources  # noqa: E402
import writer  # noqa: E402

LESSONS = ROOT / "lessons"
CHANNEL_ID = "swify"
CHANNEL_DIR = ROOT / "channels" / CHANNEL_ID
CHANNEL = json.loads((CHANNEL_DIR / "channel.json").read_text(encoding="utf-8"))
STEPS = ["Topic", "Script", "Lesson plan", "Video"]
STAGE_STEP = {"topic": 0, "review": 1, "approved": 2, "video": 3}
LEVELS = ["Beginner", "Intermediate", "Advanced"]

st.set_page_config(page_title="Swify Studio", page_icon=str(CHANNEL_DIR / "mascot" / "avatar.png"), layout="wide")
st.markdown("""
<style>
  .block-container {padding-top: 3.2rem; max-width: 1180px;}
  h1, h2, h3 {letter-spacing: -0.02em;}
  .steps {display:flex; gap:10px; margin: 0 0 1.4rem 0;}
  .step {flex:1; padding:10px 14px; border-radius:12px; background:#F3E4CC; color:#8C7462; font-weight:600; font-size:0.92rem;}
  .step.done {background:#F6D3B4; color:#4A2A1A;}
  .step.now {background:#E07B39; color:#FFFDF8;}
  .card {background:#FFFDF8; border:1px solid #E6D3B3; border-radius:14px; padding:14px 16px; height:100%;}
  .card .k {font-size:0.78rem; letter-spacing:0.08em; text-transform:uppercase; color:#8C7462; font-weight:600;}
  .card .v {font-size:1.35rem; font-weight:700; margin-top:2px;}
  .ok {color:#4F7A40;} .warn {color:#A9531E;} .bad {color:#B5533C;}
  .issue {border-left:4px solid #E6D3B3; padding:6px 12px; margin:6px 0; background:#FFFDF8; border-radius:0 10px 10px 0;}
  .issue.error {border-color:#B5533C;} .issue.warning {border-color:#E07B39;}
  .muted {color:#8C7462; font-size:0.9rem;}
  textarea[aria-label="Code"] {font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace !important; font-size: 0.92rem !important;}
</style>""", unsafe_allow_html=True)


# ------------------------------------------------------------------ storage
def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "lesson"


def load(slug):
    p = LESSONS / slug / "draft.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def save(d):
    p = LESSONS / d["slug"] / "draft.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    d["updated"] = time.strftime("%Y-%m-%d %H:%M")
    p.write_text(json.dumps(d, indent=1), encoding="utf-8")


def drafts():
    out = []
    for p in sorted(LESSONS.glob("*/draft.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            pass
    return out


def llm_ready():
    if os.environ.get("SWIFY_MOCK_LLM"):
        return "mock"
    env = ROOT / "llm" / ".env"
    txt = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(r"^LLM_BASE_URL=\S*(localhost|127\.0\.0\.1)", txt, re.M) or "localhost" in os.environ.get("LLM_BASE_URL", ""):
        return "ok"  # a model on this computer (e.g. Ollama) needs no key
    return "ok" if re.search(r"^LLM_API_KEY=(?!your-key-here)\S+", txt, re.M) or os.environ.get("LLM_API_KEY") else None


HAVE_SWIFTC = shutil.which("swiftc") is not None


# ------------------------------------------------------------------ checks (run after writing and after every save)
def run_checks(d, judge=True):
    sc = d["script"]
    d["checks"] = s2l.check(sc, d["fmt"])
    results = {}
    for ci, ch in enumerate(sc["chapters"]):
        for si, s in enumerate(ch["scenes"]):
            if s.get("kind") == "code":
                key = f"c{ci + 1}s{si + 1}"
                prev = d.get("code_results", {}).get(key)
                if prev and prev.get("code") == s["code"]:
                    results[key] = prev
                    continue
                r = code_check.check_code(s["code"], CHANNEL["code"]["lang"])
                r["code"] = s["code"]
                if r["ok"]:
                    if r["output"].strip() != s.get("expected_output", "").strip():
                        r["note"] = f"Real output differs from what the script expected ({s.get('expected_output', '')!r}); the real output will be shown. Check the narration still matches."
                    r["output_used"] = r["output"]
                else:
                    r["output_used"] = s.get("expected_output", "")
                results[key] = r
    d["code_results"] = results
    if judge:
        with st.spinner("Fact-checking the script against the Swift book…"):
            d["judge"] = writer.judge_script(sc, d["source"]["text"], d["source"]["chapter"])


def counts(d):
    cr = d.get("code_results", {}).values()
    return {
        "code_ok": sum(1 for r in cr if r["ok"]), "code_bad": sum(1 for r in cr if r["ok"] is False),
        "code_unv": sum(1 for r in cr if r["ok"] is None),
        "errors": sum(1 for c in d.get("checks", []) if c["severity"] == "error"),
        "judge_err": sum(1 for i in d.get("judge", {}).get("issues", []) if i.get("severity") == "error"),
        "judge_warn": sum(1 for i in d.get("judge", {}).get("issues", []) if i.get("severity") != "error"),
    }


def spoken_seconds(sc):
    n = 0
    for ch in sc["chapters"]:
        for s in ch["scenes"]:
            for k in ("say", "output_say", "left_say", "right_say"):
                n += len(s.get(k, "").split())
            n += sum(len(x.get("say", "").split()) for x in s.get("steps", []))
            n += sum(len(x.get("say", "").split()) for x in s.get("items", []) if isinstance(x, dict))
    return n / 2.5 + 2.5 * sum(len(ch["scenes"]) for ch in sc["chapters"])


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.image(str(CHANNEL_DIR / "mascot" / "avatar.png"), width=110)
    st.markdown("### Swify Studio")
    if st.button("＋ New lesson", width="stretch", type="primary"):
        st.session_state.slug = None
        st.rerun()
    st.markdown("**Your lessons**")
    for dd in drafts():
        label = f"{dd.get('topic', dd['slug'])}  ·  {STEPS[STAGE_STEP.get(dd.get('stage', 'topic'), 0)]}"
        if st.button(label, key=f"open_{dd['slug']}", width="stretch"):
            st.session_state.slug = dd["slug"]
            st.rerun()
    st.divider()
    lr = llm_ready()
    st.markdown(f"AI writer: {'✅ connected' if lr == 'ok' else '🧪 demo answers' if lr == 'mock' else '⚠️ no key'}")
    if not lr:
        st.caption("Copy llm/.env.example to llm/.env and add a free API key (e.g. Groq), or point it at a local Ollama model, then restart.")
    st.markdown(f"Swift compiler: {'✅ found' if HAVE_SWIFTC else '⚠️ not found'}")
    if not HAVE_SWIFTC:
        st.caption("Install Xcode command line tools (`xcode-select --install`) so code is compiled and run.")

if "slug" not in st.session_state and st.query_params.get("lesson"):
    st.session_state.slug = st.query_params.get("lesson")
slug = st.session_state.get("slug")
if slug:
    st.query_params["lesson"] = slug
elif "lesson" in st.query_params:
    del st.query_params["lesson"]
d = load(slug) if slug else None
stage = d["stage"] if d else "topic"
step = STAGE_STEP[stage]

st.markdown('<div class="steps">' + "".join(
    f'<div class="step {"now" if i == step else "done" if i < step else ""}">{i + 1}. {name}</div>' for i, name in enumerate(STEPS)
) + "</div>", unsafe_allow_html=True)


# ------------------------------------------------------------------ step 1: topic
def step_topic():
    st.header("What should Swify teach?")
    topic = st.text_input("Topic", value=(d or {}).get("topic", ""), placeholder="e.g. Closures and capturing values")
    c1, c2, c3 = st.columns(3)
    level = c1.selectbox("Viewer level", LEVELS, index=LEVELS.index((d or {}).get("level", "Beginner")))
    fmt_label = c2.radio("Format", ["Long video + Shorts", "Short only"], index=0 if (d or {}).get("fmt", "long") == "long" else 1)
    fmt = "long" if fmt_label.startswith("Long") else "short"
    chapters = c3.number_input("Chapters", 2, 6, (d or {}).get("chapters", 3), disabled=fmt == "short",
                               help="Each chapter is about 1 minute and can also become its own Short.")
    titles = list(sources.SWIFT_BOOK)
    suggested = sources.suggest_chapter(topic) if topic else "The Basics"
    book = st.selectbox("Source: Swift book chapter", titles, index=titles.index((d or {}).get("source", {}).get("chapter", suggested)) if d else titles.index(suggested),
                        help="The script is written only from this chapter of the official Swift book.")
    notes = st.text_area("Notes for the writer (optional)", value=(d or {}).get("notes", ""),
                         placeholder="e.g. Use a shopping-cart example. Skip escaping closures.")
    own = st.text_area("Extra source text (optional)", value=(d or {}).get("own_source", ""), height=90,
                       placeholder="Paste anything else the lesson must be based on (docs, your notes).")
    disabled = not topic.strip() or not llm_ready()
    if st.button("✍️  Write the script", type="primary", disabled=disabled):
        try:
            with st.status("Writing your script…", expanded=True) as s:
                s.write(f"Reading the Swift book: **{book}**")
                try:
                    text, url, used = sources.excerpt(book, topic)
                except Exception as e:  # offline or GitHub unreachable: fall back to pasted text
                    if not own.strip():
                        st.error(f"Could not load the Swift book ({e}). Paste source text above and try again.")
                        return
                    text, url, used = "", "", []
                if own.strip():
                    text = (text + "\n\n## Creator's source notes\n" + own.strip())[-sources.MAX_CHARS - 2000:]
                s.write(f"Using sections: {', '.join(used) or 'your pasted text'}")
                s.write("Drafting the lesson…")
                script = writer.write_script(topic, level, fmt, int(chapters), text, book, notes)
                nd = {"slug": (d or {}).get("slug") or f"{slugify(topic)}-{date.today():%m%d}", "topic": topic, "level": level, "fmt": fmt,
                      "chapters": int(chapters), "notes": notes, "own_source": own,
                      "source": {"chapter": book, "url": url, "sections": used, "text": text},
                      "script": script, "history": [], "stage": "review", "created": time.strftime("%Y-%m-%d %H:%M")}
                s.write("Compiling the code samples and fact-checking…")
                run_checks(nd)
                save(nd)
                s.update(label="Script ready for your review", state="complete")
            st.session_state.slug = nd["slug"]
            st.rerun()
        except Exception as e:
            st.error(f"The AI step failed: {e}")


# ------------------------------------------------------------------ step 2: review
def lines_str(v):
    return ", ".join(str(x) for x in v)


def parse_lines(s):
    return [int(x) for x in re.findall(r"\d+", s)]


def step_review():
    sc = d["script"]
    c = counts(d)
    st.header(sc.get("title", d["topic"]))
    src = d["source"]
    secs = " · " + ", ".join(src["sections"]) if src["sections"] else ""
    st.markdown(f'<div class="muted">Based on the Swift book: <a href="{src["url"]}">{src["chapter"]}</a>{secs} · about {spoken_seconds(sc) / 60:.1f} min</div>',
                unsafe_allow_html=True)
    k1, k2, k3 = st.columns(3)
    jv = d.get("judge", {})
    parts = ([f"{c['judge_err']} error" + ("s" if c["judge_err"] > 1 else "")] if c["judge_err"] else []) + \
            ([f"{c['judge_warn']} note" + ("s" if c["judge_warn"] > 1 else "")] if c["judge_warn"] else [])
    fact_txt = ", ".join(parts) or "No problems found"
    fact_cls = "bad" if c["judge_err"] else "warn" if c["judge_warn"] else "ok"
    k1.markdown(f'<div class="card"><div class="k">Fact check</div><div class="v {fact_cls}">{fact_txt}</div></div>', unsafe_allow_html=True)
    code_txt = "{} failing".format(c["code_bad"]) if c["code_bad"] else "{} compiled and run".format(c["code_ok"]) if c["code_ok"] else ""
    if c["code_unv"]:
        code_txt += (" · " if code_txt else "") + "{} not verified".format(c["code_unv"])
    code_cls = "bad" if c["code_bad"] else "warn" if c["code_unv"] else "ok"
    k2.markdown(f'<div class="card"><div class="k">Code samples</div><div class="v {code_cls}">{code_txt or "none"}</div></div>', unsafe_allow_html=True)
    fc = d.get("checks", [])
    fmt_txt = "Looks good" if not fc else "{} thing(s) to look at".format(len(fc))
    fmt_cls = "bad" if c["errors"] else "warn" if fc else "ok"
    k3.markdown(f'<div class="card"><div class="k">Format</div><div class="v {fmt_cls}">{fmt_txt}</div></div>', unsafe_allow_html=True)

    issues = [{**i, "from": "Fact check"} for i in jv.get("issues", [])] + [{**i, "from": "Format"} for i in fc]
    for key, r in d.get("code_results", {}).items():
        if r["ok"] is False:
            issues.append({"where": key, "severity": "error", "problem": "Code does not run: " + r["error"][:400], "from": "Compiler"})
        if r.get("note"):
            issues.append({"where": key, "severity": "warning", "problem": r["note"], "from": "Compiler"})
    if issues:
        with st.expander(f"Things to look at ({len(issues)})", expanded=True):
            for i in issues:
                sev = i.get("severity", "warning")
                fix = "<br><span class=muted>Suggested: " + i["fix"] + "</span>" if i.get("fix") else ""
                st.markdown(f'<div class="issue {sev}"><b>{i["from"]} · {i["where"]}</b> — {i["problem"]}{fix}</div>', unsafe_allow_html=True)
    with st.expander("Ask the AI for changes"):
        req = st.text_area("What should change?", placeholder="e.g. Use a simpler example in chapter 2. Explain $0 shorthand.", key="revise_req")
        a, b = st.columns(2)
        if a.button("Revise with my request", disabled=not req.strip()):
            revise(req)
        if b.button("Fix the fact-check and format issues", disabled=not issues):
            revise("Fix these review findings:\n" + "\n".join(f"- {i['where']}: {i['problem']} {i.get('fix', '')}" for i in issues))

    st.subheader("Script")
    st.caption("Edit anything below, then save. Code is compiled again when it changes. In narration, put code in `backticks`.")
    with st.form("script_form"):
        t1, t2 = st.columns(2)
        title = t1.text_input("Video title", sc.get("title", ""))
        hook = t2.text_input("Hook (title card / Short banner)", sc.get("hook", ""))
        edited = {"title": title, "hook": hook, "chapters": [], "facts": sc.get("facts", [])}
        fix_buttons = {}
        for ci, ch in enumerate(sc["chapters"]):
            st.markdown(f"#### Chapter {ci + 1}")
            ech = {"title": st.text_input("Chapter title", ch["title"], key=f"ct{ci}"), "scenes": []}
            for si, s in enumerate(ch["scenes"]):
                k = s["kind"]
                key = f"c{ci + 1}s{si + 1}"
                with st.expander(f"Scene {si + 1} · {k}  —  {s.get('label') or s.get('on_screen') or s.get('say', '')[:60]}", expanded=k == "code"):
                    e = {"kind": k}
                    if k in ("idea", "code", "compare", "list"):
                        e["label"] = st.text_input("Label (small heading)", s.get("label", ""), key=f"{key}lb")
                    if k == "intro":
                        e["say"] = st.text_area("Narration", s["say"], key=f"{key}say", height=70)
                    elif k == "idea":
                        a, b = st.columns([3, 1])
                        e["on_screen"] = a.text_input("On screen (≤ 8 words)", s.get("on_screen", ""), key=f"{key}os")
                        e["highlight"] = b.text_input("Highlight word", s.get("highlight", ""), key=f"{key}hl")
                        e["sub"] = st.text_input("Second line on screen", s.get("sub", ""), key=f"{key}sub")
                        e["say"] = st.text_area("Narration", s["say"], key=f"{key}say", height=80)
                    elif k == "code":
                        a, b = st.columns([3, 2])
                        e["code"] = a.text_area("Code", s["code"], key=f"{key}code", height=max(160, 26 * (s["code"].count("\n") + 2)))
                        r = d.get("code_results", {}).get(key, {})
                        with b:
                            if r.get("ok"):
                                st.success("Compiled and ran. Output:")
                                st.code(r["output"] or "(no output)", language=None)
                            elif r.get("ok") is False:
                                st.error("Does not run")
                                st.code(r["error"][:900], language=None)
                                fix_buttons[key] = st.form_submit_button(f"🛠 Ask AI to fix code in {key}")
                            else:
                                st.warning("Not verified (no Swift compiler). Expected output:")
                                st.code(s.get("expected_output", ""), language=None)
                        e["expected_output"] = r.get("output") if r.get("ok") else s.get("expected_output", "")
                        e["steps"] = []
                        for ti, stp in enumerate(s.get("steps", [])):
                            x, y = st.columns([1, 5])
                            ln = x.text_input(f"Step {ti + 1} lines", lines_str(stp["lines"]), key=f"{key}st{ti}l")
                            sy = y.text_input(f"Step {ti + 1} narration", stp["say"], key=f"{key}st{ti}s")
                            if sy.strip():
                                e["steps"].append({"lines": parse_lines(ln), "say": sy})
                        x, y = st.columns([1, 5])
                        nl = x.text_input("New step lines", "", key=f"{key}newl", placeholder="e.g. 7")
                        ns = y.text_input("New step narration", "", key=f"{key}news", placeholder="optional: add a step")
                        if ns.strip():
                            e["steps"].append({"lines": parse_lines(nl), "say": ns})
                        e["output_say"] = st.text_input("Narration when the output appears", s.get("output_say", ""), key=f"{key}os")
                    elif k == "compare":
                        a, b = st.columns(2)
                        e["left"] = {"title": a.text_input("Left title", s["left"]["title"], key=f"{key}lt"),
                                     "items": [x for x in a.text_area("Left items (one per line)", "\n".join(s["left"]["items"]), key=f"{key}li", height=70).split("\n") if x.strip()]}
                        e["right"] = {"title": b.text_input("Right title", s["right"]["title"], key=f"{key}rt"),
                                      "items": [x for x in b.text_area("Right items (one per line)", "\n".join(s["right"]["items"]), key=f"{key}ri", height=70).split("\n") if x.strip()]}
                        e["left_say"] = a.text_area("Left narration", s.get("left_say", ""), key=f"{key}ls", height=70)
                        e["right_say"] = b.text_area("Right narration", s.get("right_say", ""), key=f"{key}rs", height=70)
                    elif k == "list":
                        e["items"] = []
                        for ii, it in enumerate(s["items"]):
                            x, y = st.columns([2, 3])
                            tx = x.text_input(f"Point {ii + 1} on screen", it["text"], key=f"{key}it{ii}")
                            sy = y.text_input(f"Point {ii + 1} narration", it["say"], key=f"{key}is{ii}")
                            if tx.strip():
                                e["items"].append({"text": tx, "say": sy})
                    elif k == "outro":
                        e["next"] = st.text_input("Next lesson", s.get("next", ""), key=f"{key}nx")
                        e["say"] = st.text_area("Narration", s["say"], key=f"{key}say", height=70)
                    if st.checkbox("Remove this scene", key=f"{key}rm"):
                        e["_remove"] = True
                    ech["scenes"].append(e)
            edited["chapters"].append(ech)
        a, b, c3 = st.columns([1, 1, 2])
        saved = a.form_submit_button("💾 Save edits", type="primary")
        saved_judge = b.form_submit_button("Save + fact-check again")

    for ch in edited["chapters"]:
        ch["scenes"] = [s for s in ch["scenes"] if not s.pop("_remove", False)]
    fix_key = next((k for k, v in fix_buttons.items() if v), None)
    if saved or saved_judge or fix_key:
        d["history"].append({"at": time.strftime("%H:%M"), "script": sc})
        d["history"] = d["history"][-10:]
        d["script"] = edited
        if fix_key:
            ci, si = [int(x) - 1 for x in re.findall(r"\d+", fix_key)]
            s = edited["chapters"][ci]["scenes"][si]
            with st.spinner("Asking the AI to fix the code…"):
                fx = writer.fix_code(s["code"], d["code_results"][fix_key]["error"], " ".join(x["say"] for x in s["steps"]))
            s["code"], s["expected_output"] = fx["code"], fx.get("expected_output", s.get("expected_output", ""))
            st.toast(f"Code changed: {fx.get('change', '')}")
        run_checks(d, judge=bool(saved_judge))
        save(d)
        st.rerun()

    st.divider()
    blockers = c["code_bad"] + c["errors"]
    a, b = st.columns([2, 3])
    ok_unv = True
    if c["code_unv"]:
        ok_unv = b.checkbox("I checked the code myself (no Swift compiler on this computer)")
    ack = True
    if c["judge_err"]:
        ack = b.checkbox("I've read the fact-check errors and the script is correct")
    if blockers:
        b.markdown(f'<span class="bad">Fix {blockers} blocking problem(s) above before approving.</span>', unsafe_allow_html=True)
    if a.button("✅ Approve script", type="primary", disabled=bool(blockers) or not ack or not ok_unv):
        d["stage"] = "approved"
        d["approved_at"] = time.strftime("%Y-%m-%d %H:%M")
        make_lesson()
        save(d)
        st.rerun()
    if d["history"] and st.button("↩︎ Undo last change"):
        d["script"] = d["history"].pop()["script"]
        run_checks(d, judge=False)
        save(d)
        st.rerun()


def revise(instr):
    try:
        with st.spinner("Revising the script…"):
            new = writer.revise_script(d["script"], d["source"]["text"], d["source"]["chapter"], instr, d["fmt"], d["chapters"])
        d["history"].append({"at": time.strftime("%H:%M"), "script": d["script"]})
        d["script"] = new
        run_checks(d)
        save(d)
        st.rerun()
    except Exception as e:
        st.error(f"Revision failed: {e}")


def make_lesson():
    res = {k: {"output": r.get("output_used", ""), "verified": bool(r.get("ok"))} for k, r in d.get("code_results", {}).items()}
    s2l.convert(d["script"], LESSONS / d["slug"], CHANNEL, d["fmt"], res)


# ------------------------------------------------------------------ step 3: lesson plan
def step_plan():
    les = json.loads((LESSONS / d["slug"] / "lesson.json").read_text(encoding="utf-8"))
    st.header("Lesson plan")
    st.caption("This is what will be animated, made directly from your approved script. Each row is one scene.")
    rows = []
    for ci, ch in enumerate(les["chapters"]):
        for s in ch["scenes"]:
            what = s.get("text") or s.get("title") or s.get("eyebrow") or ""
            if s["type"] == "code":
                what = f'{s["eyebrow"]} · {len(s["reveal"])} reveal steps + output'
            if s["type"] == "list":
                what = " / ".join(s["items"])
            swify = ", ".join([m["beat"] for m in s.get("mascot", []) if "beat" in m] + [f'says "{m["line"]}"' for m in s.get("mascot", []) if "line" in m])
            rows.append({"Chapter": f"{ci + 1}. {ch['title']}", "Scene": s["type"], "On screen": what, "Swify": swify,
                         "≈ seconds": round(len(s.get("say", "").split()) / 2.5 + 1.5 + s.get("hold", 0))})
    st.dataframe(rows, width="stretch", hide_index=True)
    vids = (["YouTube video (16:9)"] if les.get("landscape", True) else []) + [f"Short {i + 1}: {sh['hook']}" for i, sh in enumerate(les["shorts"])]
    st.markdown("**Will make:** " + " · ".join(vids))
    with st.expander("lesson.json"):
        st.json(les)
    a, b = st.columns([1, 4])
    if a.button("🎬 Continue to video", type="primary"):
        d["stage"] = "video"
        save(d)
        st.rerun()
    if b.button("← Back to the script"):
        d["stage"] = "review"
        save(d)
        st.rerun()


# ------------------------------------------------------------------ step 4: video
def step_video():
    les = json.loads((LESSONS / d["slug"] / "lesson.json").read_text(encoding="utf-8"))
    out = LESSONS / d["slug"] / "out"
    st.header("Make the video")
    a, b = st.columns(2)
    voice = a.radio("Voice", ["AI voice (Edge, online)", "AI voice (Kokoro, offline)"], index=0 if d.get("voice", "edge") == "edge" else 1)
    voice = "edge" if "Edge" in voice else "kokoro"
    with b:
        yt = st.checkbox("YouTube video (16:9)", value=les.get("landscape", True), disabled=not les.get("landscape", True))
        picks = [i + 1 for i, sh in enumerate(les["shorts"]) if st.checkbox(f"Short {i + 1}: {sh['hook']}", value=i == 0, key=f"sh{i}")]
    est = spoken_seconds(d["script"]) * (3.5 if yt else 0) + sum(30 * 3.5 for _ in picks)
    st.caption(f"Rendering takes roughly {max(1, round(est / 60))} min on a laptop. You can leave this tab open and come back.")
    if st.button("▶️  Render", type="primary", disabled=not (yt or picks)):
        d["voice"] = voice
        save(d)
        cmd = [sys.executable, str(ROOT / "make.py"), str(LESSONS / d["slug"]), "--voice", voice]
        if not yt:
            cmd.append("--no-youtube")
        cmd += ["--shorts", ",".join(map(str, picks)) if picks else "0"]
        if not HAVE_SWIFTC:
            cmd.append("--allow-unverified")
        box = st.empty()
        log = []
        with st.status("Rendering…", expanded=True) as s:
            p = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
            for line in p.stdout:
                log.append(line.rstrip())
                box.code("\n".join(log[-18:]), language=None)
            p.wait()
            s.update(label="Done" if p.returncode == 0 else "Render failed", state="complete" if p.returncode == 0 else "error")
        if p.returncode == 0:
            d["rendered_at"] = time.strftime("%Y-%m-%d %H:%M")
            save(d)
    files = sorted(out.glob("*.mp4")) if out.exists() else []
    if files:
        st.subheader("Your videos")
        for f in files:
            if f.name.endswith("_raw.mp4"):
                continue
            portrait = "short" in f.stem
            cols = st.columns([1, 2] if portrait else [3, 1])
            with cols[0]:
                st.video(str(f))
            with cols[1]:
                st.markdown(f"**{f.name}**  \n{f.stat().st_size / 1e6:.1f} MB")
                st.download_button("Download", f.read_bytes(), file_name=f.name, key=f"dl{f.name}")
        extras = [p for p in out.glob("*") if p.suffix in (".srt", ".txt")]
        for p in extras:
            st.download_button(f"Download {p.name}", p.read_bytes(), file_name=p.name, key=f"dl{p.name}")
    if st.button("← Back to the lesson plan"):
        d["stage"] = "approved"
        save(d)
        st.rerun()


{"topic": step_topic, "review": step_review, "approved": step_plan, "video": step_video}[stage]()
