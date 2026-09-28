"""danta - exact business intent in, verified software out.

    danta check    SPEC                 validate a spec; exit 1 on errors
    danta show     SPEC                 print each compiled flow as an outline
    danta compile  SPEC [--out DIR]     write each flow as IR2 JSON
    danta simulate SPEC                 run every path of every flow; show the test runs
    danta build    SPEC [--out DIR]     generate the projects (Python, JavaScript, Spring Boot)
                   [--lang python,javascript,java] [--verify]
    danta studio   [--port 8765] [--no-browser]
    danta prompt                        print the prompt that teaches an LLM to write specs
"""

import argparse
import sys


def _read(path):
    try:
        with open(path) as f:
            return f.read()
    except OSError as e:
        sys.exit(str(e))


def simulate(path):
    from danta.app.pipeline import build
    out = build(_read(path))
    if out['errors']:
        for e in out['errors']:
            print(f"{path}:{e['line']}: error [{e['rule']}] {e['message']}")
        return 1
    for f in out['flows']:
        if f.get('blocked'):
            print(f"{f['name']}: {f['blocked']}")
            continue
        print(f"{f['name']}  ({len(f['runs'])} test runs, {round(f['coverage'] * 100)}% of paths)")
        for r in f['runs']:
            outcome = 'ok' if r['status'] == 'ok' else f"error: {r['error']}"
            print(f"  {r['name']:4} {outcome}")
            for effect in r['effects']:
                print(f'         {effect}')
    return 0


def build_projects(path, out_dir, langs, verify):
    from danta.app.pipeline import build
    from danta.codegen.project import verify_project, write
    out = build(_read(path))
    if out['errors']:
        for e in out['errors']:
            print(f"{path}:{e['line']}: error [{e['rule']}] {e['message']}")
        return 1
    if not out['project']:
        print('no project: every flow must compile to exact logic (no prose values) first')
        return 1
    failed = False
    for lang in langs:
        p = out['project'][lang]
        target = f'{out_dir}/{lang}'
        write(p['files'], target)
        line = f"{lang:10} {len(p['files'])} files -> {target}  ({p['format']['status']})"
        if verify:
            r = verify_project(p['files'], lang)
            line += f"  tests {r['status']} {r['passed']}/{r['total']}"
            failed |= r['status'] == 'failed'
        print(line)
    return 1 if failed else 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ('check', 'show', 'compile'):
        from danta.spec.__main__ import main as spec_main
        return spec_main(argv)
    ap = argparse.ArgumentParser(prog='danta', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='command', required=True)
    sub.add_parser('check').add_argument('spec')
    sub.add_parser('show').add_argument('spec')
    sub.add_parser('compile').add_argument('spec')
    sub.add_parser('simulate').add_argument('spec')
    b = sub.add_parser('build')
    b.add_argument('spec')
    b.add_argument('--out', default='dist')
    b.add_argument('--lang', default='python,javascript,java')
    b.add_argument('--verify', action='store_true', help="run each project's own tests")
    s = sub.add_parser('studio')
    s.add_argument('--port', type=int, default=8765)
    s.add_argument('--no-browser', action='store_true')
    sub.add_parser('prompt')
    a = ap.parse_args(argv)
    if a.command == 'simulate':
        return simulate(a.spec)
    if a.command == 'build':
        return build_projects(a.spec, a.out, [x.strip() for x in a.lang.split(',') if x.strip()], a.verify)
    if a.command == 'studio':
        from danta.app.server import serve
        serve(a.port, not a.no_browser)
        return 0
    if a.command == 'prompt':
        from danta.app.prompt import build_prompt
        print(build_prompt())
        return 0
    return 2


if __name__ == '__main__':
    sys.exit(main())
