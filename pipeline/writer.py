"""AI steps of the studio: write a script from the source, judge it, revise it, fix code.

The script is a structured JSON the app shows for review (see SCHEMA below). Nothing here touches video: the
approved script is turned into lesson.json by script_to_lesson.py, without AI, so what you approved is what renders.

The AI calls go through llm/picker.py (free OpenAI-compatible providers with fallback; keys in llm/.env).
Set SWIFY_MOCK_LLM=1 to try the whole app without any key (canned answers).
"""
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "llm"))

SCHEMA = """{
  "title": "Closures in Swift",
  "hook": "Functions without a name",
  "chapters": [
    {
      "title": "What is a closure?",
      "scenes": [
        {"kind": "intro", "say": "Today, let's learn closures in Swift."},
        {"kind": "idea", "label": "The idea", "on_screen": "A closure is a function without a name",
         "highlight": "closure", "sub": "You can pass it around like a value",
         "say": "A closure is a block of code without a name. You can store it in a variable and pass it around."},
        {"kind": "code", "label": "Your first closure",
         "code": "let greet = { (name: String) in\\n    print(\\"Hi, \\\\(name)\\")\\n}\\ngreet(\\"Swify\\")",
         "steps": [
           {"lines": [1], "say": "Curly braces start a closure, and `in` separates the parameters from the body."},
           {"lines": [2, 3], "say": "The body prints a greeting."},
           {"lines": [4], "say": "We call it like any function."}
         ],
         "expected_output": "Hi, Swify",
         "output_say": "And it prints our hello."}
      ]
    },
    {
      "title": "Recap",
      "scenes": [
        {"kind": "compare", "label": "Function vs closure",
         "left": {"title": "Function", "items": ["func greet()", "Has a name"]},
         "right": {"title": "Closure", "items": ["{ (x) in ... }", "No name needed"]},
         "left_say": "A function has a name.", "right_say": "A closure can be written right where you need it."},
        {"kind": "list", "label": "Recap", "items": [
           {"text": "Closures are unnamed functions", "say": "Closures are functions without a name."},
           {"text": "Write them in braces", "say": "You write them in curly braces."},
           {"text": "Call them like functions", "say": "And you call them like any function."}]},
        {"kind": "outro", "next": "Trailing closures", "say": "Next time, trailing closures. See you there!"}
      ]
    }
  ],
  "facts": [{"claim": "Closures can capture values from their surrounding context", "source": "Capturing Values"}]
}"""

RULES = """Rules:
- Teach ONLY what the SOURCE says. Do not add facts that are not in it. If the source does not cover something, leave it out.
- Every code sample is a complete Swift program (top-level code in main.swift, Swift 5.9+), compiles on its own,
  prints its result with print(), max {max_lines} lines, max 40 characters per line, 4-space indents, no imports needed
  unless used. "expected_output" is exactly what it prints.
- "steps" walk through the code in order; each step names the lines it explains (1-based) and is one or two short
  spoken sentences. Every non-empty line should be covered by some step.
- Narration ("say", "output_say", "left_say", ...) is spoken: short sentences, plain words, friendly, no markdown.
  Wrap code words in backticks, e.g. `in`, `Int?`, `sorted(by:)`; keep each backticked part free of spaces.
  Write numbers as digits. Every "say" ends with . ! or ?
- "on_screen" text is at most 8 words; "highlight" is one word that appears in "on_screen".
- "list" has 3 items, each "text" at most 6 words; compare sides have exactly 2 items each, at most 4 words.
- Scenes: the FIRST chapter starts with one "intro" scene; the LAST chapter ends with "list" (recap) then "outro".
  Every chapter must make sense on its own (it may become a YouTube Short).
- Allowed kinds: intro, idea, code, compare, list, outro. Use 2 to 4 scenes per chapter (plus intro/recap/outro).
- Each chapter's narration is {words} words in total.
- "facts" lists every factual claim you made with the source section it comes from.
Return ONLY the JSON object."""


def _llm(prompt, role="gen"):
    if os.environ.get("SWIFY_MOCK_LLM"):
        return _mock(prompt, role)
    from picker import ask_llm
    return ask_llm(prompt, role=role)


def _json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def plan_params(fmt, chapters):
    """fmt: 'short' = one ~50 s chapter; 'long' = N chapters for a YouTube video (each one can become a Short)."""
    if fmt == "short":
        return {"chapters": 1, "words": "110 to 150", "max_lines": 10}
    return {"chapters": max(2, chapters), "words": "130 to 190", "max_lines": 12}


def write_script(topic, level, fmt, chapters, source, source_title, notes=""):
    p = plan_params(fmt, chapters)
    prompt = f"""You write scripts for short animated Swift lessons. A friendly bird mascot, Swify, appears on screen,
but the lesson content is the focus: clear code, one idea at a time.

TOPIC: {topic}
VIEWER LEVEL: {level}
LENGTH: {p['chapters']} chapter(s)
{('NOTES FROM THE CREATOR: ' + notes) if notes.strip() else ''}

SOURCE (from the official Swift book, chapter "{source_title}"):
<<<
{source}
>>>

Write the lesson as JSON exactly in this shape (this example shows the format, not the content):
{SCHEMA}

{RULES.format(max_lines=p['max_lines'], words=p['words'])}"""
    return _json(_llm(prompt, "gen"))


