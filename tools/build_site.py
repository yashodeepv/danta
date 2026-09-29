"""build_site.py - Spec Studio for GitHub Pages: no server, Danta's Python runs in the page.

    python tools/build_site.py [--out site]

Writes:
    site/index.html   the Studio page (danta/app/static/index.html) with a loader that starts
                      Pyodide, unpacks danta.zip and answers the page's /api/ requests itself
    site/danta.zip    Danta's Python sources and data (no tests)
    site/.nojekyll    serve files as they are

Local `danta studio` keeps its server (and runs the projects' tests); this build asks
the user to run the tests after downloading a project.
"""

import argparse
import io
import os
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PYODIDE = 'https://cdn.jsdelivr.net/pyodide/v0.26.4/full/'

LOADER = r'''<script>
// GitHub Pages build: there is no server. Danta's Python runs in this page (Pyodide),
// and the /api/ requests the Studio makes are answered here, by danta/web.py.
(function () {
  const PYODIDE = '__PYODIDE__';
  const cover = document.createElement('div');
  cover.id = 'boot';
  cover.innerHTML = '<div><b>Starting Danta in your browser…</b><span>The first visit downloads Python (about 10 MB); after that it is cached.</span></div>';
  document.addEventListener('DOMContentLoaded', () => document.body.appendChild(cover));

  const ready = (async () => {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = PYODIDE + 'pyodide.js';
      s.onload = resolve;
      s.onerror = () => reject(new Error('could not download Pyodide'));
      document.head.appendChild(s);
    });
    const py = await loadPyodide({ indexURL: PYODIDE });
    const bundle = await fetch('danta.zip');
    if (!bundle.ok) throw new Error('could not download danta.zip');
    py.unpackArchive(await bundle.arrayBuffer(), 'zip', { extractDir: '/home/pyodide/danta' });
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide/danta')");
    return py.pyimport('danta.web');
  })();
  ready.then(() => cover.remove(),
             (e) => { cover.innerHTML = `<div><b>Danta could not start.</b><span>${e.message}</span></div>`; });

  const json = (text, status = 200) => new Response(text, { status, headers: { 'Content-Type': 'application/json' } });
  const realFetch = window.fetch.bind(window);
  window.fetch = async (url, init = {}) => {
    const path = typeof url === 'string' ? url : (url.url || url.href || String(url));
    if (!path.startsWith('/api/')) return realFetch(url, init);
    const web = await ready;
    const body = init.body ? JSON.parse(init.body) : {};
    await new Promise((r) => setTimeout(r, 30));        // let "Building…" paint before Python takes the thread
    try {
      if (path === '/api/prompt') return new Response(web.api_prompt());
      if (path === '/api/examples') return json(web.api_examples());
      if (path === '/api/build') return json(web.api_build(body.spec || ''));
      if (path === '/api/verify') return json(web.api_verify(body.language || 'python'));
      if (path === '/api/correction-prompt') return json(web.api_correction_prompt(body.spec || '', body.attempt || 1, body.max_attempts || 3));
      if (path === '/api/project') {
        const data = web.api_project(body.spec || '', body.language || 'python');
        if (data === undefined || data === null) return json('{"fatal": "build the spec without errors first"}', 400);
        const bytes = data.toJs();
        data.destroy();
        return new Response(new Blob([bytes], { type: 'application/zip' }));
      }
    } catch (e) {
      return json(JSON.stringify({ fatal: String(e.message || e) }), 500);
    }
    return new Response('not found', { status: 404 });
  };
})();
</script>
<style>
#boot { position: fixed; inset: 0; z-index: 100; display: grid; place-items: center; background: var(--paper); }
#boot div { display: grid; gap: 6px; text-align: center; padding: 24px 28px; border: 1px solid var(--line);
  border-radius: 14px; background: var(--surface); box-shadow: var(--shadow); }
#boot b { font-size: 16px; }
#boot span { color: var(--muted); font-size: 13px; }
</style>
'''

KEEP = ('.py', '.md', '.json')


def bundle():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        for d, dirs, files in os.walk(os.path.join(ROOT, 'danta')):
            dirs[:] = sorted(x for x in dirs if x not in ('__pycache__', 'tests', 'static'))
            for f in sorted(files):
                if f.endswith(KEEP):
                    full = os.path.join(d, f)
                    z.write(full, os.path.relpath(full, ROOT))
    return buf.getvalue()


def landing():
    with open(os.path.join(ROOT, 'danta', 'app', 'static', 'index.html')) as f:
        return f.read()


def studio():
    with open(os.path.join(ROOT, 'danta', 'app', 'static', 'studio.html')) as f:
        html = f.read()
    pos = html.index('<script>\n(function () {')
    return html[:pos] + LOADER.replace('__PYODIDE__', PYODIDE) + html[pos:]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=os.path.join(ROOT, 'site'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, 'index.html'), 'w') as f:
        f.write(landing())
    with open(os.path.join(a.out, 'studio.html'), 'w') as f:
        f.write(studio())
    with open(os.path.join(a.out, 'danta.zip'), 'wb') as f:
        f.write(bundle())
    open(os.path.join(a.out, '.nojekyll'), 'w').close()
    skill_src = os.path.join(ROOT, 'tools', 'danta-skill.md')
    skill_dst = os.path.join(a.out, 'danta-skill.md')
    with open(skill_src) as f:
        with open(skill_dst, 'w') as g:
            g.write(f.read())
    print(f'wrote {a.out}/index.html, {a.out}/studio.html, {a.out}/danta.zip and {a.out}/danta-skill.md')


if __name__ == '__main__':
    main()
