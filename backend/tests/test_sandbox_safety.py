import io
import json
import tarfile
import pytest
from brz.config import Settings
from brz.sandbox import SandboxRunner, pack_files, read_archive


def archive(name, body=b"{}", kind=tarfile.REGTYPE, link=""):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w") as tar:
        entry = tarfile.TarInfo(name)
        entry.type, entry.linkname, entry.size = kind, link, len(body)
        tar.addfile(entry, io.BytesIO(body) if kind == tarfile.REGTYPE else None)
    return [output.getvalue()]


@pytest.mark.parametrize("name", ["../outside.json", "/root/file.json", "artifacts/../outside.json", "artifacts/sub/file.json"])
def test_artifact_paths_are_never_extracted(name):
    with pytest.raises(ValueError):
        read_archive(archive(name))


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE])
def test_artifact_links_and_special_files_rejected(kind):
    with pytest.raises(ValueError):
        read_archive(archive("artifacts/result.json", kind=kind, link="/etc/passwd"))


def test_archive_limits_type_and_signature():
    assert read_archive(archive("artifacts/result.json")) == {"result.json": b"{}"}
    with pytest.raises(ValueError):
        read_archive(archive("artifacts/result.html"))
    with pytest.raises(ValueError):
        read_archive(archive("artifacts/result.png"))
    with pytest.raises(ValueError):
        read_archive(archive("artifacts/result.json", b"x" * (2 * 1024 * 1024 + 1)))


def test_inputs_use_only_fixed_filenames():
    with pytest.raises(ValueError):
        pack_files({"../x": b"bad"})
    assert pack_files({"input.csv": b"x\n1\n"})


def test_proxy_configuration_has_no_broad_allow_and_exact_demo_exception():
    config = Settings(demo_ip="8.8.4.4", demo_url="https://demo.example.com:8443")
    text = SandboxRunner(config)._proxy_configuration("172.20.0.2").decode()
    assert "dstdomain -n news.ycombinator.com" in text
    assert "http_access deny !CONNECT" in text
    assert "http_access allow worker CONNECT demo demo_port" in text
    assert text.index("http_access deny !research") < text.index("http_access deny private")
    assert text.index("http_access deny private") < text.index("http_access allow worker CONNECT research")
    assert "allow localnet" not in text
    assert text.strip().endswith("http_access deny all")


def test_sandbox_options_never_inherit_proxy_credentials_or_host_mounts():
    runner = SandboxRunner(Settings())
    code, browser = runner._common(), runner._common(browser=True)
    assert code["mem_limit"] == code["memswap_limit"] == "256m"
    assert browser["mem_limit"] == browser["memswap_limit"] == "512m"
    for options in (code, browser):
        assert options["use_config_proxy"] is False
        assert options["cap_drop"] == ["ALL"]
        assert options["user"] != "0:0"
        assert options["read_only"]
        assert "binds" not in options and "volumes" not in options
        assert "VULTR_API_KEY" not in options["environment"]
        assert "no-new-privileges:true" in options["security_opt"]
