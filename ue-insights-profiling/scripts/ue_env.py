#!/usr/bin/env python3
"""Discover everything the profiling tools and any AI assistant need about the current Unreal project.

Usage:  python ue_env.py [--project PATH_TO_UPROJECT_OR_DIR] [--json]

Prints: .uproject, engine root, Build.bat / UnrealInsights.exe / UnrealEditor.exe,
game modules, an existing profiling header (if any), trace folders, newest .utrace,
whether the editor is running, and which version control the project uses.
Windows-first (registry lookup); falls back to UE_ROOT env var elsewhere.
"""
import argparse, glob, json, os, re, subprocess, sys

SCOPE_DEFINE = re.compile(r'#\s*define\s+(\w+)\s*\(.*TRACE_CPUPROFILER_EVENT_SCOPE')


def find_uproject(start):
    start = os.path.abspath(start)
    if os.path.isfile(start) and start.lower().endswith('.uproject'):
        return start
    d = start if os.path.isdir(start) else os.path.dirname(start)
    while True:
        hits = glob.glob(os.path.join(d, '*.uproject'))
        if hits:
            return hits[0]
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def find_engine(association):
    env = os.environ.get('UE_ROOT')
    if env and os.path.isdir(env):
        return env
    try:
        import winreg
    except ImportError:
        return None
    # Launcher install: HKLM\SOFTWARE\EpicGames\Unreal Engine\<ver>\InstalledDirectory
    for hive, base in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\EpicGames\Unreal Engine'),
                       (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\EpicGames\Unreal Engine')):
        try:
            with winreg.OpenKey(hive, base + '\\' + association) as k:
                return winreg.QueryValueEx(k, 'InstalledDirectory')[0]
        except OSError:
            pass
    # Source / custom build: HKCU\Software\Epic Games\Unreal Engine\Builds[GUID or name]
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Epic Games\Unreal Engine\Builds') as k:
            i = 0
            while True:
                name, val, _ = winreg.EnumValue(k, i)
                i += 1
                if name == association:
                    return val.replace('/', '\\')
    except OSError:
        pass
    return None


def run(cmd, cwd=None):
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20, shell=isinstance(cmd, str)).stdout
    except Exception:
        return ''


def find_profiling_header(source_dirs):
    """Return (path, macro names) of an existing header that wraps TRACE_CPUPROFILER_EVENT_SCOPE_*."""
    for sd in source_dirs:
        for root, _, files in os.walk(sd):
            for f in files:
                if f.endswith('.h'):
                    p = os.path.join(root, f)
                    try:
                        txt = open(p, encoding='utf-8', errors='replace').read()
                    except OSError:
                        continue
                    macros = SCOPE_DEFINE.findall(txt)
                    if macros:
                        return p, sorted(set(re.findall(r'#\s*define\s+(\w+)\s*\(', txt)))
    return None, []


def discover(project_hint='.'):
    up = find_uproject(project_hint)
    if not up:
        return {'error': 'no .uproject found from ' + os.path.abspath(project_hint)}
    root = os.path.dirname(up)
    data = json.load(open(up, encoding='utf-8'))
    assoc = data.get('EngineAssociation', '')
    engine = find_engine(assoc)
    info = {'uproject': up, 'project_root': root, 'engine_association': assoc, 'engine_root': engine}
    if engine:
        b = os.path.join(engine, 'Engine', 'Binaries', 'Win64')
        info['build_bat'] = os.path.join(engine, 'Engine', 'Build', 'BatchFiles', 'Build.bat')
        info['unreal_insights'] = os.path.join(b, 'UnrealInsights.exe')
        info['unreal_editor'] = os.path.join(b, 'UnrealEditor.exe')
        info['engine_trace_headers'] = os.path.join(engine, 'Engine', 'Source', 'Runtime', 'Core', 'Public', 'ProfilingDebugging')
        info['insights_exists'] = os.path.exists(info['unreal_insights'])
    mods = []
    for m in data.get('Modules', []):
        d = os.path.join(root, 'Source', m['Name'])
        mods.append({'name': m['Name'], 'type': m.get('Type'), 'source_dir': d, 'build_cs': os.path.join(d, m['Name'] + '.Build.cs'),
                     'exists': os.path.isdir(d)})
    info['modules'] = mods
    hdr, macros = find_profiling_header([m['source_dir'] for m in mods if m['exists']])
    info['profiling_header'] = hdr
    info['profiling_macros'] = macros
    pfx = None
    if hdr:
        m = re.search(r'TRACE_CPUPROFILER_EVENT_SCOPE_STR\(\s*"([^"]*)"', open(hdr, encoding='utf-8', errors='replace').read())
        pfx = m.group(1) if m else None
    info['profiling_prefix'] = pfx   # e.g. "MP/" - scope names start with this
    info['targets'] = [os.path.splitext(os.path.basename(p))[0].replace('.Target', '')
                       for p in glob.glob(os.path.join(root, 'Source', '*.Target.cs'))]
    traces = []
    for d in (os.path.join(root, 'Saved', 'Profiling'), os.path.join(root, 'Saved', 'TraceSessions'),
              os.path.join(os.environ.get('LOCALAPPDATA', ''), 'UnrealEngine', 'Common', 'UnrealTrace', 'Store')):
        traces += glob.glob(os.path.join(d, '**', '*.utrace'), recursive=True)
    traces.sort(key=os.path.getmtime, reverse=True)
    info['recent_traces'] = traces[:5]
    out = run('tasklist /FI "IMAGENAME eq UnrealEditor.exe" /NH')
    info['editor_running'] = 'UnrealEditor.exe' in out
    if os.path.exists(os.path.join(root, '.p4config')) or run(['p4', 'info'], cwd=root).count('Client root'):
        info['vcs'] = 'perforce'
    elif os.path.isdir(os.path.join(root, '.git')):
        info['vcs'] = 'git'
    else:
        info['vcs'] = 'none/unknown'
    info['path_has_spaces'] = ' ' in root
    return info


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='.')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()
    d = discover(a.project)
    if a.json:
        print(json.dumps(d, indent=2, ensure_ascii=False))
    else:
        for k, v in d.items():
            print(f'{k}: {v}')