def judge_script(script, source, source_title):
    prompt = f"""You are a strict Swift technical reviewer. Check this lesson script against the SOURCE and your Swift knowledge.
Look for: wrong or misleading claims, claims not supported by the source, code that would not compile or prints
something other than "expected_output", narration that does not match its code lines, confusing explanations
for the level, and anything a careful Swift developer would object to.

SOURCE (Swift book, "{source_title}"):
<<<
{source}
>>>

SCRIPT:
{json.dumps(script, indent=1)}

Return ONLY JSON: {{"verdict": "pass" or "fix",
 "issues": [{{"where": "chapter 1, scene 2", "severity": "error" or "warning", "problem": "...", "fix": "..."}}]}}
Use "error" only for things that are wrong; style points are "warning". An empty list is fine when it is correct."""
    out = _json(_llm(prompt, "judge"))
    out.setdefault("issues", [])
    out.setdefault("verdict", "pass" if not out["issues"] else "fix")
    return out


def revise_script(script, source, source_title, instructions, fmt, chapters):
    p = plan_params(fmt, chapters)
    source = source[:3500]  # the current script is in the prompt too: keep within free-tier token limits
    prompt = f"""Revise this Swift lesson script. Apply the INSTRUCTIONS; keep everything else as it is unless a rule below is broken.

INSTRUCTIONS:
{instructions}

SOURCE (Swift book, "{source_title}"):
<<<
{source}
>>>

CURRENT SCRIPT:
{json.dumps(script, indent=1)}

{RULES.format(max_lines=p['max_lines'], words=p['words'])}"""
    return _json(_llm(prompt, "gen"))


def fix_code(code, error, intent):
    prompt = f"""This Swift program must compile and run as main.swift (Swift 5.9+) but it fails.
What it is meant to show: {intent}

CODE:
{code}

ERROR:
{error}

Fix it with the smallest change; keep max 40 characters per line and the same number of lines if you can.
Return ONLY JSON: {{"code": "...", "expected_output": "...", "change": "one sentence"}}"""
    return _json(_llm(prompt, "gen"))


# ------------------------------------------------------------------ canned answers for trying the app without keys
def _mock(prompt, role):
    if role == "judge":
        return json.dumps({"verdict": "fix", "issues": [
            {"where": "chapter 1, scene 3", "severity": "warning",
             "problem": "Step 1 says `in` separates parameters from the body; also mention the return type can be inferred.",
             "fix": "Optional: add 'Swift infers the types here.'"}]})
    if prompt.startswith("This Swift program"):
        return json.dumps({"code": re.search(r"CODE:\n(.*?)\n\nERROR", prompt, re.S).group(1), "expected_output": "", "change": "no change (mock)"})
    return json.dumps({
        "title": "Closures in Swift", "hook": "Code you can pass around",
        "chapters": [
            {"title": "What is a closure?", "scenes": [
                {"kind": "intro", "say": "Today, let's learn closures in Swift."},
                {"kind": "idea", "label": "The idea", "on_screen": "A closure is code you can pass around",
                 "highlight": "closure", "sub": "Like a function, but without a name",
                 "say": "A closure is a self-contained block of code that you can pass around. It works like a function, but it does not need a name."},
                {"kind": "code", "label": "Sorting with a closure",
                 "code": "let names = [\"Chris\", \"Alex\", \"Ewa\"]\n\nlet sorted = names.sorted { a, b in\n    a < b\n}\nprint(sorted)",
                 "steps": [
                     {"lines": [1], "say": "Here is an array of names."},
                     {"lines": [3, 4, 5], "say": "We pass `sorted` a closure in braces. It gets two names and returns true when the first comes first."},
                     {"lines": [6], "say": "Then we print the result."}],
                 "expected_output": "[\"Alex\", \"Chris\", \"Ewa\"]",
                 "output_say": "The names come out in alphabetical order."}]},
            {"title": "Capturing values", "scenes": [
                {"kind": "code", "label": "A closure remembers",
                 "code": "func makeCounter() -> () -> Int {\n    var count = 0\n    return {\n        count += 1\n        return count\n    }\n}\nlet next = makeCounter()\n_ = next()\nprint(next())",
                 "steps": [
                     {"lines": [1, 2], "say": "This function starts a count at 0."},
                     {"lines": [3, 4, 5, 6], "say": "It returns a closure that adds 1 and returns the count."},
                     {"lines": [8, 9, 10], "say": "Each call to `next` uses the same captured count."}],
                 "expected_output": "2",
                 "output_say": "So the second call prints 2."},
                {"kind": "list", "label": "Recap", "items": [
                    {"text": "Closures are blocks of code", "say": "Closures are blocks of code you can pass around."},
                    {"text": "Write them in braces", "say": "You write them in curly braces."},
                    {"text": "They capture values", "say": "And they capture values from around them."}]},
                {"kind": "outro", "next": "Trailing closures", "say": "Next time, trailing closures. See you there!"}]}],
        "facts": [{"claim": "Closures are self-contained blocks of functionality that can be passed around", "source": "Introduction"},
                  {"claim": "A closure can capture constants and variables from the surrounding context", "source": "Capturing Values"}]})
