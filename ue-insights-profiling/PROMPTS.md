# Ready-to-paste prompts

For assistants that cannot read the repository or run commands. Attach `SKILL.md` and the `docs/*.md` file
named in the prompt. Replace the text in `[brackets]`.

## 1. Instrument a mechanic

```
You are helping me add Unreal Insights profiling scopes to an Unreal Engine C++ project.
Follow the attached SKILL.md (Job A) and docs/instrumentation.md exactly.
Mechanic to instrument: [e.g. the Fermenter and everything it calls per frame].
Below are the source files (full contents). Profiling macro header: [paste MPProfiling.h, or say "none, create one from the template"].
Return, for every file, the complete modified function(s) with scopes and "// [Profiling]" comments,
then a table: scope name | what it measures | how often it runs.
Do not change behavior. Do not rename or reorder anything else.
[paste files]
```

## 2. Analyze a trace

```
You are analyzing an Unreal Insights trace. Follow the attached SKILL.md (Job B) and docs/analysis.md.
Below is the output of trace_report.py for these modes: [overview / cost / scopes / hitches].
Goal: [find what costs FPS in normal play / explain the hitches / compare before and after].
Answer with: one-sentence conclusion, a table of the top costs in ms/frame (ours / UI / engine / editor / GPU),
the hitches by type, caveats (editor vs standalone, window length) and what to measure next.
Use only numbers from the output; mark everything else as a hypothesis. Do not propose code changes unless I ask.
[paste script output]
```

## 3. Which command should I run?

```
I have an Unreal Insights trace at [path] and I want to know [question].
Follow SKILL.md and tell me the exact trace_report.py commands to run, in order, one per code block.
I will paste the output back.
```

## 4. Review my instrumentation

```
Review the profiling scopes I added against docs/instrumentation.md: naming, placement, comments, hot-loop cost,
same-line collisions, scopes in headers, variables declared inside scope blocks. Here is the diff / files and the
output of audit_scopes.py: [paste]
```

## 5. Suggest fixes for what the trace found

```
Follow the attached SKILL.md (Job B, step 5) and docs/optimization.md.
Here is the analysis report and the output of `trace_report.py locate`: [paste both]
Here are the source files behind the biggest costs: [paste files, or attach the project folder].
Suggest fixes only for the problems in the report, in the format from optimization.md
(problem with number, file and line, why it is slow, fix, estimated gain, risk, how to check).
Rank them by value. Do not change any code until I choose.
If I did not give you the source files, ask me for them first and name the files you need.
```

## 6. How do I record the trace?

```
Using docs/capture.md, give me the exact command to record a trace of [map / scenario] for this project in
[standalone / editor], and the steps to perform during recording. Engine path: [path]. Project: [path].
```
