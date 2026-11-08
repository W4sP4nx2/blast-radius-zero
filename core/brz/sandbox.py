"""Trusted Docker coordinator. No caller-supplied Docker options are accepted."""
from __future__ import annotations

from dataclasses import dataclass, field
import base64
import io
import ipaddress
import json
import logging
from pathlib import Path, PurePosixPath
import re
import socket
import tarfile
import threading
import time
from typing import Callable
from urllib.parse import urlsplit
import uuid

import docker
from docker.errors import DockerException, NotFound
from docker.types import LogConfig

logger = logging.getLogger(__name__)
MIB = 1024 * 1024
LABELS = {'brz.managed': 'true', 'brz.owner': 'coordinator'}
MAX_ARTIFACTS = 8 * MIB
MAX_LOGS = MIB
PROTECTED = ['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
             '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
             '192.88.99.0/24', '192.168.0.0/16', '198.18.0.0/15',
             '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4']


@dataclass
class RunResult:
    status: str
    output: str = ''
    error: str = ''
    artifacts: dict[str, bytes] = field(default_factory=dict)
    details: dict = field(default_factory=dict)


def pack_files(files: dict[str, bytes], *, uid=10001, mode=0o600) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w') as archive:
        for name, content in files.items():
            if '/' in name or name.startswith('.'):
                raise ValueError('Only fixed input file names are accepted')
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.uid, info.gid = len(content), mode, uid, uid
            archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def read_archive(chunks, *, limit=MAX_ARTIFACTS, root='artifacts') -> dict[str, bytes]:
    """Parse bounded data; do not ever extract an untrusted archive to the host."""
    buffer = bytearray()
    for chunk in chunks:
        buffer.extend(chunk)
        if len(buffer) > limit + 128 * 1024:
            raise ValueError('Artifact archive exceeds size limit')
    result, total = {}, 0
    with tarfile.open(fileobj=io.BytesIO(buffer), mode='r:') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk():
                raise ValueError('Unsafe artifact archive path or link')
            if member.isdir():
                continue
            if not member.isfile() or len(path.parts) != 2 or path.parts[0] != root:
                raise ValueError('Artifacts must be regular files directly inside the artifact directory')
            if path.suffix.lower() not in {'.csv', '.json', '.png', '.jpg', '.jpeg'}:
                raise ValueError('Unsupported artifact format')
            if member.size > 2 * MIB or member.size < 0:
                raise ValueError('Artifact exceeds individual size limit')
            total += member.size
            if total > limit or len(result) >= 16:
                raise ValueError('Artifact quota exceeded')
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError('Missing artifact bytes')
            content = stream.read(member.size + 1)
            if len(content) != member.size:
                raise ValueError('Invalid artifact size')
            if path.suffix.lower() == '.png' and not content.startswith(b'\x89PNG\r\n\x1a\n'):
                raise ValueError('Invalid PNG artifact')
            if path.suffix.lower() in {'.jpg', '.jpeg'} and not content.startswith(b'\xff\xd8\xff'):
                raise ValueError('Invalid JPEG artifact')
            result[path.name] = content
    return result


