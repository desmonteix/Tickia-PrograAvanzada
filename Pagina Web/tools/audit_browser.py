"""Local lab audit of the production bundle, with controlled API responses."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'test-results'
BASE = 'http://127.0.0.1:5177'
OUT.mkdir(exist_ok=True)
server = subprocess.Popen(['node', 'node_modules/vite/bin/vite.js', 'preview', '--host', '127.0.0.1', '--port', '5177', '--strictPort'], cwd=ROOT / 'frontend', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
try:
    for _ in range(100):
        try:
            urllib.request.urlopen(BASE, timeout=1).close()
            break
        except OSError:
            time.sleep(.2)
    else:
        raise RuntimeError('Production preview did not start')
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for width in [360, 768, 1440]:
            context = browser.new_context(viewport={'width': width, 'height': 900}, reduced_motion='reduce')
            page = context.new_page()
            errors, missing = [], []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.on('response', lambda response: missing.append(response.url) if response.status == 404 else None)
            page.route('**/api/auth/me', lambda route: route.fulfill(status=401, json={'detail': 'Sesión requerida'}))
            page.route('**/api/tickets', lambda route: route.fulfill(json=[{'id': '10000000-0000-0000-0000-000000000001', 'event_name': 'Evento de prueba local', 'event_date': '2099-12-01T20:00:00Z', 'zone': 'General', 'ticket_type': 'no_nominada', 'is_renominated': False, 'price': 125.50, 'estado': 'DISPONIBLE'}]))
            page.route('https://js.culqi.com/**', lambda route: route.fulfill(body='', content_type='application/javascript'))
            page.add_init_script("window.lab={lcp:0,cls:0,shifts:[]};new PerformanceObserver(list=>{for(const entry of list.getEntries())window.lab.lcp=entry.startTime}).observe({type:'largest-contentful-paint',buffered:true});new PerformanceObserver(list=>{for(const entry of list.getEntries())if(!entry.hadRecentInput){window.lab.cls+=entry.value;window.lab.shifts.push({value:entry.value,sources:entry.sources.map(s=>({node:s.node?.outerHTML.slice(0,150),before:s.previousRect.toJSON(),after:s.currentRect.toJSON()}))})}}).observe({type:'layout-shift',buffered:true});")
            page.goto(BASE, wait_until='networkidle')
            page.evaluate('document.fonts.ready')
            expect(page.get_by_role('heading', name='Evento de prueba local', exact=True)).to_be_visible()
            page.add_script_tag(path=str(ROOT / 'frontend/node_modules/axe-core/axe.min.js'))
            violations = page.evaluate("async () => (await axe.run(document,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}})).violations.map(v=>v.id)")
            measurement = page.evaluate("({width:innerWidth,lcp_ms:lab.lcp,cls:lab.cls,shifts:lab.shifts,fcp_ms:performance.getEntriesByName('first-contentful-paint')[0]?.startTime,overflow:document.documentElement.scrollWidth>innerWidth,resources:performance.getEntriesByType('resource').map(r=>({name:new URL(r.name).pathname,bytes:r.encodedBodySize,duration_ms:r.duration}))})")
            measurement.update({'javascript_errors': errors, 'missing_resources': missing, 'accessibility_violations': violations, 'environment': 'local production build; controlled API; no network/CPU throttling'})
            page.screenshot(path=str(OUT / f'production-{width}.png'), full_page=True)
            assert not errors and not missing and not violations and not measurement['overflow'], measurement
            assert 0 < measurement['lcp_ms'] < 2500, measurement
            assert measurement['cls'] < .1, measurement
            results.append(measurement)
            context.close()
        browser.close()
    (OUT / 'production-lab.json').write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps([{key: row[key] for key in ['width', 'lcp_ms', 'fcp_ms', 'cls', 'overflow', 'accessibility_violations']} for row in results], ensure_ascii=False))
finally:
    server.terminate()
    server.wait(timeout=10)
