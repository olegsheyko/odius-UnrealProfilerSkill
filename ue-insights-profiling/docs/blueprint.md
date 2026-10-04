# Profiling inside Blueprints

For people who build logic in Blueprint (AI, State Tree, widgets, gameplay) and do not write C++.

## The problem

With the `cpu` channel on (see `capture.md`), the trace shows every Blueprint function and event, but an Event Graph
is one block (`ExecuteUbergraph_...`). You cannot see which part of the graph is slow.

The fix: put profiling nodes inside the graph, around the part you want to measure.

## The nodes (category "Profiling")

| Node | Use it for | Rules |
|---|---|---|
| **Begin Profile Scope** (Name) -> Handle | A short timed part of one function or event | Must end in the same frame. Call **End Profile Scope** on **every** path out of the marked part. |
| **End Profile Scope** (Handle) | Ends the scope | Pass the Handle from Begin. |
| **Begin Profile Region** (Name) -> Handle | Work that lasts several frames (a latent State Tree task, `Delay`, a long AI action) | Safe if End is missed. Shows in the Regions track. |
| **End Profile Region** (Handle) | Ends the region | Pass the Handle from Begin. |
| **Profile Bookmark** (Text) | One-time events ("order created", "guest left") | No End needed. |

All nodes are **Development only**: they are removed from Shipping builds, so they cost nothing there.
In the trace the names get a prefix: `MP/BP/<Name>`. Use the Timers search `MP/BP/` to find them.

> The node library comes from the C++ project (`UMPProfilingBlueprintLibrary`). If you do not see the nodes,
> ask a C++ developer to add and build it (see `SKILL.md`, Job D).

## How to use a Scope (step by step)

1. In your function or event graph, add **Begin Profile Scope**. Type a short name, for example `GenerateOrder.PickRecipe`.
2. Connect it right before the nodes you want to measure.
3. Keep the **Handle** output (promote it to a local variable if the End is far away).
4. Add **End Profile Scope** after the last node of that part and connect the same Handle.
5. If your graph has branches, `Return` nodes or loops that can leave the marked part, add an End on each of those paths.

```
[Event]  ->  Begin Profile Scope ("PickRecipe")  ->  (your nodes)  ->  End Profile Scope  ->  (rest)
```

## Choosing Scope or Region

- The marked part runs and finishes within one frame, with no `Delay` or latent node inside: use a **Scope**.
- The marked part waits (Delay, latent task, timer, several frames): use a **Region**.
- You only want to see "this happened here": use a **Bookmark**.

## Rules that keep the trace correct

1. **Every Begin needs an End on every path.** A missing End on a Scope breaks the nesting of the timeline for that frame.
   The library closes forgotten scopes at the end of the frame and prints a warning in the Output Log:
   `Profile Scope '<name>' was never ended ...`. If you see this, find the path without End.
2. **Never keep a Scope open across a `Delay` or a latent node.** Use a Region.
3. **Do not put Scopes in loops that run hundreds of times per frame.** Put one Scope around the whole loop.
4. **Use clear names.** `Mechanic.Part`, for example `Guest.GenerateOrder.LoadTable`. Names are `FName`s, so they are cheap.
5. **Nesting is fine.** A Scope inside another Scope works. End them in reverse order (inner first).
6. **Blueprint thread-safe animation graphs** run on worker threads. The nodes only work on the game thread. Outside it they do nothing.

## The `BeginProfileScope` bar

The engine wraps every Blueprint function call in its own timer event (in the editor, whenever the `cpu` channel is on). So in the timeline
you will see a long `BeginProfileScope` bar around your scope, with `MP/BP/<Name>` inside it, and tiny `(scope begin)` and
`EndProfileScope` bars. This is normal. **Read the time from `MP/BP/<Name>`** and ignore `BeginProfileScope`.
(The library counts these engine events so that `MP/BP/<Name>` measures only your marked part. If `MP/BP/<Name>` shows
about 0 µs while `BeginProfileScope` is long, the project has an old version of the nodes: update and rebuild.)

## What you see in Insights

- Scopes: in the Timers panel and the timeline, as `MP/BP/<Name>`, with Count, Incl and Excl like any other mark.
- Regions: in the **Regions** track of the timeline.
- Bookmarks: as vertical lines with your text.

Blueprint function names around your marks show up automatically in the editor. In other builds also tick **Stat Named Events**.

## Example: finding the slow part of a function

A hitch shows `ExecuteUbergraph_BPC_GuestOrder` taking 20 ms. Inside, you suspect the data table lookup.

1. Put **Begin Profile Scope** ("GuestOrder.TableLookup") before the lookup nodes and **End Profile Scope** after them.
2. Record again and search for `MP/BP/GuestOrder`.
3. If `TableLookup` is about 20 ms, the lookup is the problem. If it is tiny, move the scope to the next part.
4. When you are done, remove the nodes, or keep them if they are cheap. Check them with `audit_scopes.py`-style review
   so that every Begin still has an End.

## Troubleshooting

| Problem | What to do |
|---|---|
| The nodes are not in the node list | Search for "Profile". If missing, the C++ library is not in the project or the project is not rebuilt. |
| `MP/BP/...` is missing in the trace | The `cpu` channel was off, or the code never ran. The nodes record only while a trace is running. |
| Warning "was never ended" in the log | A path leaves the marked part without End. Add an End on that path. |
| The timeline looks wrong in one frame | A Scope was left open. Fix the missing End. |
| Nothing happens in Shipping | Expected. The nodes are Development only. |
