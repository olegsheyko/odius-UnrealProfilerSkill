# How to analyze a trace

## Rules to follow

1. The goal is to find the costly operations that lower FPS in normal play. It is not only about big hitches.
   The main mode is `cost`. The `hitches` mode is a helper.
2. Tell **work** and **waiting** apart. A bar named `Wait*` means the thread is doing nothing.
   Look for the reason on another thread at the same time.
3. Tell **Incl** and **Excl** apart. Incl is the whole time including inner calls. Excl is the time of the timer itself.
   A big Excl with tiny inner calls means one of three things: the body is expensive, the thread was blocked
   or paused by the OS, or the code is not marked yet.
4. Back every conclusion with a number from the scripts. If something is not proven, call it a hypothesis and say how to test it.
5. The editor (PIE) changes the numbers. See the section below.

## How the script counts

- Data source: `TimingInsights.ExportTimingEvents`. Columns: `ThreadName,TimerName,StartTime,Duration,Depth` (in seconds).
  Do NOT use `ExportTimerStatistics` for numbers per thread: in UE 5.7 it ignores `-threads`.
- One frame = one `FEngineLoop::Tick` event on the GameThread.
  **Active time** = frame length minus `FEngineLoop_UpdateTimeAndHandleMaxTickRate`
  (the sleep of the frame limiter, or the slow-down when the editor is in the background).
  Frames where this sleep is longer than 100 ms are "editor in background" frames. They are not hitches.
- The default `cost` window is the longest stretch of frames without such sleeps.
- Excl is calculated from `Depth`: the event length minus the sum of its direct children.
- These are not counted as work: names with `Wait`, and the wrappers `Frame`, `FEngineLoop::Tick`,
  `RenderGraphExecute`, `Oversubscription`, `GameThreadWaitForTask`, `TaskWorkerIsLookingForWork`,
  `ExecuteForegroundTask`, `ExecuteBackgroundTask`.
- Excl on GPU tracks can include waiting for the queue. For the GPU, look at the real passes, not at the wrappers.
- A space or a non-English letter in the output path breaks the Insights parser. The script uses a short ASCII folder instead.

## Modes

| Mode | When to use it | What you get |
|---|---|---|
| `overview` | Always first | Frames, p95/p99, number of background frames, number of hitches, best windows |
| `cost` | "What costs FPS?" | ms per frame by thread (GameThread, RenderThread, RHIThread, GPU0-*, Workers), calls per frame, your scopes |
| `scopes` | "What do our mechanics cost?" | For each scope: total, ms per frame, calls, average, max over the whole trace |
| `hitches` | Stutters | For each hitch: the main timer, a label for the cause, your share |
| `compare` | Before and after a change | The biggest changes in ms per frame, by timer |

## How to draw conclusions

- **What limits the frame:** compare the busy time of the GameThread, the RenderThread and the GPU.
  If the GameThread busy time is close to the ms per frame, the game thread limits the frame.
  If the GPU busy time is close, the GPU limits it. This is an estimate from sums, so say "probably".
- **Share of the frame:** ms per frame divided by (1000 / FPS). Budgets: 16.7 ms at 60 FPS, 33.3 ms at 30 FPS.
- **Ours or not ours:** a scope with the project prefix is ours. `Slate*`, `UMG`, `WBP_*` are UI
  (partly the game, and in PIE also the editor). `Tick_Core`, `WinPumpMessages`, `ZenHttp_*`, EOS and Steam are engine and platform.
- If the sum of our scopes in a hitch is about 0, the hitch is not from marked code.
  Name the main timer and suggest where to add scopes.

## Timer reference

| Timer | Meaning |
|---|---|
| `FEngineLoop_UpdateTimeAndHandleMaxTickRate` | The sleep of the FPS limiter. An editor in the background shows about 300 ms. |
| `WinPumpMessages` | Windows messages: input, console, window focus. Typing `Trace.Start` can cost 100+ ms. |
| `Tick_Core` | `FTSTicker::GetCoreTicker()`: all `FTSTicker` delegates (voice, watermark, session), HTTP, EOS, Steam. Big Excl without children means the delegates are not marked. |
| `Tick_Engine`, `UWorld_Tick` | World and actor ticks. Components show by class name (for example `NetworkGrabSync`). |
| `Slate::Prepass`, `Slate_PaintSlowPath`, `Slate::DrawWindows` | UI layout and painting. In PIE they also include the editor's own UI. |
| `SInvalidationPanel Uncached` | UI without invalidation cache. More expensive. |
| `GameThreadWaitForTask`, `WaitForTasks`, `ProcessUntilTasksComplete`, `TickCompletionEvents` | The game thread waits for tasks (animation `CharacterMesh0`, physics, rendering). |
| `Oversubscription` (on a worker) | A worker is blocked, so the pool starts extra threads. |
| `CharacterMesh0` (on a Foreground Worker) | The animation task of a skeletal mesh. |
| `PerformReachabilityAnalysisOnObjectsInternal`, `*GarbageCollect*` | Garbage collection: many UObjects are created or destroyed. |
| `TemporalSuperResolution`, `SceneRender`, `Nanite::*`, `VirtualShadowMap*`, `ShadowProjection*`, `FXSystemPreRender` | GPU: TSR, scene, Nanite, shadows, Niagara. |
| `RHI_Finalize`, `D3D12_Present`, `CreateCommittedResource` | RHI and driver. |
| `ZenHttp_CurlPerform` | Zen/DDC network, usually in the background. |
| `UAssetRegistryImpl::GetAssets` | Asset query. In game code this is suspicious. |
| `FileSystemCacheStoreMaintainer`, `FBaseShaderFormat_*`, `ShaderJobTask` | Cache upkeep and shaders, in the background. |

## PIE versus Standalone

A trace from PIE contains the editor UI, extra viewports, PIE overhead, and the slow-down when the window loses focus.
Confirm conclusions about Slate and rendering with a trace from `-game`. Numbers for your own scopes (gameplay CPU
cost) from PIE are mostly fine.

## Report format

1. A conclusion in one or two sentences ("The frame is limited by the GameThread. Our biggest cost X is N ms per frame.").
2. A table of the 5 to 10 biggest costs: ms per frame, calls per frame, share of the frame, who owns it.
3. Hitches: how many real ones, by type, which are ours.
4. Warnings: the source (PIE or Standalone), the window length, the number of frames, hypotheses.
5. Next steps: what to measure, where to add scopes, what to record. Change code only if asked.

## Manual exports (for a custom view)

```
UnrealInsights.exe -OpenTraceFile="X.utrace" -AutoQuit -NoUI -ExecOnAnalysisCompleteCmd="TimingInsights.ExportTimingEvents C:\out\e.csv -columns=ThreadName,TimerName,StartTime,Duration,Depth -threads=GameThread -timers=MP/* -startTime=10 -endTime=20" -log
```
Commands: `ExportThreads`, `ExportTimers`, `ExportTimingEvents`, `ExportTimerStatistics` (not per thread),
`ExportTimerCallees`, `ExportCounters`. The `-threads` and `-timers` filters take comma lists and `*`.
In PowerShell, start the program with `&`.
