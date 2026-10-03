---
name: ue-insights-profiling
description: Unreal Insights profiling for Unreal Engine C++ projects - add trace marks (scopes) to mechanics, analyze .utrace files without the Insights UI, find the source files behind the costs and suggest fixes. Use for any request about profiling, Unreal Insights, trace files, hitches, stutter, frame time, what costs FPS, optimizing performance, or adding measurements to a mechanic. Also use for Russian requests - профилирование, профилировщик, трассировка, трейс, разметь механику, добавь замеры, ФПС, просадки, хитч, фриз, что тратит кадр, почему тормозит.
---

# Unreal Insights profiling

This file is a full set of instructions. It works with any AI assistant or agent. A person can follow it too.
Paths below are relative to THIS skill folder (the folder that contains this file). Call it `<skill>`.
Run every command with the Unreal project root as the working directory, or add `--project <path to the project>`.

There are two jobs: **INSTRUMENT** (add profiling marks to code) and **ANALYZE** (read a `.utrace` file).
Never change how the game behaves. Marks only add measurements.

## How to run commands

- **You can use a terminal:** run the commands yourself and read the output.
- **You only have a chat:** show the exact command, ask the user to run it and paste the output, then continue.
  The scripts print plain text for this reason. If you need a file, ask the user to paste it (give the file path).

## Step 0: learn the environment (always do this first)

1. Run `python <skill>/scripts/ue_env.py --project .`
   It prints the `.uproject`, the engine folder, `Build.bat`, `UnrealInsights.exe`, the game modules, the profiling
   header if one exists (`profiling_header`, with its macros and `profiling_prefix`), recent `.utrace` files,
   whether the editor is running, and the version control system.
   If `python` is missing, try `py -3` or `python3`.
2. If the project has a rules file (`README`, `AGENTS.md`, `CONTRIBUTING`, or an assistant rules file), read it and
   follow its version control and build rules.

## Job A: INSTRUMENT a mechanic

Input: the developer names a mechanic, class, file or system. Example: "instrument Fermenter" or "the whole inventory".

1. **Find the code.** Search for the class and function names. Read the files fully. If the request is unclear, or it
   touches more than about 10 files, list the files you found and ask before you edit.
2. **Macro header.** If `profiling_header` exists, use its macros and prefix. If not, create one from
   `<skill>/templates/Profiling.h.template`. Replace `__PROJECT__`, `__PREFIX__` and `__PFX__` with a short project
   prefix (for example `MP`). Put it in the main game module. You do not need to change `Build.cs`.
3. **Read `<skill>/docs/instrumentation.md` before you edit.** It explains the macros, names, what to mark, patterns and mistakes.
4. **Rules for editing:**
   - Scope name: `Mechanic/Function[/Phase]`. It must be a string literal and unique in the project.
   - Put the scope on the first line of the function. Put inner phases in their own `{ }` block.
   - Never put two scopes on one source line (the id is built from `__LINE__`).
   - Add `// [Profiling] <what it measures / why / how often>` above every inner scope. For the scope at the start of
     a function, add a comment only if the thread or the frequency is not obvious. Use the same language and style as the code around it.
   - Use bookmarks only for one-time events. Never use them in `Tick`.
   - Mark: ticks, timers and delegates, RPC and OnRep functions, widget paint and tick, `FTSTicker` delegates,
     spawns and `NewObject`, synchronous loads (`LoadObject`, `LoadClass`, `LoadSynchronous`), loops over actors,
     traces and overlaps, heavy math. Do not mark small getters or code that runs thousands of times per frame for no reason.
5. **Version control.** Follow the project rules. With Perforce: run `p4 edit <file>` before you change a tracked file
   (files are read-only until then), and `p4 add` for new files. Do not remove the read-only flag by hand.
   Do not run `p4 submit`, `revert`, `shelve` or `obliterate`. The human does that.
6. **Check your work:**
   - `python <skill>/scripts/audit_scopes.py --project .` finds duplicate names, two scopes on one line, and bad names.
     It exits with code 1 if it finds problems.
   - Build the editor target: `<build_bat> <Target>Editor Win64 Development -Project=<uproject> -WaitMutex -NoHotReload`.
     If `editor_running` is true, do NOT kill the process. Ask the user to close the editor (or to build with Live Coding).
