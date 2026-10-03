#!/usr/bin/env python3
"""Headless Unreal Insights export + analysis of a .utrace file.

  python trace_report.py overview --trace X.utrace
  python trace_report.py scopes   --trace X.utrace [--prefix MP/]
  python trace_report.py cost     --trace X.utrace [--from S --to S]   # where the frame goes, ms/frame per thread
  python trace_report.py hitches  --trace X.utrace [--threshold 40 --top 10]
  python trace_report.py compare  --trace NEW.utrace --baseline OLD.utrace [--prefix MP/]
  python trace_report.py locate   --trace X.utrace [--timers NAME ...]   # which project files are behind the costs

Common: --out DIR (default <project>/Saved/Profiling/analysis), --insights EXE, --prefix PFX.
Times in Insights CSVs are seconds; everything printed here is milliseconds.
Only uses `TimingInsights.ExportTimingEvents` / `ExportThreads` (ExportTimerStatistics ignores
the -threads filter in UE 5.7, so it is never used for per-thread numbers).
"""
import argparse, bisect, collections, csv, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_env  # noqa: E402

TICK = 'FEngineLoop::Tick'
IDLE = 'FEngineLoop_UpdateTimeAndHandleMaxTickRate'   # frame limiter / background throttle sleep
WRAPPERS = {'Frame', TICK, IDLE, 'RenderGraphExecute', 'Oversubscription', 'GameThreadWaitForTask',
            'TaskWorkerIsLookingForWork', 'ExecuteForegroundTask', 'ExecuteBackgroundTask'}
KEY_THREADS = ['GameThread', 'RenderThread 0', 'RHIThread', 'GPU0-Graphics0', 'GPU0-Compute0', 'Workers']


def is_noise(name):
    return 'Wait' in name or name in WRAPPERS


def group_of(thread):
    return 'Workers' if 'Worker' in thread else thread


def safe_dir(path):
    """Insights' command parser breaks on spaces / non-ASCII in the CSV path. Return a directory whose
    path is plain ASCII without spaces (8.3 short name, tempdir or C:\\Users\\Public fallback)."""
    import ctypes, tempfile
    def ok(p): return p.isascii() and ' ' not in p
    def short(p):
        buf = ctypes.create_unicode_buffer(1024)
        try:
            n = ctypes.windll.kernel32.GetShortPathNameW(p, buf, 1024)
            return buf.value if n else p
        except Exception:
            return p
    os.makedirs(path, exist_ok=True)
    for cand in (path, short(path), short(tempfile.gettempdir()), r'C:\Users\Public'):
        if ok(cand):
            if cand != path:
                cand = os.path.join(cand, 'ueprof_analysis'); os.makedirs(cand, exist_ok=True)
            return cand
    return path


