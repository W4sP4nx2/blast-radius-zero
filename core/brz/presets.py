"""Deterministic plans. These never invoke the model client."""
from textwrap import dedent

CSV_CODE = dedent('''\
    import csv, io, json, pathlib, time
    print("[1/3] Loading CSV inside the offline sandbox", flush=True)
    path = pathlib.Path('/tmp/input.csv')
    sample = "category,quantity,unit_price\\nCompute,4,12.50\\nStorage,10,3.00\\nCompute,2,15.00\\nNetwork,5,4.00\\n"
    text = path.read_text(encoding='utf-8-sig') if path.exists() else sample
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValueError("CSV has no data rows")
    print(f"Loaded {len(rows)} rows. Summarizing numeric columns.", flush=True)
    time.sleep(0.4)
    numeric = {}
    for key in rows[0]:
        values = []
        for row in rows:
            try:
                value = float(row[key])
                if not __import__('math').isfinite(value):
                    raise ValueError('nonfinite')
                values.append(value)
            except (ValueError, TypeError):
                break
        else:
            numeric[key] = {'sum': round(sum(values), 4), 'min': min(values), 'max': max(values), 'mean': round(sum(values)/len(values), 4)}
    summary = {'rows': len(rows), 'columns': list(rows[0]), 'numeric': numeric}
    if {'quantity', 'unit_price'}.issubset(rows[0]):
        summary['total_revenue'] = round(sum(float(r['quantity'])*float(r['unit_price']) for r in rows), 2)
    print('[2/3] Writing evidence artifacts', flush=True)
    out = pathlib.Path('/tmp/artifacts'); out.mkdir(exist_ok=True)
    (out/'analysis.json').write_text(json.dumps(summary, indent=2))
    with (out/'summary.csv').open('w', newline='') as f:
        w = csv.writer(f); w.writerow(['column', 'sum', 'min', 'max', 'mean'])
        for key, stats in numeric.items(): w.writerow([key, *stats.values()])
    time.sleep(0.4)
    print(json.dumps(summary, indent=2), flush=True)
    print('[3/3] Complete. No model calls; no external network.', flush=True)
''')

PRESETS = [
    {"id": "csv-analysis", "name": "CSV Analyst", "description": "Summarize an uploaded CSV or a built-in four-row sales sample. Download real JSON and CSV artifacts.", "pattern": "code", "code": CSV_CODE},
    {"id": "network-denial", "name": "Test network isolation", "description": "Attempt an external HTTPS request from a container with networking disabled.", "pattern": "code", "code": "import urllib.request\nprint('Attempting external HTTPS — network mode is none', flush=True)\nurllib.request.urlopen('https://vultr.com', timeout=3)"},
    {"id": "cpu-timeout", "name": "Test hard timeout", "description": "A busy loop is CPU-limited and terminated after ten seconds.", "pattern": "code", "code": "print('Starting bounded busy loop; harness deadline: 10 seconds', flush=True)\nwhile True: pass"},
    {"id": "memory-limit", "name": "Test memory cap", "description": "Attempt to allocate 600 MiB under a 256 MiB memory limit.", "pattern": "code", "code": "print('Requesting 600 MiB under a 256 MiB cap', flush=True)\nb = bytearray(1024 * 1024 * 600)"},
    {"id": "secret-hygiene", "name": "Check secret hygiene", "description": "Check that the host/provider key was not passed into the sandbox.", "pattern": "code", "code": "import os\nprint('VULTR_API_KEY:', os.environ.get('VULTR_API_KEY', 'CLEAN'))\nprint('BRZ_TEST_SECRET:', os.environ.get('BRZ_TEST_SECRET', 'CLEAN'))"},
    {"id": "readonly-filesystem", "name": "Test read-only root", "description": "Attempt a write to an otherwise user-owned home directory.", "pattern": "code", "code": "print('Attempting rootfs write in user-owned home', flush=True)\nopen('/home/sandbox/probe.txt', 'w').write('must not persist')"},
    {"id": "hn-research", "name": "Research with Receipts", "description": "Capture Hacker News and extract its top three headlines and source links. No AI summary is invented.", "pattern": "browser", "plan": {"kind": "research", "url": "https://news.ycombinator.com/"}},
    {"id": "metadata-probe", "name": "Test metadata denial", "description": "Attempt Vultr metadata navigation through the filtered browser proxy.", "pattern": "browser", "plan": {"kind": "metadata_probe", "url": "http://169.254.169.254/v1/identity/token"}},
    {"id": "demo-form", "name": "Prepare an approved action", "description": "Fill our demo form and inspect a screenshot. Nothing is submitted until you approve.", "pattern": "browser", "plan": {"kind": "prepare_form", "title": "Containment demo", "message": "This project-owned form creates a demo receipt only. I will review before submitting."}},
]
BY_ID = {p["id"]: p for p in PRESETS}


def public_presets():
    return [{k: v for k, v in p.items() if k != "plan"} for p in PRESETS]


def preset_ids():
    return [p["id"] for p in PRESETS]
