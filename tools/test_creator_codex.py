"""Probe the installed Codex client's MCP serialization against a local fake API.

No model, API key or remote endpoint is used. Only two fixed read-only tool
calls execute in a temporary empty workspace. This complements SDK tests;
it is not an evaluation of a model's ability to select the right tool.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading


def verify(codex='codex'):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def do_GET(self):
            data = b'{"models": []}'
            self.send_response(200); self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)

        def do_POST(self):
            requests.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
            number = len(requests)
            if number <= 2:
                item = dict(id=f'fc_probe_{number}', type='function_call', namespace='mcp__exp_creator',
                    name='schema_get' if number == 1 else 'project_get', call_id=f'call_probe_{number}',
                    arguments=json.dumps(dict(kind='choice') if number == 1 else dict(path='missing.expproj')))
            else:
                item = dict(id='msg_probe', type='message', role='assistant', status='completed',
                    content=[dict(type='output_text', text='Local MCP probe complete.', annotations=[])])
            events = [dict(type='response.output_item.done', output_index=0, item=item),
                dict(type='response.completed', response=dict(id=f'resp_{number}', object='response',
                    status='completed', output=[item], usage=dict(input_tokens=1, output_tokens=1, total_tokens=2)))]
            body = ''.join('event: ' + e['type'] + '\ndata: ' + json.dumps(e) + '\n\n' for e in events).encode()
            self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    with tempfile.TemporaryDirectory(prefix='creator-codex-') as directory:
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        settings = {
            'model_provider': 'creator_probe', 'model_providers.creator_probe.name': 'Local creator probe',
            'model_providers.creator_probe.base_url': f'http://127.0.0.1:{server.server_port}/v1',
            'model_providers.creator_probe.wire_api': 'responses',
            'model_providers.creator_probe.requires_openai_auth': False,
            'mcp_servers.exp_creator.command': sys.executable,
            'mcp_servers.exp_creator.args': ['-m', 'exp_runtime.creator.mcp_server', '--workspace', directory],
            'mcp_servers.exp_creator.required': True, 'features.apps': False, 'features.hooks': False,
            'features.plugins': False, 'features.skip_host_skill_discovery': True,
        }
        args = [codex, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
                '--sandbox', 'read-only', '--json', '--model', 'creator-probe', '-C', directory]
        for key, value in settings.items(): args += ['-c', key + '=' + json.dumps(value)]
        args += ['Inspect the creator MCP schema. Do not read or write any project.']
        try:
            result = subprocess.run(args, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                env=dict(os.environ, NO_PROXY='127.0.0.1,localhost'), timeout=45)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)
    if result.returncode: raise RuntimeError(result.stderr[-2000:])
    if len(requests) != 3: raise AssertionError('Expected two tool calls and one completion')
    catalog = next(t for t in requests[0]['tools'] if t.get('name') == 'mcp__exp_creator')
    definitions = {t['name']: t for t in catalog['tools']}
    for name in ('project_apply_edits', 'project_preview_edits', 'playtest_run_scenario'):
        tool = definitions[name]
        assert len(json.dumps(tool).encode()) < 5000, name
        assert tool['description'], name
    operation = definitions['project_apply_edits']['parameters']['$defs']['Edit']['properties']['resource']
    assert '0–32767' in operation['description'], 'Parameter limit prose was lost'
    outputs = {item['call_id']: item['output'] for item in requests[-1]['input']
               if item.get('type') == 'function_call_output'}
    assert 'choice' in outputs['call_probe_1'] and 'compatibility' in outputs['call_probe_1']
    assert 'invalid_request' in outputs['call_probe_2'] and 'recovery' in outputs['call_probe_2']
    events = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
    calls = [event['item'] for event in events if event.get('type') == 'item.completed'
             and event.get('item', {}).get('type') == 'mcp_tool_call']
    assert [(c['tool'], c['status']) for c in calls] == [('schema_get', 'completed'), ('project_get', 'failed')]
    version = subprocess.run([codex, '--version'], capture_output=True, text=True, check=True).stdout.strip()
    return dict(status='passed', client=version, tools=len(definitions), checks=[
        'Client-visible names, descriptions and compact operation/scenario schemas',
        'Parameter constraints survive as prose', 'Successful schema result and failed-call recovery reach the client',
        'Expected error marked failed', 'No project writes or remote model calls'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codex', default='codex', help='Installed Codex executable (tested with 0.162.1)')
    parser.add_argument('--output', type=Path, help='Optional path for the small verification report')
    args = parser.parse_args()
    report = json.dumps(verify(args.codex), indent=2)
    if args.output: args.output.write_text(report + '\n')
    print(report)
