#!/usr/bin/env python3
"""Audit profiling scopes in the game source.

  python audit_scopes.py [--project PATH] [--macro MP_SCOPE] [--files a.cpp b.cpp]

Reports: scopes per file, duplicate names, two scopes on one line (breaks the __LINE__ based id),
names not matching "Mechanic/Function[/Phase]", scopes with a non-literal name, and scopes
placed inside headers. Exit code 1 if there are problems (usable as a pre-submit check).
"""
import argparse, collections, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ue_env  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', default='.')
    ap.add_argument('--macro', help='scope macro name (default: auto-detect from the profiling header)')
    ap.add_argument('--files', nargs='*', help='only audit these files')
    a = ap.parse_args()
    env = ue_env.discover(a.project)
    macros = [a.macro] if a.macro else [m for m in env.get('profiling_macros', []) if 'SCOPE' in m and 'DYN' not in m]
    if not macros:
        sys.exit('no scope macro found; pass --macro')
    pat = re.compile(r'\b(' + '|'.join(map(re.escape, macros)) + r')\s*\((.*?)\)\s*;')
    files = a.files or [os.path.join(r, f) for m in env['modules'] for r, _, fs in os.walk(m['source_dir'])
                        for f in fs if f.endswith(('.cpp', '.h', '.inl'))]
    names = collections.defaultdict(list)
    per_file, problems = collections.Counter(), []
    for p in files:
        if os.path.basename(p) == os.path.basename(env.get('profiling_header') or ''):
            continue
        for ln, line in enumerate(open(p, encoding='utf-8', errors='replace'), 1):
            if line.lstrip().startswith('//') or '#define' in line:
                continue
            hits = pat.findall(line)
            if not hits:
                continue
            per_file[p] += len(hits)
            if len(hits) > 1:
                problems.append(f'{p}:{ln}: {len(hits)} scopes on one line (id collision)')
            if p.endswith('.h'):
                problems.append(f'{p}:{ln}: scope in a header (inline function) - prefer the .cpp')
            for _, arg in hits:
                arg = arg.strip()
                if not (arg.startswith('"') and arg.endswith('"')):
                    problems.append(f'{p}:{ln}: scope name is not a string literal: {arg}')
                    continue
                n = arg.strip('"')
                names[n].append(f'{os.path.basename(p)}:{ln}')
                if not re.fullmatch(r'[A-Za-z0-9_]+(/[A-Za-z0-9_]+)+', n):
                    problems.append(f'{p}:{ln}: name "{n}" should look like Mechanic/Function[/Phase]')
    for n, locs in names.items():
        if len(locs) > 1:
            problems.append(f'duplicate name "{n}": {", ".join(locs)}')
    print(f'{sum(per_file.values())} scopes in {len(per_file)} files, {len(names)} distinct names (macros: {", ".join(macros)})')
    for p, c in per_file.most_common():
        print(f'  {c:3d}  {os.path.relpath(p, env["project_root"])}')
    if problems:
        print(f'\n{len(problems)} problem(s):')
        for x in problems:
            print('  ' + x)
        sys.exit(1)
    print('no problems')


if __name__ == '__main__':
    main()
