"""Real HTTP -> Redis -> coordinator -> Docker -> SSE/artifact smoke test.

Run only against a deployment you own. Consumes one rate-limited preset task.
No provider request or browser task is made. This is not a mock server.
"""
import json
import os
import time
import httpx


def main():
    base = os.getenv('BRZ_SMOKE_URL', 'http://127.0.0.1:8000').rstrip('/')
    origin = os.getenv('BRZ_SMOKE_ORIGIN', base)
    with httpx.Client(base_url=base, timeout=30, headers={'Origin': origin}) as client:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if client.get('/api/health').json().get('worker_ready'):
                break
            time.sleep(0.5)
        else:
            raise RuntimeError('A ready real execution worker is required')
        session = client.get('/api/session')
        session.raise_for_status()
        client.headers['X-CSRF-Token'] = session.json()['csrf_token']
        start = time.monotonic()
        response = client.post('/api/execute', json={'kind': 'preset', 'preset_id': 'csv-analysis'})
        response.raise_for_status()
        task_id = response.json()['task_id']
        first_status = None
        event_types = []
        with client.stream('GET', f'/api/tasks/{task_id}/events') as stream:
            stream.raise_for_status()
            for line in stream.iter_lines():
                if line == 'event: end':
                    break
                if not line.startswith('data: '):
                    continue
                event = json.loads(line[6:])
                event_types.append(event['type'])
                if event['type'] == 'stdout' and first_status is None:
                    first_status = client.get(f'/api/tasks/{task_id}').json()['status']
        task = client.get(f'/api/tasks/{task_id}').json()
        assert task['status'] == 'succeeded', task.get('error')
        assert first_status == 'running', f'First stdout arrived after completion: {first_status}'
        assert task['source'] == 'preset' and task['provider_requests'] == 0
        artifact = next(a for a in task['artifacts'] if a['name'] == 'analysis.json')
        downloaded = client.get(artifact['url'])
        downloaded.raise_for_status()
        analysis = downloaded.json()
        assert analysis['rows'] == 4 and analysis['total_revenue'] == 130
        if os.getenv('BRZ_SMOKE_EXPECT_AI_OFF') == '1':
            unavailable = client.post('/api/execute', json={'kind': 'task', 'pattern': 'code', 'prompt': 'Analyze my CSV'})
            assert unavailable.status_code == 503 and unavailable.json()['detail']['available_presets']
        print(json.dumps({'result': 'passed', 'task_id': task_id, 'status': task['status'],
                          'first_stdout_task_status': first_status, 'provider_requests': task['provider_requests'],
                          'rows': analysis['rows'], 'total_revenue': analysis['total_revenue'],
                          'artifacts': [a['name'] for a in task['artifacts']],
                          'event_types': sorted(set(event_types)), 'elapsed_seconds': round(time.monotonic()-start, 3)}))


if __name__ == '__main__':
    main()
