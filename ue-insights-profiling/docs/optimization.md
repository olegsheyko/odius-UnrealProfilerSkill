# How to suggest fixes for the problems you found

Use this after the trace analysis, when you can read the project's source code.

## Rules

1. **Only fix what the trace showed.** Every suggestion must point to a number from the report
   (for example "`PaintStirGuide/Project` = 1.48 ms per frame, 242 calls per frame"). No guessing, no general advice.
2. **Read the code first.** Run `trace_report.py locate`, open the files it lists, and read the whole function
   (and the code that calls it) before you suggest anything. The file list is only a list of candidates.
3. **Do not change files unless the user asks.** Suggest first. End with a question: "Which of these should I apply?"
4. **Rank by value.** Order the suggestions by (ms per frame you can save) divided by (effort). Steady per-frame costs
   come first. Repeated hitches come next. One-time hitches come last.
5. **Be honest about the gain.** Give a rough estimate and say it is an estimate. Say how to check it.
6. **Do not blame the project for engine or editor costs.** If the cost is in the engine, the OS or the editor, say so,
   and suggest how to confirm it (a standalone trace). Only suggest a fix if there is a real option (a setting, or a way to call the engine less).

## Format for each suggestion

```
### N. <short title>  (priority: high / medium / low)
Problem:  <timer name> = <number> (<share of the frame>), seen in <where in the trace>.
Where:    <file>:<line>  <function>
Why:      <what the code does that makes it slow, from reading the code>
Fix:      <the concrete change, in 1-4 steps; a small code sketch if it helps>
Gain:     about <X> ms per frame (estimate). Risk: low / medium / high. Effort: small / medium / large.
Check:    record the same scenario again and run `trace_report.py compare`; <timer> should drop to about <Y>.
```

After the list, ask which ones to apply. If the user says yes, change the code, keep the profiling marks, build, and
ask for a new trace to compare.

## Common problems and fixes

Use this as a list of ideas. Only use an item if the trace and the code agree.

| What the trace shows | Common causes in code | Fixes to consider |
|---|---|---|
| A mark with a huge call count per frame (hundreds) | A function called inside a loop; the same math repeated (for example a world-to-screen projection for every point) | Compute shared data once per frame (camera matrix) and reuse it. Use fewer points or steps. Cache results that do not change until the camera or the actor moves. |
| `NativePaint`, `OnPaint` or widget `NativeTick` is expensive | Heavy math or many draw calls in paint; paint runs every frame | Move math out of paint and cache it. Reduce draw elements. Update only when data changes. |
| `Slate_PaintSlowPath`, `Slate::Prepass`, `SInvalidationPanel Uncached` are large | Many widgets, widgets that change every frame, hidden widgets that still take layout, property bindings that run every frame | Use Collapsed instead of Hidden. Use event-driven updates instead of bindings. Group static UI in an Invalidation Box or Retainer Box. Reduce the number of widgets. Confirm with a standalone trace (in PIE this also contains the editor UI). |
| A component or actor `Tick` is expensive, or ticks when idle | Work that runs every frame even when nothing happens | Early return when idle. Turn the tick off when not needed (`SetComponentTickEnabled`). Set a `TickInterval`. Use events, timers or delegates instead of polling. |
| `LoadObject`, `LoadClass`, `LoadSynchronous`, `StaticLoadObject` in a hitch | Loading an asset on the game thread at the moment of use | Use soft references and async loading (`FStreamableManager`). Preload at level start or `BeginPlay`. Cache the loaded class. |
| `SpawnActor`, `NewObject`, `CreateWidget`, `RegisterComponent`, `CreateAndSetMaterialInstanceDynamic` costs, or garbage collection (`PerformReachabilityAnalysis...`) | Creating and destroying many objects at runtime | Reuse objects (a pool). Create once and show or hide. Cache dynamic materials. Avoid `NewObject` in `Tick`. |
| `Tick_Core` is large | An `FTSTicker` delegate (voice, session, watermark, EOS, Steam, HTTP) does slow or blocking work | Add marks inside each delegate to find the slow one. Raise the delegate interval. Move blocking calls (opening audio devices, network, file access) to a background thread or retry less often. |
| Line traces, overlaps or `TActorIterator` loops are expensive | Searching the world every frame | Cache the result. Run it less often. Limit the count per frame. Use a tighter collision channel or shape. |
| Replication functions cost a lot, or `ForceNetUpdate` is called every frame | Sending data that did not change | Send only on change. Lower the net update frequency. Use dormancy. |
| `CharacterMesh0` or other animation tasks on workers are large | Many animated characters, high update rate | Use update rate optimization and LOD. Do not tick animation when the mesh is not visible. |
| GPU: `TemporalSuperResolution`, `VirtualShadowMap*`, `ShadowProjection*`, `Nanite*`, `FXSystemPreRender` | Quality settings and content cost | Lower the screen percentage or the AA quality (`r.ScreenPercentage`, `sg.AntiAliasingQuality`). Reduce shadow-casting lights and shadow quality. Check Niagara particle counts and GPU simulations. Use scalability settings. |
| `WinPumpMessages`, a console command, editor-only timers | The OS, the editor or the recording itself | Not a game problem. Confirm with a standalone trace and ignore it. |
| A big Excl with no children, or `Oversubscription` | The code is not marked, or a thread is blocked | Add marks inside the function and record again. Record the `contextswitch` channel to see why a thread waits. |

## After the fix

1. Build and record the same scenario again (same map, same actions, same length).
2. Run `trace_report.py compare --trace NEW --baseline OLD`. The target timer should drop, and nothing new should rise.
3. Report the result in numbers: before, after, and the change in ms per frame.
