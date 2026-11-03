#!/usr/bin/env python3
"""Install/verify only BRZ-owned host rules; never flush Docker's chains.

The verifier is also copied into the trusted proxy image. Browser readiness is
based on the live host rules, not a writable attestation file or environment flag.
"""
import argparse
import ipaddress
import json
import shlex
import subprocess
import sys

BRIDGE = 'brz-egress'
SUBNET = '172.29.250.0/24'
PROTECTED = ['0.0.0.0/8', '10.0.0.0/8', '100.64.0.0/10', '127.0.0.0/8',
             '169.254.0.0/16', '172.16.0.0/12', '192.0.0.0/24', '192.0.2.0/24',
             '192.88.99.0/24', '192.168.0.0/16', '198.18.0.0/15',
             '198.51.100.0/24', '203.0.113.0/24', '224.0.0.0/4', '240.0.0.0/4']


def command(args, **kwargs):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=8, **kwargs).stdout


def normalize(line):
    # iptables-save writes netmasks canonically and protocol match modules.
    return shlex.split(line)


def policy(demo, dns):
    egress = [f'-A BRZ-EGRESS -d {dns}/32 -p udp -m udp --dport 53 -j ACCEPT',
              f'-A BRZ-EGRESS -d {dns}/32 -p tcp -m tcp --dport 53 -j ACCEPT',
              f'-A BRZ-EGRESS -d {demo}/32 -p tcp -m tcp --dport 8443 -j ACCEPT',
              '-A BRZ-EGRESS -m addrtype --dst-type LOCAL -j DROP']
    egress += [f'-A BRZ-EGRESS -d {cidr} -j DROP' for cidr in PROTECTED]
    egress += ['-A BRZ-EGRESS -p tcp -m tcp --dport 443 -j ACCEPT', '-A BRZ-EGRESS -j DROP']
    host = [f'-A BRZ-HOST -d {demo}/32 -p tcp -m tcp --dport 8443 -j ACCEPT', '-A BRZ-HOST -j DROP']
    return egress + host


def hooks():
    return [f'-A DOCKER-USER -s {SUBNET} -i {BRIDGE} -j BRZ-EGRESS',
            f'-A INPUT -s {SUBNET} -i {BRIDGE} -j BRZ-HOST']


def validate_ip(value):
    ip = ipaddress.ip_address(value)
    if ip.version != 4 or not ip.is_global:
        raise ValueError('demo IP and resolver must be globally routable IPv4 addresses')
    return str(ip)


def install(demo, dns):
    # Do not replace a live policy while browser proxies own active connections.
    if command(['docker', 'ps', '-q', '--filter', 'label=brz.role=proxy']).strip():
        raise RuntimeError('Stop the worker/browser jobs before replacing the egress policy')
    for chain in ('BRZ-EGRESS', 'BRZ-HOST'):
        subprocess.run(['iptables', '-w', '-N', chain], capture_output=True, timeout=8)
    lines = ['*filter', '-F BRZ-EGRESS', '-F BRZ-HOST', *policy(demo, dns), 'COMMIT', '']
    command(['iptables-restore', '--noflush', '-w'], input='\n'.join(lines))
    for line in hooks():
        args = shlex.split(line)
        check = subprocess.run(['iptables', '-w', '-C', *args[1:]], capture_output=True, timeout=8)
        if check.returncode:
            command(['iptables', '-w', '-I', args[1], '1', *args[2:]])
    for chain in ('FORWARD', 'INPUT'):
        args = ['-i', BRIDGE, '-j', 'DROP']
        if subprocess.run(['ip6tables', '-w', '-C', chain, *args], capture_output=True, timeout=8).returncode:
            command(['ip6tables', '-w', '-I', chain, '1', *args])
    verify(demo, dns)


def verify(demo, dns):
    lines = command(['iptables-save', '-t', 'filter']).splitlines()
    by_chain = {}
    for line in lines:
        if line.startswith('-A '):
            tokens = normalize(line)
            by_chain.setdefault(tokens[1], []).append(tokens)
    expected = policy(demo, dns)
    for chain in ('BRZ-EGRESS', 'BRZ-HOST'):
        wanted = [normalize(x) for x in expected if x.startswith('-A ' + chain + ' ')]
        if by_chain.get(chain) != wanted:
            raise RuntimeError('Missing or changed live host chain: ' + chain)
    for line in hooks():
        rule = normalize(line)
        if not by_chain.get(rule[1]) or by_chain[rule[1]][0] != rule:
            raise RuntimeError('Required rule must be first in chain: ' + rule[1])
    if not by_chain.get('FORWARD') or by_chain['FORWARD'][0] != ['-A', 'FORWARD', '-j', 'DOCKER-USER']:
        raise RuntimeError('Docker iptables DOCKER-USER hook must be first in FORWARD')
    six = command(['ip6tables-save', '-t', 'filter']).splitlines()
    for chain in ('FORWARD', 'INPUT'):
        first = next((normalize(x) for x in six if x.startswith('-A ' + chain + ' ')), None)
        if first != ['-A', chain, '-i', BRIDGE, '-j', 'DROP']:
            raise RuntimeError('Missing first IPv6 drop rule in ' + chain)
    print(json.dumps({'verified': True, 'bridge': BRIDGE, 'subnet': SUBNET,
                      'demo_ip': demo, 'dns': dns, 'ipv6': 'blocked'}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['install', 'verify'])
    parser.add_argument('--demo-ip', required=True)
    parser.add_argument('--dns', default='1.1.1.1')
    args = parser.parse_args()
    try:
        demo, dns = validate_ip(args.demo_ip), validate_ip(args.dns)
        (install if args.mode == 'install' else verify)(demo, dns)
    except Exception as exc:
        print(json.dumps({'verified': False, 'reason': str(exc)}), file=sys.stderr)
        sys.exit(1)
