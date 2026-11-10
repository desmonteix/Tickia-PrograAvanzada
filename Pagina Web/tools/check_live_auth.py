"""Opt-in browser E2E against Tickia, with one synthetic account per run.

Credentials exist only in memory. No payment, SMS, email or personal account
is used. Artifacts contain request paths/statuses, never headers or bodies.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-test-registration', action='store_true')
    parser.add_argument('--channel', choices=('chromium', 'msedge', 'chrome'), default='chromium')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.allow_test_registration:
        parser.error('This E2E creates one synthetic account; opt in explicitly.')
    args.output.mkdir(parents=True, exist_ok=True)
    origin = 'https://tickia.lat'
    email = 'tickia-e2e-' + secrets.token_hex(8) + '@example.com'
    password = secrets.token_urlsafe(24)
    report = {'started_at_utc': datetime.now(timezone.utc).isoformat(),
              'origin': origin, 'test_account_email': email, 'steps': [],
              'auth_responses': [], 'auth_requests': [], 'script_paths': [], 'page_error_types': [],
              'console_error_count': 0, 'credentials_logged': False,
              'live_payments_attempted': False}
    current = 'launch_isolated_browser'
    passed = False
    with sync_playwright() as pw:
        launch_options = {} if args.channel == 'chromium' else {'channel': args.channel}
        browser = pw.chromium.launch(timeout=25000, **launch_options)
        context = browser.new_context(viewport={'width': 1440, 'height': 1000})
        page = context.new_page()
        # A registration chains register, login and /me. Each API call has its
        # own 20-second app timeout, so the whole-flow assertion must cover all
        # three calls. Request timings remain visible in the result.
        page.set_default_timeout(65000)
        page.set_default_navigation_timeout(25000)
        started = time.monotonic()

        def response_seen(response):
            parsed = urlsplit(response.url)
            if parsed.path.startswith('/api/auth/'):
                report['auth_responses'].append({'host': parsed.netloc,
                    'path': parsed.path, 'method': response.request.method,
                    'status': response.status,
                    'seconds_since_start': round(time.monotonic() - started, 3)})

        def request_seen(request, event):
            parsed = urlsplit(request.url)
            if parsed.path.startswith('/api/auth/'):
                report['auth_requests'].append({'event': event, 'host': parsed.netloc,
                    'path': parsed.path, 'method': request.method,
                    'seconds_since_start': round(time.monotonic() - started, 3)})

        def console_seen(message):
            if message.type == 'error':
                report['console_error_count'] += 1

        def step(name, action):
            nonlocal current
            current = name
            start = time.monotonic()
            action()
            report['steps'].append({'name': name, 'result': 'PASS',
                'duration_seconds': round(time.monotonic() - start, 3)})

        page.on('response', response_seen)
        page.on('request', lambda request: request_seen(request, 'started'))
        page.on('requestfinished', lambda request: request_seen(request, 'finished'))
        page.on('requestfailed', lambda request: request_seen(request, 'failed'))
        page.on('console', console_seen)
        page.on('pageerror', lambda error: report['page_error_types'].append(type(error).__name__))
        try:
            def open_site():
                page.goto(origin, wait_until='domcontentloaded')
                expect(page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
                report['script_paths'] = [urlsplit(src).path for src in
                    page.locator('script[src]').evaluate_all('(nodes) => nodes.map(n => n.src)')]
            step('open_production_site_with_valid_tls', open_site)

            def register():
                page.get_by_role('button', name='Ingresar', exact=True).click()
                page.get_by_role('button', name='¿No tienes cuenta? Regístrate').click()
                page.get_by_label('Correo electrónico').fill(email)
                page.get_by_label('Teléfono').fill('000000000')
                page.get_by_label('Contraseña', exact=True).fill(password)
                page.get_by_role('button', name='Registrarse', exact=True).click()
                expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
            step('register_and_automatically_sign_in', register)

            def reload_session():
                page.reload(wait_until='domcontentloaded')
                expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
            step('session_survives_reload', reload_session)

            def logout():
                page.get_by_role('button', name='Salir', exact=True).click()
                expect(page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
                with page.expect_response(lambda r: urlsplit(r.url).path == '/api/auth/me') as response:
                    page.reload(wait_until='domcontentloaded')
                if response.value.status != 401:
                    raise AssertionError('Anonymous session must return 401 after logout.')
                expect(page.get_by_role('button', name='Ingresar', exact=True)).to_be_visible()
            step('logout_and_verify_anonymous_after_reload', logout)

            def login():
                page.get_by_role('button', name='Ingresar', exact=True).click()
                page.get_by_label('Correo electrónico').fill(email)
                page.get_by_label('Contraseña', exact=True).fill(password)
                page.get_by_role('button', name='Iniciar sesión', exact=True).click()
                expect(page.get_by_role('button', name='Salir', exact=True)).to_be_visible()
            step('sign_in_with_existing_account', login)
            step('existing_account_session_survives_reload', reload_session)
            step('final_logout', logout)

            auth = report['auth_responses']
            if any(item['host'] != 'tickia.lat' for item in auth):
                raise AssertionError('Authentication must use the app origin.')
            if report['page_error_types']:
                raise AssertionError('Unexpected JavaScript exception.')
            passed = True
        except Exception as error:
            report['failure'] = {'stage': current, 'type': type(error).__name__}
            report['visible_alerts'] = page.get_by_role('alert').all_text_contents()
        finally:
            report['result'] = 'PASS' if passed else 'FAIL'
            try:
                page.screenshot(path=str(args.output / 'live-auth.png'), full_page=True)
            except Exception:
                report['screenshot_unavailable'] = True
            context.close()
            browser.close()
    report['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    (args.output / 'live-auth.json').write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