7. **Report:** give a table with `scope -> what it measures -> how often it runs`. Say how to record a trace
   (`<skill>/docs/capture.md`) and what to look for in Insights. Do not optimize anything unless asked.

## Job B: ANALYZE a trace

Input: a `.utrace` path, or "analyze the latest trace" (use `recent_traces[0]` from step 0).

1. Run `python <skill>/scripts/trace_report.py overview --trace <file>`.
2. Pick the mode that fits the question:
   - What costs FPS, or where the frame time goes: `cost` (automatic window, or `--from S --to S`).
   - What our mechanics cost: `scopes` (the prefix is found automatically, or use `--prefix X/`).
   - Stutters and freezes: `hitches --threshold 40 --top 10`.
   - Before and after a change: `compare --trace NEW --baseline OLD`.
3. **Read `<skill>/docs/analysis.md`** to understand the results: work versus waiting, engine timers, editor (PIE) warnings, report format.
4. **Write the report:** a short conclusion; a table of the biggest costs in ms per frame; a split into ours, UI,
   engine, editor and GPU; warnings (PIE or Standalone, window length); and what to measure next. Take numbers only
   from the script output. Call everything else a hypothesis and say how to test it. Do not change code unless asked.
5. **Connect the report to the code (always do this after the report).** Check whether you can read the project's
   source: step 0 found a `.uproject` and a `Source` folder, or you can open the files the user attached.
   - **Project connected:**
     1. Run `python <skill>/scripts/trace_report.py locate --trace <file>`. It maps the biggest costs and the hitch
        causes to source files and lines. To check one cost, add `--timers NAME [NAME ...]`.
     2. Open the candidate files and read the whole functions (and their callers).
     3. **Read `<skill>/docs/optimization.md`.** Write suggestions only for the problems the analysis found, in the
        format of that file: problem with its number, file and line, why it is slow, the fix, the estimated gain, the risk,
        and how to check it. Rank them by value. Say clearly which costs belong to the engine or the editor and have no project fix.
     4. Do not edit code. End by asking which suggestions the user wants you to apply.
   - **Project NOT connected** (the script prints `PROJECT_NOT_CONNECTED`, or you cannot read any project files):
     stop after the report and ask the user, in the same message, using words like these:
     "To suggest fixes I need to read the code. Please connect or attach the Unreal project folder (at least `Source/`,
     and `Config/` if possible), then tell me and I will continue." If the chat cannot connect folders, ask the user
     to paste the files behind the biggest costs, and name them if you can (for example the class names in the trace,
     such as `NetworkGrabSync` means `NetworkGrabSyncComponent.cpp`).
6. **After the user applies a fix:** ask for a new trace of the same scenario and run `compare` (see `optimization.md`).

Do not use `ExportTimerStatistics` for numbers per thread. In UE 5.7 it ignores `-threads`. The scripts use `ExportTimingEvents`.

## Job C: help record a trace

Give the commands from `<skill>/docs/capture.md`. For honest numbers: use Standalone or `-game`, the Development
configuration, no debugger, and keep the game window in focus.

## Limits (tell the user when they apply)

- Logic that exists only in Blueprint cannot be marked with C++ macros. Mark the C++ parts, or move hot code to C++.
- Shipping builds remove all marks. You need a Development or Test build to get traces.
- A trace from the editor also contains the cost of the editor's own UI.
- The trace tail buffer adds a few seconds from before the start command.

## If something does not work

- The export makes no CSV file: the path may have spaces or non-English letters (the script tries a short path),
  `UnrealInsights.exe` may be missing, or Insights may have the same trace open.
- There are no project scopes in the trace: the `cpu` channel was off, or the build has no marks.
  Run `audit_scopes.py` and rebuild the editor.
- The build fails: look for a missing `#include` of the macro header, two scopes on one line, a variable declared
  inside a scope block but used after it (declare it before the block), or a scope in a `.h` file.