class Insights:
    def __init__(self, trace, out_dir, exe):
        self.trace, self.out = os.path.abspath(trace), safe_dir(os.path.abspath(out_dir))
        self.exe = exe
        if not os.path.exists(self.trace):
            sys.exit(f'trace not found: {self.trace}')
        if not os.path.exists(self.exe):
            sys.exit(f'UnrealInsights.exe not found: {self.exe}')
        import re
        self.tag = re.sub(r'[^A-Za-z0-9_.-]', '_', os.path.splitext(os.path.basename(self.trace))[0])

    def export(self, name, command_tail, cmd='ExportTimingEvents'):
        """Run an export (cached by file name). Returns the CSV path."""
        path = os.path.join(self.out, f'{self.tag}__{name}.csv')
        if os.path.exists(path) and os.path.getsize(path) > 0:
            return path
        # NB: one raw command-line string so inner quotes reach UE untouched.
        qpath = path   # Insights' parser breaks on spaces: safe_dir() guarantees a plain path
        line = (f'"{self.exe}" -OpenTraceFile="{self.trace}" -AutoQuit -NoUI '
                f'-ExecOnAnalysisCompleteCmd="TimingInsights.{cmd} {qpath} {command_tail}" -log')
        subprocess.run(line, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not os.path.exists(path):
            sys.exit(f'export failed ({cmd}); try a trace/out path without spaces or non-ASCII characters.\n{line}')
        return path


def num(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if v != v or v in (float('inf'), float('-inf')) else v


def load_frames(ins):
    """Per-frame list: (start_s, active_ms, total_ms, idle_ms); active = total minus frame-limiter sleep."""
    p = ins.export('frames', f'-columns=TimerName,StartTime,Duration -threads=GameThread -timers={TICK},{IDLE}')
    ticks, idles = [], []
    for r in csv.DictReader(open(p, encoding='utf-8', errors='replace')):
        st, du = num(r['StartTime']), num(r['Duration'])
        if st is None or du is None:
            continue
        (ticks if r['TimerName'] == TICK else idles).append((st, du))
    ticks.sort(); idles.sort()
    ist = [i[0] for i in idles]
    frames = []
    for st, du in ticks:
        k, idle = bisect.bisect_left(ist, st), 0.0
        while k < len(idles) and idles[k][0] <= st + du:
            idle += idles[k][1]; k += 1
        frames.append((st, (du - idle) * 1000, du * 1000, idle * 1000))
    return frames


def foreground_runs(frames, idle_ms=100):
    """Consecutive frames not dominated by the frame limiter (i.e. the editor/game was in focus)."""
    runs, cur = [], []
    for f in frames:
        if f[3] > idle_ms:
            if cur: runs.append(cur); cur = []
        else:
            cur.append(f)
    if cur: runs.append(cur)
    return sorted(runs, key=len, reverse=True)


def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(len(sorted_vals) * p))] if sorted_vals else 0.0


def load_window(ins, t0, t1, tag):
    p = ins.export(f'win_{tag}', f'-columns=ThreadName,TimerName,StartTime,Duration,Depth -threads=* -timers=* -startTime={t0:.6f} -endTime={t1:.6f}')
    ev = collections.defaultdict(list)
    for r in csv.DictReader(open(p, encoding='utf-8', errors='replace')):
        s, d = num(r['StartTime']), num(r['Duration'])
        if s is None or d is None:
            continue
        ev[r['ThreadName']].append((s, d, int(r['Depth']), r['TimerName']))
    return ev


def exclusive(ev):
    """(group, timer) -> [excl_s, count, incl_s, max_incl_s]; exclusive = duration minus direct children."""
    out = collections.defaultdict(lambda: [0.0, 0, 0.0, 0.0])
    for th, lst in ev.items():
        g = group_of(th)
        lst.sort(key=lambda e: (e[0], e[2]))
        last, selfd = {}, []
        for i, (s, d, dep, n) in enumerate(lst):
            selfd.append(d); last[dep] = i
            if dep > 0 and (dep - 1) in last:
                selfd[last[dep - 1]] -= d
        for (s, d, dep, n), sd in zip(lst, selfd):
            x = out[(g, n)]
            x[0] += max(sd, 0); x[1] += 1; x[2] += d; x[3] = max(x[3], d)
    return out


# ------------------------------------------------------------------ modes
def mode_overview(ins, a):
    fr = load_frames(ins)
    act = sorted(f[1] for f in fr)
    print(f'trace: {ins.trace}')
    print(f'frames: {len(fr)} | active frame time median {pct(act,.5):.1f} ms, p95 {pct(act,.95):.1f}, p99 {pct(act,.99):.1f}, max {act[-1]:.1f} ms')
    bg = sum(1 for f in fr if f[3] > 100)
    print(f'frames dominated by frame-limiter sleep (>100 ms; editor in background/throttled): {bg}')
    print(f'real hitches (active >= {a.threshold:.0f} ms): {sum(1 for f in fr if f[1] >= a.threshold)}')
    print('longest foreground runs (good windows for `cost`):')
    for r in foreground_runs(fr)[:5]:
        print(f'  {r[0][0]:.1f}s -> {r[-1][0]:.1f}s  frames={len(r)}  avg {sum(x[2] for x in r)/len(r):.1f} ms/frame')
    p = ins.export('threads', '', cmd='ExportThreads')
    names = [r['Name'] for r in csv.DictReader(open(p, encoding='utf-8', errors='replace'))]
    print(f'threads ({len(names)}): ' + ', '.join(sorted(set(group_of(n) for n in names)))[:300])