class SandboxRunner:
    def __init__(self, config):
        self.config = config
        self.client = None
        self._preflight_cache = None
        self._preflight_at = 0.0

    def _docker(self):
        if self.client is None:
            self.client = docker.from_env(timeout=getattr(self.config, 'docker_timeout', 5))
        return self.client

    @staticmethod
    def _close_channel(channel):
        """Close the owning HTTP response, not only its hijacked SocketIO.

        Closing SocketIO alone leaves HTTPResponse.fp dangling on Python 3.14.
        Shutdown first also releases a concurrent streaming reader.
        """
        response = getattr(channel, '_response', None)
        if response is None:
            try:
                channel.close()
            except (OSError, ValueError):
                pass
            return
        try:
            fp = response.raw._fp.fp
            raw = getattr(fp, 'raw', fp)
            raw = getattr(raw, '_sock', raw)
            if raw is not None:
                try:
                    raw.shutdown(socket.SHUT_RDWR)
                except (OSError, AttributeError):
                    pass
        except AttributeError:
            pass
        try:
            response.close()
        except (OSError, ValueError):
            pass

    def _common(self, *, browser=False):
        amount = 512 if browser else 256
        options = dict(
            user='10001:10001', working_dir='/tmp', read_only=True,
            mem_limit=f'{amount}m', memswap_limit=f'{amount}m',
            nano_cpus=1_000_000_000 if browser else 500_000_000,
            pids_limit=256 if browser else 64,
            cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
            tmpfs={'/tmp': f'rw,nosuid,nodev,size={128 if browser else 64}m,mode=1777'},
            shm_size='128m' if browser else '16m', ipc_mode='private',
            environment={'HOME': '/tmp/home' if browser else '/tmp',
                         'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1'},
            use_config_proxy=False,
            command=['python', '-u', '-c', 'import time; time.sleep(300)'],
            entrypoint=[], init=True,
            labels={**LABELS, 'brz.role': 'browser' if browser else 'code'},
            log_config=LogConfig(type='json-file', config={'max-size': '1m', 'max-file': '1'}),
        )
        if browser:
            profile = Path(__file__).with_name('seccomp_profile.json')
            if not profile.exists():
                profile = Path(__file__).resolve().parents[2] / 'sandbox' / 'browser' / 'seccomp_profile.json'
            options['security_opt'].append('seccomp=' + json.dumps(json.loads(profile.read_text())))
        return options

    def _inspect_enforcement(self, container, *, browser):
        container.reload()
        host = container.attrs['HostConfig']
        expected_memory = (512 if browser else 256) * MIB
        checks = [host.get('Memory') == expected_memory,
                  host.get('MemorySwap') == expected_memory,
                  host.get('NanoCpus') == (1_000_000_000 if browser else 500_000_000),
                  host.get('PidsLimit') == (256 if browser else 64),
                  host.get('ReadonlyRootfs') is True,
                  container.attrs['Config'].get('User') == '10001:10001',
                  'ALL' in [x.upper() for x in host.get('CapDrop', [])],
                  any('no-new-privileges' in x for x in host.get('SecurityOpt', [])),
                  not host.get('Privileged'), not host.get('Binds'),
                  host.get('IpcMode') == 'private']
        if not browser:
            checks.append(host.get('NetworkMode') == 'none')
        if not all(checks):
            raise RuntimeError('Docker did not apply required sandbox restrictions')

    def _stage_inputs(self, container, files):
        """Docker archive APIs do not reliably see container tmpfs mounts.

        A fixed isolated Python helper receives length-framed JSON over exec stdin.
        No shell, host mount, caller-selected path, or large command-line argument.
        """
        if set(files) - {'input.csv', 'input.json', 'squid.conf'}:
            raise ValueError('Unsupported input filename')
        payload = json.dumps({name: base64.b64encode(value).decode() for name, value in files.items()}).encode()
        if len(payload) > 4 * MIB:
            raise ValueError('Staged input exceeds limit')
        script = """import base64,json,pathlib,sys
n=int(sys.stdin.buffer.readline())
if not 0<=n<=4194304: raise ValueError('input size')
raw=sys.stdin.buffer.read(n)
if len(raw)!=n: raise ValueError('incomplete input')
items=json.loads(raw)
if set(items)-{'input.csv','input.json','squid.conf'}: raise ValueError('input name')
for name,value in items.items():
    path=pathlib.Path('/tmp')/name
    path.write_bytes(base64.b64decode(value,validate=True))
    path.chmod(0o600)
"""
        # Proxy uses its own unprivileged UID; the image/user is trusted configuration.
        uid = '13:13' if 'squid.conf' in files else '10001:10001'
        execution = self._docker().api.exec_create(container.id, ['python3', '-I', '-c', script],
                                                   user=uid, stdin=True, stdout=False, stderr=True)
        channel = self._docker().api.exec_start(execution['Id'], socket=True)
        try:
            raw_socket = getattr(channel, '_sock', channel)
            raw_socket.settimeout(5)
            raw_socket.sendall(str(len(payload)).encode() + b'\n' + payload)
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                state = self._docker().api.exec_inspect(execution['Id'])
                if not state['Running']:
                    if state.get('ExitCode') != 0:
                        raise RuntimeError('Sandbox input staging failed')
                    return
                time.sleep(0.02)
            raise RuntimeError('Sandbox input staging deadline exceeded')
        finally:
            self._close_channel(channel)

    def _get_file(self, container, path, *, limit=128 * 1024):
        if path != '/tmp/brz-result.json':
            raise ValueError('Unsupported result path')
        script = "import pathlib,sys; p=pathlib.Path('/tmp/brz-result.json'); assert not p.is_symlink(); sys.stdout.buffer.write(p.open('rb').read(131073))"
        execution = self._docker().api.exec_create(container.id, ['python', '-I', '-c', script], user='10001:10001', stdout=True, stderr=False)
        chunks = self._docker().api.exec_start(execution['Id'], stream=True)
        data = bytearray()
        finished = False
        try:
            for chunk in chunks:
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError('Result data exceeds limit')
            finished = True
            if self._docker().api.exec_inspect(execution['Id']).get('ExitCode') != 0:
                raise ValueError('Result could not be read')
            return bytes(data)
        finally:
            self._close_channel(chunks)

    def _collect_artifacts(self, container):
        script = """import os,sys,tarfile
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|',dereference=False) as archive:
    if os.path.lexists('/tmp/artifacts'): archive.add('/tmp/artifacts',arcname='artifacts')
"""
        execution = self._docker().api.exec_create(container.id, ['python', '-I', '-c', script], user='10001:10001', stdout=True, stderr=False)
        chunks = self._docker().api.exec_start(execution['Id'], stream=True)
        finished = False
        try:
            result = read_archive(chunks)
            finished = True
            if self._docker().api.exec_inspect(execution['Id']).get('ExitCode') != 0:
                raise ValueError('Artifact transfer failed')
            return result
        finally:
            self._close_channel(chunks)

    def _run_exec(self, container, command, emit, cancelled, *, browser=False, inputs=None):
        """Run an exec inside a live bounded container, allowing tmpfs collection.

        tmpfs disappears when the container stops. The base process stays alive
        until the host captures files, then is forcibly removed on every path.
        """
        client = self._docker()
        result = RunResult('infrastructure_error')
        thread = None
        stream = None
        try:
            container.reload()
            if not container.attrs.get('State', {}).get('Running'):
                container.start()
            self._inspect_enforcement(container, browser=browser)
            if inputs:
                self._stage_inputs(container, inputs)
            if not browser:
                # User code has only this directory for returned files.
                setup = container.exec_run(['mkdir', '-p', '/tmp/artifacts'], user='10001:10001')
                if setup.exit_code:
                    raise RuntimeError('Scratch directory initialization failed')
            execution = client.api.exec_create(container.id, command, user='10001:10001', workdir='/tmp', stdout=True, stderr=True)
            execution_id = execution['Id']
            started = time.monotonic()
            stream = client.api.exec_start(execution_id, stream=True, demux=True)
            pieces = []
            state = {'bytes': 0, 'events': 0, 'overflow': False, 'stream_error': False}

            def consume():
                try:
                    for stdout, stderr in stream:
                        for kind, chunk in (('stdout', stdout), ('stderr', stderr)):
                            if not chunk:
                                continue
                            remaining = MAX_LOGS - state['bytes']
                            kept = chunk[:max(0, remaining)]
                            state['bytes'] += len(chunk)
                            state['events'] += 1
                            if kept and not state['overflow']:
                                text = kept.decode('utf-8', errors='replace')
                                # Terminal control characters do not become UI instructions.
                                text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
                                pieces.append(text)
                                emit(kind, {'text': text})
                            if state['bytes'] > MAX_LOGS or state['events'] > 2048:
                                state['overflow'] = True
                                # Keep draining (discarding) until kill closes the
                                # exec stream. Stopping reads can deadlock daemon
                                # termination on backpressured stdout pipes.
                except Exception:
                    state['stream_error'] = True

            thread = threading.Thread(target=consume, daemon=True)
            thread.start()
            limit = 30 if browser else 10
            forced = None
            info = {}
            while True:
                if cancelled():
                    forced = 'cancelled'
                elif state['overflow']:
                    forced = 'output_limit'
                elif time.monotonic() - started >= limit:
                    forced = 'timed_out'
                if forced:
                    container.kill()
                    break
                info = client.api.exec_inspect(execution_id)
                if not info.get('Running'):
                    break
                container.reload()
                if not container.attrs.get('State', {}).get('Running'):
                    break
                time.sleep(0.05)
            thread.join(timeout=1)
            container.reload()
            oom = bool(container.attrs.get('State', {}).get('OOMKilled'))
            exit_code = client.api.exec_inspect(execution_id).get('ExitCode')
            result.output = ''.join(pieces)
            result.details = {'exit_code': exit_code, 'oom_killed': oom,
                              'duration_ms': round((time.monotonic() - started) * 1000),
                              'container_id': container.short_id}
            result.status = forced or ('oom_killed' if oom else ('succeeded' if exit_code == 0 else 'failed'))
            if result.status == 'succeeded' and state['stream_error']:
                result.status = 'infrastructure_error'
                result.error = 'Execution output stream was interrupted'
            if result.status == 'succeeded':
                if browser:
                    result.details.update(json.loads(self._get_file(container, '/tmp/brz-result.json')))
                try:
                    result.artifacts = self._collect_artifacts(container)
                except NotFound:
                    result.artifacts = {}
                except ValueError as exc:
                    result.status, result.error = 'output_limit', str(exc)
            if result.status != 'succeeded' and not result.error:
                result.error = {'timed_out': f'Execution exceeded {limit} seconds',
                                'cancelled': 'Task cancelled',
                                'output_limit': 'Output limit exceeded',
                                'oom_killed': 'Container memory limit exceeded'}.get(result.status, 'Program exited with a non-zero status')
        except Exception as exc:
            logger.exception('Container execution failed')
            result.status, result.error = 'infrastructure_error', 'Container execution unavailable: ' + type(exc).__name__
        finally:
            if stream is not None:
                try:
                    self._close_channel(stream)
                except Exception:
                    pass
            try:
                container.remove(force=True, v=True)
            except NotFound:
                pass
            except Exception:
                logger.exception('Container cleanup failed')
                result.status = 'infrastructure_error'
                result.error = 'Sandbox cleanup failed; operator attention required'
                result.details['cleanup_failed'] = True
        return result

    def run_code(self, code: str, upload: bytes | None, emit: Callable, cancelled: Callable) -> RunResult:
        if len(code.encode()) > 64 * 1024 or (upload is not None and len(upload) > 2 * MIB):
            return RunResult('failed', error='Payload exceeds sandbox input limits')
        try:
            emit('status', {'message': 'Starting isolated Python container', 'phase': 'container_start'})
            container = self._docker().containers.create(self.config.python_image, network_mode='none', **self._common())
            return self._run_exec(container, ['python', '-u', '-I', '-c', code], emit, cancelled,
                                  inputs={'input.csv': upload} if upload is not None else {})
        except DockerException as exc:
            logger.exception('Cannot create Python sandbox')
            return RunResult('infrastructure_error', error='Docker sandbox unavailable: ' + type(exc).__name__)

    def _verify_firewall(self):
        demo = ipaddress.ip_address(self.config.demo_ip)
        dns = ipaddress.ip_address(self.config.egress_dns)
        if demo.version != 4 or dns.version != 4 or not demo.is_global or not dns.is_global:
            raise ValueError('Configure global IPv4 DEMO_IP and EGRESS_DNS')
        bridge = self._docker().networks.get('brz-egress')
        if bridge.attrs.get('EnableIPv6') or bridge.attrs.get('Options', {}).get('com.docker.network.bridge.name') != 'brz-egress':
            raise RuntimeError('Unexpected proxy egress network configuration')
        subnets = [x.get('Subnet') for x in bridge.attrs.get('IPAM', {}).get('Config', [])]
        if subnets != ['172.29.250.0/24']:
            raise RuntimeError('Unexpected proxy egress subnet')
        probe = self._docker().containers.create(
            self.config.proxy_image,
            command=['python3', '/opt/brz/firewall_policy.py', 'verify', '--demo-ip', str(demo), '--dns', str(dns)],
            entrypoint=[], user='0:0', network_mode='host', cap_drop=['ALL'], cap_add=['NET_ADMIN'],
            security_opt=['no-new-privileges:true'], read_only=True, mem_limit='64m', memswap_limit='64m',
            nano_cpus=100_000_000, pids_limit=32, use_config_proxy=False,
            labels={**LABELS, 'brz.role': 'firewall_verifier'},
            log_config=LogConfig(type='json-file', config={'max-size': '64k', 'max-file': '1'}))
        try:
            probe.start()
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                probe.reload()
                if not probe.attrs['State']['Running']:
                    if probe.attrs['State']['ExitCode'] != 0:
                        raise RuntimeError('Required host destination-filtering policy is missing or changed')
                    data = json.loads(probe.logs(stdout=True, stderr=False).decode())
                    if not data.get('verified'):
                        raise RuntimeError('Host policy verification failed')
                    return
                time.sleep(0.1)
            raise RuntimeError('Host firewall verification timed out')
        finally:
            probe.remove(force=True, v=True)

    def _proxy_configuration(self, browser_ip):
        domains = self.config.browser_domains
        if not domains or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', x) or '..' in x for x in domains):
            raise ValueError('Invalid administrator browser domain allowlist')
        demo = urlsplit(self.config.demo_url)
        if demo.scheme != 'https' or demo.port != 8443 or not demo.hostname or not re.fullmatch(r'[a-zA-Z0-9.-]+', demo.hostname):
            raise ValueError('Demo URL must use HTTPS on dedicated port 8443')
        # No distribution default "allow localnet" rules survive this replacement.
        return '\n'.join([
            'http_port 3128', 'visible_hostname brz-egress', 'pid_filename /tmp/squid.pid',
            'cache_effective_user proxy', 'cache_effective_group proxy',
            'cache deny all', 'cache_mem 0 MB', 'maximum_object_size 0 KB',
            'cache_log /dev/stderr', 'logfile_rotate 0', 'coredump_dir /tmp',
            'logformat brz BRZ|%>a|%Ss/%>Hs|%rm|%ru', 'access_log stdio:/dev/stdout brz',
            'forwarded_for delete', 'via off', 'client_db on',
            'connect_timeout 8 seconds', 'request_timeout 15 seconds', 'read_timeout 20 seconds',
            'shutdown_lifetime 0 seconds', 'request_header_max_size 16 KB',
            f'dns_nameservers {self.config.egress_dns}',
            f'acl worker src {browser_ip}/32', 'acl CONNECT method CONNECT',
            'acl manager proto cache_object', 'acl excess maxconn 16',
            'acl https_port port 443', 'acl demo_port port 8443',
            'acl research dstdomain -n ' + ' '.join(domains),
            'acl demo dstdomain -n ' + demo.hostname,
            'acl private dst ' + ' '.join(PROTECTED) + ' ::/128 ::1/128 fc00::/7 fe80::/10 ff00::/8',
            'http_access deny manager', 'http_access deny !worker', 'http_access deny excess',
            'http_access deny !CONNECT',
            # This exact exception reaches only the separate project-owned listener.
            'http_access allow worker CONNECT demo demo_port',
            # Reject unapproved names before DNS-dependent destination ACLs.
            # Otherwise even denied hostnames could leak data through DNS queries.
            'http_access deny !research', 'http_access deny !https_port',
            'http_access deny private',
            'http_access allow worker CONNECT research https_port',
            'http_access deny all', '']).encode()

    def run_browser(self, plan: dict, emit: Callable, cancelled: Callable) -> RunResult:
        client, network, proxy, browser = self._docker(), None, None, None
        result = RunResult('infrastructure_error')
        try:
            self._verify_firewall()  # Live check before every browser container.
            kind = plan.get('kind')
            if kind not in {'research', 'prepare_form', 'submit_form', 'metadata_probe'}:
                raise ValueError('Unsupported browser operation')
            url = urlsplit(plan.get('url', ''))
            if url.username is not None or url.password is not None or not url.hostname:
                raise ValueError('Invalid browser URL')
            if kind == 'research' and (url.scheme != 'https' or (url.port or 443) != 443 or url.hostname not in self.config.browser_domains):
                raise ValueError('Research destination is not allowlisted')
            if kind in {'prepare_form', 'submit_form'} and plan['url'].rstrip('/') != self.config.demo_url.rstrip('/'):
                raise ValueError('Forms may only target the project-owned demo service')
            if kind == 'metadata_probe' and plan['url'] not in {'http://169.254.169.254/', 'http://169.254.169.254/v1/identity/token'}:
                raise ValueError('Invalid metadata test destination')
            name = 'brz-run-' + uuid.uuid4().hex[:16]
            emit('status', {'message': 'Creating isolated browser network and trusted proxy', 'phase': 'container_start'})
            network = client.networks.create(name, driver='bridge', internal=True, enable_ipv6=False,
                options={'com.docker.network.bridge.gateway_mode_ipv4': 'isolated',
                         'com.docker.network.bridge.enable_ip_masquerade': 'false'},
                labels={**LABELS, 'brz.ephemeral': 'true'})
            browser = client.containers.create(self.config.browser_image, network=name, dns=['127.0.0.1'], **self._common(browser=True))
            browser.reload()
            browser_ip = browser.attrs['NetworkSettings']['Networks'][name]['IPAddress']
            # Addresses are assigned at start by some Engine versions.
            if not browser_ip:
                browser.start()
                browser.reload()
                browser_ip = browser.attrs['NetworkSettings']['Networks'][name]['IPAddress']
            proxy = client.containers.create(self.config.proxy_image, network='brz-egress',
                entrypoint=[], command=['python3', '-u', '-c', 'import time; time.sleep(300)'],
                user='13:13', read_only=True, cap_drop=['ALL'], security_opt=['no-new-privileges:true'],
                mem_limit='128m', memswap_limit='128m', nano_cpus=100_000_000, pids_limit=64,
                tmpfs={'/tmp': 'rw,nosuid,nodev,size=16m,mode=1777'},
                use_config_proxy=False, environment={},
                labels={**LABELS, 'brz.role': 'proxy'},
                log_config=LogConfig(type='json-file', config={'max-size': '1m', 'max-file': '1'}))
            network.connect(proxy)
            proxy.start()
            proxy.reload()
            proxy_ip = proxy.attrs['NetworkSettings']['Networks'][name]['IPAddress']
            configuration = self._proxy_configuration(browser_ip)
            self._stage_inputs(proxy, {'squid.conf': configuration})
            # Squid is the only process producing trusted proxy access logs.
            started = client.api.exec_create(proxy.id, ['/usr/sbin/squid', '-N', '-f', '/tmp/squid.conf'], user='13:13')
            proxy_stream = client.api.exec_start(started['Id'], stream=True, demux=False)
            proxy_log = bytearray()

            def read_proxy():
                try:
                    for chunk in proxy_stream:
                        if len(proxy_log) < MAX_LOGS:
                            proxy_log.extend(chunk[:MAX_LOGS - len(proxy_log)])
                except Exception:
                    pass

            proxy_thread = threading.Thread(target=read_proxy, daemon=True)
            proxy_thread.start()
            time.sleep(0.4)
            if not client.api.exec_inspect(started['Id']).get('Running'):
                raise RuntimeError('Trusted proxy failed to start')
            inputs = {'input.json': json.dumps({**plan, 'proxy': f'http://{proxy_ip}:3128'}).encode()}
            # _run_exec handles already-started browser containers as well.
            result = self._run_exec(browser, ['python', '-u', '/opt/brz/browser.py'], emit, cancelled, browser=True, inputs=inputs)
            browser = None
            time.sleep(0.1)
            denied = []
            for line in proxy_log.decode(errors='replace').splitlines():
                fields = line.split('|', 4)
                if len(fields) != 5 or fields[0] != 'BRZ' or fields[1] != browser_ip or fields[2] != 'TCP_DENIED/403':
                    continue
                target = fields[4][:2048]
                metadata = urlsplit(target if '://' in target else 'http://' + target).hostname == '169.254.169.254'
                event = {'rule': 'cloud_metadata' if metadata else 'browser_egress',
                         'message': 'BLOCKED: Cloud Metadata Access Denied' if metadata else 'BLOCKED: Browser destination denied',
                         'target': target, 'enforcement': 'trusted_squid_access_log'}
                denied.append(event)
                emit('policy', event)
            if denied:
                result.details['policy_denials'] = denied
                if result.status == 'failed':
                    result.status, result.error = 'blocked', denied[-1]['message']
            if kind == 'metadata_probe' and not denied:
                # Never imply containment from a mere timeout or Python traceback.
                result.status, result.error = 'infrastructure_error', 'Metadata test did not produce verified proxy-denial evidence'
                result.artifacts = {}
            try:
                self._close_channel(proxy_stream)
            except Exception:
                pass
        except Exception as exc:
            logger.exception('Browser sandbox unavailable')
            result.status, result.error = 'infrastructure_error', 'Browser containment preflight failed: ' + str(exc)
        finally:
            for resource in (browser, proxy):
                if resource is not None:
                    try:
                        resource.remove(force=True, v=True)
                    except NotFound:
                        pass
                    except Exception:
                        logger.exception('Browser container cleanup failed')
                        result.status, result.error = 'infrastructure_error', 'Browser cleanup failed'
                        result.details['cleanup_failed'] = True
            if network is not None:
                try:
                    network.remove()
                except Exception:
                    logger.exception('Browser network cleanup failed')
                    result.status, result.error = 'infrastructure_error', 'Browser network cleanup failed'
                    result.details['cleanup_failed'] = True
        return result

    def preflight(self) -> dict:
        if self._preflight_cache and time.monotonic() - self._preflight_at < 30:
            return self._preflight_cache.copy()
        report = {'ready': False, 'browser_ready': False, 'reason': '', 'browser_reason': ''}
        try:
            client = self._docker()
            info = client.info()
            if info.get('OSType') != 'linux':
                raise RuntimeError('Linux Docker Engine required')
            for feature in ('MemoryLimit', 'SwapLimit', 'CpuCfsQuota', 'PidsLimit'):
                if not info.get(feature):
                    raise RuntimeError('Required Docker resource control unavailable: ' + feature)
            if not any('seccomp' in value for value in info.get('SecurityOptions', [])):
                raise RuntimeError('Docker seccomp support required')
            client.images.get(self.config.python_image)
            report['ready'] = True
            try:
                if int(client.version()['Version'].split('.')[0]) < 28:
                    raise RuntimeError('Docker Engine 28+ required for isolated gateway mode')
                client.images.get(self.config.browser_image)
                client.images.get(self.config.proxy_image)
                self._verify_firewall()
                # Fail closed if the actual Chromium sandbox cannot launch on this host.
                probe = client.containers.create(self.config.browser_image, network_mode='none', **self._common(browser=True))
                result = self._run_exec(probe, ['python', '-u', '/opt/brz/browser.py'], lambda *_: None,
                    lambda: False, browser=True, inputs={'input.json': json.dumps({'kind': 'preflight', 'proxy': 'http://127.0.0.1:9'}).encode()})
                if result.status != 'succeeded' or not result.details.get('sandbox_enabled'):
                    raise RuntimeError('Chromium sandbox startup probe failed')
                report['browser_ready'] = True
            except Exception as exc:
                report['browser_reason'] = str(exc)
        except Exception as exc:
            report['reason'] = 'Docker containment unavailable: ' + str(exc)
        self._preflight_cache, self._preflight_at = report.copy(), time.monotonic()
        return report

    def reap(self):
        """One coordinator owns these labels. Call before accepting new tasks."""
        client = self._docker()
        for container in client.containers.list(all=True, filters={'label': ['brz.managed=true', 'brz.owner=coordinator']}):
            container.remove(force=True, v=True)
        for network in client.networks.list(filters={'label': ['brz.ephemeral=true', 'brz.owner=coordinator']}):
            network.remove()
