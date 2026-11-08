"""Fixed browser operations. Receives JSON data, never generated Python or JS."""
import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

from playwright.sync_api import sync_playwright


def run(plan):
    Path('/tmp/home').mkdir(exist_ok=True)
    artifacts = Path('/tmp/artifacts')
    artifacts.mkdir(exist_ok=True)
    kind = plan['kind']
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            chromium_sandbox=True,
            proxy={'server': plan['proxy']},
            args=['--disable-quic', '--disable-background-networking', '--disable-features=AsyncDns,DnsOverHttps'],
        )
        try:
            context = browser.new_context(viewport={'width': 1280, 'height': 720}, service_workers='block', accept_downloads=False)
            page = context.new_page()
            page.set_default_timeout(10000)
            if kind == 'preflight':
                page.goto('about:blank')
                return {'title': 'Chromium sandbox started', 'sandbox_enabled': True}
            url = plan['url']
            print('Browser started; navigating to ' + url, flush=True)
            response = page.goto(url, timeout=15000, wait_until='domcontentloaded')
            if response is not None and response.status >= 400:
                raise RuntimeError('Navigation rejected: HTTP ' + str(response.status))
            if kind == 'metadata_probe':
                # A failed containment check must never capture or publish metadata.
                raise RuntimeError('Metadata navigation was not denied; response body was not collected')
            result = {'url': page.url, 'title': page.title(), 'http_status': response.status if response else None}
            if kind in ('prepare_form', 'submit_form'):
                revision = page.locator('meta[name="brz-form-revision"]').get_attribute('content')
                if not revision or revision != plan['revision']:
                    raise RuntimeError('Form revision changed; new preparation and approval are required')
                form = page.locator('form#demo-form')
                action = form.get_attribute('action')
                if action not in ('/submit', plan['url'].rstrip('/') + '/submit'):
                    raise RuntimeError('Unexpected form destination')
                if (form.get_attribute('method') or '').lower() != 'post':
                    raise RuntimeError('Unexpected form method')
                form.locator('[name="title"]').fill(plan['title'])
                form.locator('[name="message"]').fill(plan['message'])
                result.update(form_revision=revision, form_fields={'title': plan['title'], 'message': plan['message']})
                if kind == 'submit_form':
                    # The form endpoint independently enforces this one-use capability.
                    form.evaluate('(form, data) => { form.elements.permit.value = data.permit; form.elements.action_id.value = data.action_id; form.elements.revision.value = data.revision; }',
                                  {'permit': plan['permit'], 'action_id': plan['action_id'], 'revision': plan['revision']})
                    with page.expect_navigation(wait_until='domcontentloaded'):
                        form.locator('button[type="submit"]').click()
                    result['receipt'] = json.loads(page.locator('#receipt').inner_text())
                    print('Approved demo submission returned a receipt', flush=True)
                else:
                    print('Form prepared; waiting for human approval outside this sandbox', flush=True)
            elif kind == 'research':
                if urlparse(page.url).hostname == 'news.ycombinator.com':
                    evidence = []
                    for row in page.locator('tr.athing').all()[:3]:
                        anchor = row.locator('.titleline > a').first
                        evidence.append({'title': anchor.inner_text()[:500], 'url': urljoin(page.url, anchor.get_attribute('href') or page.url),
                                         'text': 'Hacker News headline; linked article content was not fetched.'})
                    result['evidence'] = evidence
                else:
                    text = page.locator('body').inner_text()[:12000]
                    result['evidence'] = [{'title': page.title()[:500], 'url': page.url, 'text': text}]
                print('Captured visible evidence and source URLs', flush=True)
            elif kind != 'metadata_probe':
                raise ValueError('Unsupported browser operation')
            page.screenshot(path=str(artifacts / 'screenshot.png'), full_page=False)
            result['screenshot_name'] = 'screenshot.png'
            result['captured_at'] = time.time()
            return result
        finally:
            browser.close()


if __name__ == '__main__':
    try:
        plan = json.loads(Path('/tmp/input.json').read_text())
        result = run(plan)
        Path('/tmp/brz-result.json').write_text(json.dumps(result))
    except Exception as exc:
        print(type(exc).__name__ + ': ' + str(exc), flush=True)
        raise SystemExit(1)
