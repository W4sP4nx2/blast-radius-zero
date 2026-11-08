"""URL admission is exact-name validation, not a substitute for egress filtering."""
import pytest

from brz.policy import research_url


@pytest.mark.parametrize("url", [
    "https://news.ycombinator.com/",
    "https://news.ycombinator.com:443/item?id=1#comments",
    "HTTPS://NEWS.YCOMBINATOR.COM/newest",
])
def test_approved_https_destination_preserves_url(url):
    assert research_url(url, ["news.ycombinator.com"]) == url


def test_idna_hostname_matches_only_its_configured_ascii_name():
    url = "https://b\u00fccher.example/article"
    assert research_url(url, ["xn--bcher-kva.example"]) == url
    with pytest.raises(ValueError):
        research_url(url, ["books.example"])


@pytest.mark.parametrize("url", [
    "http://news.ycombinator.com/",
    "ftp://news.ycombinator.com/",
    "file:///etc/passwd",
    "javascript:alert(1)",
    "//news.ycombinator.com/",
    "https:///missing-host",
    "https://news.ycombinator.com:8443/",
    "https://news.ycombinator.com:80/",
    "https://news.ycombinator.com:0/",
    "https://news.ycombinator.com:not-a-port/",
    "https://news.ycombinator.com:99999/",
])
def test_only_https_on_port_443_is_admitted(url):
    with pytest.raises(ValueError):
        research_url(url, ["news.ycombinator.com"])


@pytest.mark.parametrize("url", [
    "https://user@news.ycombinator.com/",
    "https://user:password@news.ycombinator.com/",
    "https://@news.ycombinator.com/",
    "https://:password@news.ycombinator.com/",
])
def test_any_userinfo_is_rejected(url):
    with pytest.raises(ValueError):
        research_url(url, ["news.ycombinator.com"])


@pytest.mark.parametrize("host", [
    "127.0.0.1",
    "169.254.169.254",
    "10.0.0.1",
    "192.168.1.1",
    "[::1]",
    "[::ffff:127.0.0.1]",
    "1.1.1.1",
])
def test_ip_literals_are_rejected_even_if_listed_as_domains(host):
    with pytest.raises(ValueError):
        research_url(f"https://{host}/", [host.strip("[]")])


@pytest.mark.parametrize("host", [
    "news.ycombinator.com.evil.example",
    "sub.news.ycombinator.com",
    "news.ycombinator.com.",
    "evil.example",
    "localhost",
    "metadata.google.internal",
    "private.internal",
    "2130706433",
    "0x7f000001",
])
def test_allowlist_does_not_expand_to_subdomains_suffixes_or_aliases(host):
    with pytest.raises(ValueError):
        research_url(f"https://{host}/", ["news.ycombinator.com"])


def test_url_admission_does_not_claim_to_validate_dns_answers():
    # The administrator supplies names; Squid and host filtering constrain the
    # actual resolved socket destination, including an approved name rebinding.
    url = "https://approved.example/path"
    assert research_url(url, ["approved.example"]) == url
