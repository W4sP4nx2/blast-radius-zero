import pytest

from brz.critic import validate_code


@pytest.mark.parametrize(
    "source,name",
    [
        ("import socket", "socket"),
        ("import urllib.request", "urllib.request"),
        ("from http.client import HTTPSConnection", "http.client"),
        ("import subprocess as sp", "subprocess"),
        ("from ctypes import CDLL", "ctypes"),
    ],
)
def test_critic_blocks_forbidden_import_roots(source, name):
    result = validate_code(source)
    assert not result.is_approved
    assert result.verdict == "blocked"
    assert any(name in error for error in result.errors)


def test_critic_allows_offline_standard_library_code():
    source = "import csv, json, os, pathlib, sys\nprint(json.dumps({'cwd': os.getcwd()}))"
    result = validate_code(source)
    assert result.is_approved
    assert result.sanitized_code == source


def test_critic_classifies_syntax_as_repairable_without_executing():
    result = validate_code("for")
    assert not result.is_approved
    assert result.verdict == "repairable"
    assert result.sanitized_code is None


def test_critic_measures_utf8_bytes():
    result = validate_code("#" + "é" * (32 * 1024 + 1))
    assert not result.is_approved
    assert result.verdict == "blocked"


@pytest.mark.parametrize(
    "source,name",
    [
        ("import os\nos.system('id')", "os.system"),
        ("import os as operating_system\noperating_system.popen('id')", "os.popen"),
        ("exec('print(1)')", "exec"),
        ("__import__('socket')", "__import__"),
    ],
)
def test_critic_blocks_dangerous_calls(source, name):
    result = validate_code(source)
    assert not result.is_approved
    assert result.verdict == "blocked"
    assert any(name in error for error in result.errors)
