# UE Insights Profiling Skill

Find out what makes your Unreal Engine game slow, without learning the Unreal Insights window first.

Tell your AI assistant "mark the Fermenter for profiling" or "look at my last trace and tell me what costs FPS".
It adds the measurements to your code, reads the trace file, and explains the result in plain words.

This repository holds one skill: `ue-insights-profiling/`.

---

## What can it do?

**1. Add profiling marks to your code**
- You name a mechanic, a class or a file. The assistant finds the code and adds trace marks.
- Every mark gets a clear name (`Fermenter/Tick`) and a short comment, so everyone on the team knows what is measured.
- It checks its own work: no duplicate names, no broken marks, and the project still builds.
- It does not change how your game works. It only adds measurements.

**2. Read a trace file for you**
- Finds which parts of the game take the most time in every frame (CPU, UI, rendering and GPU).
- Tells you if the frame is limited by the game thread, the render thread or the GPU.
- Finds hitches (sudden slow frames) and says what caused each one.
- Shows how much your own mechanics cost, in milliseconds per frame.
- Compares two traces (before and after your change).
- Works from the command line. You do not need to open the Unreal Insights window.

**3. Help you record a trace**
- Gives you the right command and the steps for a clean recording.

---

## What do I need?

- An Unreal Engine C++ project (tested with UE 5.7 on Windows).
- Python 3.8 or newer. No extra packages are needed.
- An AI assistant that can use skills (for example Claude Code or Codex), or any chat assistant (see "No skill support?" below).

---

## Install (once per developer)

1. Download or clone this repository.
2. Copy the folder `ue-insights-profiling` into the skills folder of your AI tool. Keep the folder name.

| Tool | Skills folder |
|---|---|
| Claude Code (all projects) | `~/.claude/skills/ue-insights-profiling/` |
| Claude Code (one project) | `<your project>/.claude/skills/ue-insights-profiling/` |
| Codex CLI | `~/.codex/skills/ue-insights-profiling/` |
| Another agent | Any folder. Tell the agent: "Read `<path>/SKILL.md` and follow it." |

3. To update later, pull the latest version and copy the folder again.

---

## How to use it

Just ask in your own words. You do not need to type the skill name. For example:

- "Mark the OrderBoard for the profiler."
- "Add Unreal Insights measurements to the inventory code."
- "Look at the latest trace. What costs FPS?"
- "Why do I get stutters in this trace?"
- "Compare these two traces. Did my change help?"
- "How do I record a trace?"

Russian works too, for example "разметь Fermenter для профилировщика" or "глянь последний трейс, что жрёт фпс".

### A simple first session

1. Ask the assistant to mark a mechanic. Close the Unreal Editor when it asks to build.
2. Record a trace while you play the mechanic for about 30 seconds (see `ue-insights-profiling/docs/capture.md`).
3. Ask the assistant to analyze the trace.
4. Read the report. It tells you the biggest costs and what to check next.

---

## No skill support? Use it without an AI

All tools are plain Python scripts. Run them from your Unreal project folder:

```
python <skill>/scripts/ue_env.py --project .
python <skill>/scripts/audit_scopes.py --project .
python <skill>/scripts/trace_report.py overview --trace Saved/Profiling/my.utrace
python <skill>/scripts/trace_report.py cost     --trace Saved/Profiling/my.utrace
python <skill>/scripts/trace_report.py hitches  --trace Saved/Profiling/my.utrace
```

| Command | What it tells you |
|---|---|
| `ue_env.py` | Finds your project, engine, and recent traces |
| `audit_scopes.py` | Checks the profiling marks in your source code |
| `trace_report.py overview` | Frame times and how many hitches there are |
| `trace_report.py cost` | Where the time of each frame goes |
| `trace_report.py scopes` | What your own marks cost |
| `trace_report.py hitches` | The slowest frames and their causes |
| `trace_report.py compare` | Two traces side by side |

**Chat assistant without file access?** Open `ue-insights-profiling/PROMPTS.md`, paste a prompt, and attach
`SKILL.md` and the docs file it names. Then paste the script output the assistant asks for.

---

## Good to know

- **Trace from the editor vs. a game build.** A trace from the editor also contains the cost of the editor window.
  For the most honest numbers, record with `-game` (see `docs/capture.md`).
- **Blueprint.** Marks work in C++ only. Logic that exists only in Blueprint cannot be marked.
- **Shipping builds.** All marks are removed in Shipping builds, so they cost nothing there. Record traces with a Development build.
- **Version control.** The assistant follows your project rules. With Perforce it runs `p4 edit` before changing a file.
  It never submits your changes.
- **The editor must be closed to build.** The assistant will not close it for you. It will ask.

---

## What is inside

| Path | What |
|---|---|
| `ue-insights-profiling/SKILL.md` | The instructions for the assistant |
| `ue-insights-profiling/docs/` | How to place marks, how to read results, how to record a trace |
| `ue-insights-profiling/scripts/` | The three Python tools |
| `ue-insights-profiling/templates/` | A starter header for projects that have no profiling macros yet |
| `ue-insights-profiling/PROMPTS.md` | Ready-made prompts for chat assistants |

---

## Troubleshooting

| Problem | What to do |
|---|---|
| The assistant does not find the skill | Check that the folder is named `ue-insights-profiling` and is in your tool's skills folder. Or say: "Read `<path>/SKILL.md` and follow it." |
| `python` is not found | Install Python 3.8+, or try `py -3` or `python3`. |
| The analysis finds no CSV or fails | Make sure `UnrealInsights.exe` exists in your engine folder and the trace is not open in Insights. |
| Your marks are missing from the trace | Rebuild the editor and record again. Make sure the `cpu` channel is on (the `default` setting includes it). |
| The build fails | The assistant explains the error. The usual causes are a missing `#include` or two marks on one line. |