def mode_scopes(ins, a):
    p = ins.export('scopes_' + a.prefix.strip('/*').replace('/', '_'),
                   f'-columns=ThreadName,TimerName,StartTime,Duration,Depth -threads=* -timers={a.prefix}*')
    st = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for r in csv.DictReader(open(p, encoding='utf-8', errors='replace')):
        d = num(r['Duration'])
        if d is None: continue
        x = st[r['TimerName']]; x[0] += 1; x[1] += d; x[2] = max(x[2], d)
    fr = load_frames(ins)
    print(f'scopes "{a.prefix}*": {len(st)} timers, {len(fr)} frames in trace')
    print(f'{"total ms":>10} {"ms/frame":>9} {"calls":>8} {"avg us":>9} {"max ms":>8}  scope')
    for n, (c, tot, mx) in sorted(st.items(), key=lambda kv: -kv[1][1]):
        print(f'{tot*1000:10.1f} {tot*1000/max(len(fr),1):9.3f} {c:8d} {tot/c*1e6:9.1f} {mx*1000:8.2f}  {n}')


def mode_cost(ins, a):
    fr = load_frames(ins)
    if a.t_from is None:
        run = foreground_runs(fr)[0]
        t0, t1 = run[0][0], run[-1][0] + run[-1][2] / 1000
        print(f'auto window: longest foreground run {t0:.1f}s -> {t1:.1f}s')
    else:
        t0, t1 = a.t_from, a.t_to
    ev = load_window(ins, t0, t1, f'{t0:.0f}_{t1:.0f}')
    frames = sum(1 for e in ev['GameThread'] if e[3] == TICK) or 1
    ex = exclusive(ev)
    dur = t1 - t0
    print(f'window {t0:.1f}-{t1:.1f}s | {frames} frames | {frames/dur:.0f} FPS avg | {1000*dur/frames:.1f} ms/frame')
    print('(ms/frame = total time / frames; "busy" excludes Wait*/wrapper timers; editor traces include editor UI cost)')
    for g in KEY_THREADS:
        rows = sorted(((n, v) for (gg, n), v in ex.items() if gg == g and not is_noise(n)), key=lambda kv: -kv[1][0])
        if not rows: continue
        busy = sum(v[0] for _, v in rows) * 1000 / frames
        print(f'\n--- {g}: busy {busy:.2f} ms/frame ---')
        for n, v in rows[:a.top]:
            print(f'  {v[0]*1000/frames:7.3f} ms/frame  calls/frame {v[1]/frames:7.1f}  avg {v[0]/v[1]*1e6:8.1f} us  {n[:80]}')
    if a.prefix:
        rows = sorted(((n, v) for (g, n), v in ex.items() if n.startswith(a.prefix)), key=lambda kv: -kv[1][2])
        print(f'\n--- {a.prefix}* scopes (inclusive ms/frame) ---')
        for n, v in rows[:a.top + 4]:
            print(f'  {v[2]*1000/frames:7.3f} ms/frame  calls/frame {v[1]/frames:7.1f}  max {v[3]*1000:6.2f} ms  {n}')


