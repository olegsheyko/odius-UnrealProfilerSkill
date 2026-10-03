# How to record a trace

## Best way: start the game with tracing on (records from the first frame)

Standalone game (no editor UI, the most honest numbers):
```
"<Engine>\Engine\Binaries\Win64\UnrealEditor.exe" "<Project>.uproject" /Game/Path/To/Map -game -windowed -ResX=1280 -ResY=720 -trace=default,counters,bookmark -tracefile="<Project>\Saved\Profiling\name.utrace"
```
- The folder `Saved\Profiling` must already exist.
- A path without spaces and without non-English letters is easier for the export tools. The scripts work around
  this, but you can avoid the risk.
- Keep the game window in focus. An editor window in the background is slowed down to about 3 FPS. In the trace
  this shows up as `FEngineLoop_UpdateTimeAndHandleMaxTickRate`.
- Do not attach a debugger. Use the Development configuration.

Live view in Insights: start `UnrealInsights.exe` first. Then start the game with `-tracehost=127.0.0.1` instead of `-tracefile`.

## From an open editor

Open the console (`` ` ``). In PIE it is better to use "New Editor Window" or Standalone.
```
Trace.File default,counters,bookmark      (record to a file; Trace.Start is deprecated)
Trace.Stop
Trace.Status                              (shows where the trace goes)
Trace.Bookmark MyMarker                   (add a marker by hand)
Trace.SnapshotFile                        (save the last few seconds from memory)
```
The Trace button in the bottom right corner of the editor does the same thing.

## The tail buffer

The trace system keeps the latest events in memory. When you run `Trace.File` or `Trace.Start`, it writes this
"tail" first. So the file contains a few seconds (sometimes more) from BEFORE your command. This includes the hitch
caused by typing the command itself (`WinPumpMessages`). The log line "Trace started" shows the real start.
It is better to analyze only what comes after it. You can change the size with `-TraceTailMb`.

## Channels

`default` = `cpu,gpu,frame,log,bookmark,screenshot,region` (checked in UE 5.7, `TraceAuxiliary.cpp`).
Add `counters` if you use `TRACE_COUNTER_*`. Bookmarks are already part of `default`.
To see why a thread was waiting, add `contextswitch` (Windows, needs administrator rights).
For memory use `memory`. For loading use `loadtime`.

## A good recording plan

1. Load the map and wait 10 to 20 seconds (shaders and loads warm up).
2. Play the mechanic for 20 to 30 seconds (stir the cauldron, serve drinks, use the UI...).
   For a "what costs FPS" analysis you need one long stretch with the window in focus.
3. Stop the recording and close the game.
4. One trace = one scenario. To compare before and after, repeat exactly the same scenario.
