# How to add profiling marks to code

## How the macros work (UE 5.4 to 5.7, checked in the 5.7 source)

Engine file: `Engine/Source/Runtime/Core/Public/ProfilingDebugging/CpuProfilerTrace.h`.
Before you use this in another engine version, search the engine headers for these names:
`TRACE_CPUPROFILER_EVENT_SCOPE_STR`, `TRACE_CPUPROFILER_EVENT_SCOPE_TEXT`, `TRACE_BOOKMARK`, `TRACE_COUNTER_SET`.

| Macro | What it does |
|---|---|
| `TRACE_CPUPROFILER_EVENT_SCOPE_STR("Name")` | Measures the time until the end of the block. The name is saved once in a `static uint32` (the variable name uses `__LINE__`). After that, only a small id is written. The name must be a string literal. |
| `TRACE_CPUPROFILER_EVENT_SCOPE_TEXT(Text)` | Same, but the name is built at run time (`FString`, `FName`, `TCHAR*`). It costs more. Use it only if the name carries useful information. |
| `TRACE_BOOKMARK(TEXT("fmt %d"), V)` | Draws a vertical line on the timeline. Use it for one-time events. |
| `TRACE_DECLARE_INT_COUNTER(Var, TEXT("Group/Name"))` in a .cpp file, then `TRACE_COUNTER_SET(Var, N)` | Draws a number over time in the Counters tab (for example, the number of actors). |

In Shipping builds (or when `UE_TRACE_ENABLED=0`) all of these macros become empty, so they cost nothing.
The `cpu` channel must be on while you record (it is part of the `default` preset).

Project wrappers: run `ue_env.py` and look at `profiling_header` and `profiling_macros`. The wrapper joins two string
literals (`"MP/" Name`), so the name stays a literal.

## Names

`<Prefix>/<Mechanic>/<Function>[/<Phase>]`, for example `MP/Cauldron/Tick/ServerSimulation`.
- Mechanic: the class or system name without the `A` or `U` prefix (`Fermenter`, `Cauldron`, `BeerInteractionWidget`).
- Every name must be unique in the whole project (`audit_scopes.py` checks this).
- Phase names the action: `LoadClass`, `SpawnActor`, `Project`, `MakeLines`.

## What to mark (most important first)

1. Code that runs every frame: `Tick`, `TickComponent`, `NativeTick`, `NativePaint`, `FTSTicker` delegates, subsystem `Tick`.
2. Known causes of hitches: synchronous loads (`LoadObject`, `LoadClass`, `LoadSynchronous`, `StaticLoadObject`),
   `SpawnActor`, `NewObject`, `CreateWidget`, `RegisterComponent`, `CreateAndSetMaterialInstanceDynamic`.
3. Heavy parts inside Tick: loops over actors (`TActorIterator`), line traces and overlap queries, world-to-screen
   projections, math over big arrays, string work.
4. Events: `OnRep_*`, RPC `_Implementation` functions, delegates, timer callbacks, the end of a process (use a bookmark).
5. UI: `NativePaint`, `NativeConstruct`, updates of text and widgets.

Do not mark: getters and setters, functions shorter than about 1 microsecond, functions that are only called from a
parent you already mark, Blueprint callbacks without a C++ wrapper, and editor-only code (`WITH_EDITOR`) unless you
profile the editor.

## Patterns

A whole function:
```cpp
void AFermenter::Tick(float Dt)
{
    MP_SCOPE("Fermenter/Tick");
    Super::Tick(Dt);
    ...
}
```
A phase inside a function. The `{ }` block ends the measurement. Declare the result variable before the block:
```cpp
UClass* BeerClass = nullptr;
{
    // [Profiling] Synchronous class load: a hitch candidate on the first dispense.
    MP_SCOPE("Fermenter/SpawnBeer/LoadClass");
    BeerClass = LoadClass<AActor>(nullptr, *Path);
}
```
Code after an early `return`. Put the scope after the checks if you only want to measure the "real work" branch.
Then clients that return early do not write a measurement:
```cpp
if (!Owner->HasAuthority()) return;
// [Profiling] Server-only simulation (runs every frame on authority).
MP_SCOPE("Cauldron/Tick/ServerSimulation");
```
A lambda that is called many times: a scope inside the lambda works. If it runs more than about 100 times per frame,
keep it only while you investigate, and add a comment. The goal is to read the call count per frame:
```cpp
auto Project = [&](...) {
    // [Profiling] Called ~300x per paint. Read Count/Incl in Insights, then decide.
    MP_SCOPE("BeerInteractionWidget/PaintStirGuide/Project");
```
`const` functions can have a scope. If several `Update*()` calls are on one line, put each on its own line and in its own block.

A bookmark and a counter:
```cpp
MP_BOOKMARK(TEXT("Fermenter: fermentation finished"));
// at the top of the .cpp file:  TRACE_DECLARE_INT_COUNTER(GActiveEffects, TEXT("MP/ActiveEffects"));
TRACE_COUNTER_SET(GActiveEffects, ActiveEffects.Num());
```

## Comments

Format: `// [Profiling] <what the scope isolates / why / how often>`.
- Inner scopes (phases, loads, lambdas): a comment is required.
- The scope at the start of a function: add a comment only if the thread (GameThread, Render, Worker) or the
  frequency (every frame, or on an event) is not obvious, or if it is an `FTSTicker` delegate.
- Use the same language and style as the code around it.
- Do not write a comment that only repeats the name.

## What not to do

- Do not change logic, call order, signatures, `UPROPERTY` or `UFUNCTION`.
- Do not put a scope in a `.h` file inside an inline function.
- Do not use `SCOPE_CYCLE_COUNTER` or `DECLARE_CYCLE_STAT` instead. They only show up when the `stats` channel is on.
- Do not wrap a `Super::` call in its own scope without a reason.
- Do not use `MP_SCOPE_DYNAMIC` in hot loops.
- Never put two scopes on the same source line.

## Threads and network

- A scope is written on the thread that runs the code. Workers and render commands show on their own tracks
  (`Foreground Worker`, `RenderThread`). For async tasks, put the scope inside the task lambda.
- On a listen server the server and client code run in the same process. Check `HasAuthority()` in the code,
  not the scope name.
- Each PIE client in multi-process mode is a separate process and writes its own trace.

## Blueprint

C++ macros do not work inside Blueprint graphs. If a mechanic lives in Blueprint:
1. Mark the C++ base classes and the places where C++ calls the Blueprint.
2. Blueprint functions and events already show in the trace (in the editor whenever `cpu` is on; elsewhere with "Stat Named Events") (see `capture.md` and `analysis.md`).
3. To measure a part INSIDE a Blueprint function, use the Blueprint profiling nodes (Begin/End Profile Scope, Begin/End Profile
   Region, Profile Bookmark). See `blueprint.md` and Job D in `SKILL.md`.
4. For very hot Blueprint logic, consider moving it to C++.

## Check your work

1. `audit_scopes.py` reports no problems.
2. The Development Editor builds without errors (close the editor first).
3. Record a short trace and run `trace_report.py scopes`. The new scopes must be there with Count > 0.
   Count = 0 means the code did not run in your test.