def classify(top_gt, active_ms, prefix):
    """Label a hitch by the single dominant GameThread timer (>= 25% of the frame's active time)."""
    if not top_gt: return 'no GameThread data'
    name, v = top_gt[0]
    share = v[0] * 1000 / max(active_ms, 1e-6)
    if share < 0.25:
        return 'GameThread mostly waiting -> look at RenderThread/GPU/Workers lines (render- or task-bound)'
    if prefix and name.startswith(prefix): return f'project scope {name}'
    if 'WinPumpMessages' in name: return 'OS window messages (console/input/window focus) - not gameplay'
    if name == 'Tick_Core': return 'core ticker (FTSTicker delegates, HTTP/EOS/Steam/voice) - add scopes inside own tickers'
    low = name.lower()
    if any(k in low for k in ('garbage', 'reachability', 'collectgarbage')) or low.startswith('gc'):
        return 'garbage collection (many UObjects alive/created/destroyed: spawns, widgets, NewObject)'
    if 'shader' in low or 'compile' in low: return 'shader compilation'
    if any(k in low for k in ('loadobject', 'staticload', 'loadpackage', 'loadclass')): return 'synchronous asset loading'
    if name.startswith('Slate'): return 'Slate/UMG layout or paint'
    return f'dominant unmarked timer "{name}" ({share:.0%} of frame): find its code and add scopes inside'


def mode_hitches(ins, a):
    fr = load_frames(ins)
    hs = sorted([f for f in fr if f[1] >= a.threshold], key=lambda f: -f[1])[:a.top]
    print(f'{sum(1 for f in fr if f[1] >= a.threshold)} real hitches (active >= {a.threshold:.0f} ms); showing {len(hs)} worst. Frame-limiter sleep is excluded.')
    for i, (st, act, tot, idle) in enumerate(sorted(hs), 1):
        ev = load_window(ins, st, st + tot / 1000, f'h{st:.3f}')
        ex = exclusive(ev)
        top = sorted(((n, v) for (g, n), v in ex.items() if g in KEY_THREADS and not is_noise(n)), key=lambda kv: -kv[1][0])
        gt = sorted(((n, v) for (g, n), v in ex.items() if g == 'GameThread' and not is_noise(n)), key=lambda kv: -kv[1][0])
        mine = sum(v[0] for (g, n), v in ex.items() if a.prefix and n.startswith(a.prefix)) * 1000
        print(f'\n=== hitch {i}: t={st:.3f}s ({int(st//60)}m{st%60:05.2f}s) active {act:.1f} ms [{classify(gt, act, a.prefix)}]')
        for n, v in gt[:3]:
            print(f'    GameThread  {v[0]*1000:7.2f} ms  x{v[1]:<4} {n[:70]}')
        others = [(g, n, v) for (g, n), v in ex.items() if g != 'GameThread' and g in KEY_THREADS and not is_noise(n)]
        for g, n, v in sorted(others, key=lambda t: -t[2][0])[:3]:
            print(f'    {g:<11} {v[0]*1000:7.2f} ms  x{v[1]:<4} {n[:70]}')
        if a.prefix:
            print(f'    {a.prefix}* scopes exclusive total: {mine:.2f} ms')


def mode_compare(ins, a):
    base = Insights(a.baseline, ins.out, ins.exe)
    res = []
    for t in (base, ins):
        fr = load_frames(t)
        run = foreground_runs(fr)[0]
        t0, t1 = run[0][0], run[-1][0] + run[-1][2] / 1000
        ev = load_window(t, t0, t1, f'{t0:.0f}_{t1:.0f}')
        frames = sum(1 for e in ev['GameThread'] if e[3] == TICK) or 1
        ex = exclusive(ev)
        res.append((frames, {k: v[0] * 1000 / frames for k, v in ex.items() if not is_noise(k[1])}, (t1 - t0) * 1000 / frames))
    (fb, mb, ab), (fn, mn, an) = res
    print(f'baseline {fb} frames {ab:.1f} ms/frame -> new {fn} frames {an:.1f} ms/frame')
    keys = set(mb) | set(mn)
    diffs = sorted(((mn.get(k, 0) - mb.get(k, 0), k) for k in keys), key=lambda x: -abs(x[0]))[:a.top]
    print('largest ms/frame changes (new - baseline):')
    for d, (g, n) in diffs:
        print(f'  {d:+7.3f}  [{g}] {n[:80]}  ({mb.get((g,n),0):.3f} -> {mn.get((g,n),0):.3f})')


