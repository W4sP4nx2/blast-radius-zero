"""Real browser smoke test. Requires the actual local/deployed backend and worker.

Consumes one zero-inference CSV preset. Does not intercept API responses.
"""
import json
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect


def main():
    with sync_playwright() as p:
        launch = {'headless': True}
        if os.getenv('BRZ_CHROMIUM_EXECUTABLE'):
            launch['executable_path'] = os.environ['BRZ_CHROMIUM_EXECUTABLE']
        browser = p.chromium.launch(**launch)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1080})
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(os.getenv('BRZ_UI_URL', 'http://localhost:3310'))
            page.wait_for_load_state('networkidle')
            expect(page.get_by_text('Worker connected', exact=True)).to_be_visible()
            page.get_by_role('button', name=re.compile('CSV Analyst')).click()
            expect(page.get_by_label('Live execution logs')).to_contain_text('[1/3]', timeout=15000)
            expect(page.get_by_text('Execution stream complete', exact=True)).to_be_visible(timeout=15000)
            page.get_by_role('tab', name=re.compile('Artifacts')).click()
            result_link = page.get_by_role('link', name=re.compile('analysis.json'))
            expect(result_link).to_be_visible()
            expect(page.get_by_role('link', name=re.compile('summary.csv'))).to_be_visible()
            with page.expect_download() as download_info:
                result_link.click()
            data = json.loads(Path(download_info.value.path()).read_text())
            assert data['rows'] == 4 and data['total_revenue'] == 130
            page.screenshot(path='/tmp/brz-real-csv-execution.png', full_page=True)
            assert not errors, errors
        finally:
            browser.close()
    print('PASS: real browser -> Next proxy -> API/session/CSRF -> Redis -> worker -> Docker CSV -> SSE -> downloaded JSON/CSV artifacts; no API interception')


if __name__ == '__main__':
    main()