ENGINE_ONLY = ('WinPumpMessages', 'WaitForTasks', 'Slate::Prepass', 'Slate_PaintSlowPath', 'ProcessLocalPlayerSlateOperations',
               'FEngineLoop', 'RHI', 'D3D12', 'SceneRender', 'TemporalSuperResolution', 'Nanite', 'VirtualShadowMap', 'Shadow',
               'RenderGraph', 'FRDG', 'ZenHttp', 'CharacterMesh', 'UWorld_Tick', 'Tick_Engine', 'Frame', 'Present')


class SourceIndex:
    """Reads the project's C++ sources once and answers 'which file is behind this timer?'."""

    def __init__(self, env):
        self.files = {}
        for m in env.get('modules', []):
            for root, _, fs in os.walk(m['source_dir']):
                for f in fs:
                    if f.endswith(('.cpp', '.h', '.inl')):
                        p = os.path.join(root, f)
                        try:
                            self.files[p] = open(p, encoding='utf-8', errors='replace').read().splitlines()
                        except OSError:
                            pass
        self.root = env.get('project_root', '.')

    def grep(self, pattern, limit=6):
        rx, out = re.compile(pattern), []
        for p, lines in self.files.items():
            for i, line in enumerate(lines, 1):
                if rx.search(line) and not line.lstrip().startswith('//'):
                    out.append((os.path.relpath(p, self.root), i, line.strip()[:100]))
                    if len(out) >= limit:
                        return out
        return out

    def locate(self, name, prefix):
        """Return (kind, [(file, line, text)]) for a timer name."""
        if prefix and name.startswith(prefix):
            rest = name[len(prefix):]
            return 'project scope', self.grep(r'_SCOPE\w*\(\s*"' + re.escape(rest) + r'"')
        if name == 'Tick_Core':
            return 'core ticker: FTSTicker delegates registered by the project', self.grep(r'GetCoreTicker\(\)\.AddTicker|AddTicker\(')
        if name.startswith(('WBP_', 'SConstraintCanvas', 'SViewport', 'Paint: Game UI', 'Slate', 'SInvalidation', 'FViewport_Draw',
                            'ProcessLocalPlayerSlate')) or 'Widget' in name:
            hits = self.grep(r'::(NativePaint|OnPaint|NativeTick|NativeConstruct)\s*\(', 8)
            return ('UI pipeline (engine). Project widgets that paint/tick are the likely contributors; '
                    'WBP_* assets are Blueprint widgets under Content/'), hits
        if re.fullmatch(r'\w+::\w+', name):
            cls, fn = name.split('::')
            hits = self.grep(re.escape(cls.lstrip('AU')) + r'\w*::' + re.escape(fn) + r'\s*\(') or self.grep(re.escape(name) + r'\s*\(')
            return ('project function' if hits else 'engine function'), hits
        if any(name.startswith(e) for e in ENGINE_ONLY) or ' ' in name or '%' in name:
            return 'engine/OS timer (no project source)', []
        if re.fullmatch(r'\w+', name):
            hits = [(os.path.relpath(p, self.root), 1, 'file name match') for p in self.files if name.lower() in os.path.basename(p).lower()]
            hits += self.grep(r'\bclass\b[^;{]*\b[UAF]?' + re.escape(name) + r'\w*\b', 4)
            return ('component/actor tick (class name in the trace)' if hits else 'engine or Blueprint (no project match)'), hits[:6]
        return 'unknown', []


def mode_locate(ins, a):
    env = ue_env.discover(a.project)
    if 'error' in env or not env.get('modules'):
        print('PROJECT_NOT_CONNECTED: no .uproject / Source folder was found from', os.path.abspath(a.project))
        print('Ask the user to connect or attach the Unreal project folder (at least Source/, ideally the whole project)')
        print('and run again with --project <path to the folder that contains the .uproject>.')
        return
    names = list(a.timers or [])
    if not names:
        fr = load_frames(ins)
        run = foreground_runs(fr)[0]
        t0, t1 = run[0][0], run[-1][0] + run[-1][2] / 1000
        ex = exclusive(load_window(ins, t0, t1, f'{t0:.0f}_{t1:.0f}'))
        gt = sorted(((n, v) for (g, n), v in ex.items() if g == 'GameThread' and not is_noise(n)), key=lambda kv: -kv[1][0])
        mine = sorted(((n, v) for (g, n), v in ex.items() if a.prefix and n.startswith(a.prefix)), key=lambda kv: -kv[1][2])
        names = [n for n, _ in gt[:a.top]] + [n for n, _ in mine[:a.top]]
        for st, act, tot, idle in sorted([f for f in fr if f[1] >= a.threshold], key=lambda f: -f[1])[:5]:
            hex_ = exclusive(load_window(ins, st, st + tot / 1000, f'h{st:.3f}'))
            top = sorted(((n, v) for (g, n), v in hex_.items() if g == 'GameThread' and not is_noise(n)), key=lambda kv: -kv[1][0])
            if top: names.append(top[0][0])
        names = list(dict.fromkeys(names))
    idx = SourceIndex(env)
    print(f'source files indexed: {len(idx.files)}  (project: {env["project_root"]})')
    print('Timer -> where it comes from. Files are CANDIDATES: read them before proposing a fix.\n')
    for n in names:
        kind, hits = idx.locate(n, a.prefix)
        print(f'* {n}\n    kind: {kind}')
        for f, ln, txt in hits:
            print(f'    {f}:{ln}  {txt}')
        if not hits and kind.startswith(('project', 'component', 'UI', 'core')):
            print('    (no match found; search the code by hand)')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('mode', choices=['overview', 'scopes', 'cost', 'hitches', 'compare', 'locate'])
    ap.add_argument('--trace'); ap.add_argument('--baseline'); ap.add_argument('--out'); ap.add_argument('--insights')
    ap.add_argument('--project', default='.'); ap.add_argument('--prefix', default='')
    ap.add_argument('--from', dest='t_from', type=float); ap.add_argument('--to', dest='t_to', type=float)
    ap.add_argument('--threshold', type=float, default=40.0); ap.add_argument('--top', type=int, default=12)
    ap.add_argument('--timers', nargs='*', help='locate: timer names to map to source files (default: the top costs and hitch causes)')
    a = ap.parse_args()
    env = ue_env.discover(a.project)
    exe = a.insights or env.get('unreal_insights')
    trace = a.trace or (env.get('recent_traces') or [None])[0]
    if not trace and not (a.mode == 'locate' and ('error' in env or not env.get('modules'))):
        sys.exit('no --trace given and no recent .utrace found')
    out = a.out or os.path.join(env.get('project_root', '.'), 'Saved', 'Profiling', 'analysis')
    if a.mode == 'locate' and ('error' in env or not env.get('modules')):
        return mode_locate(None, a)          # prints PROJECT_NOT_CONNECTED and what to ask the user
    ins = Insights(trace, out, exe)
    if not a.prefix: a.prefix = env.get('profiling_prefix') or ''   # project scope prefix, e.g. "MP/"
    if a.mode == 'scopes' and not a.prefix: sys.exit('scopes mode needs --prefix (no profiling header found)')
    if a.t_from is not None and a.t_to is None: sys.exit('--from needs --to')
    globals()['mode_' + a.mode](ins, a)


if __name__ == '__main__':
    main()
