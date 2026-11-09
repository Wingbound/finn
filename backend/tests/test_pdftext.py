import pytest

from finn.enrich.pdftext import extract_text, get_doc_text, relevant_window
from finn.ingest.nse import NSEUnavailable, PayloadTooLarge
from tests.fakes import FIXTURES, FakeNSE

PDF = FIXTURES / "pdf"
TERMS = ["appoint", "cease", "resign", "retire", "Senior Management", "Brief profile"]


def test_extract_text_reads_pdf():
    assert "Ramesh Iyer" in extract_text((PDF / "hello.pdf").read_bytes())


def test_extract_text_garbage_is_empty():
    assert extract_text(b"not a pdf") == ""


def test_window_keeps_short_text_whole():
    text = (PDF / "106850979.txt").read_text()
    assert len(text) <= 12_000
    assert relevant_window(text, TERMS) == text


def test_window_finds_buried_change():
    text = (PDF / "106846758.txt").read_text()
    out = relevant_window(text, TERMS)
    assert len(out) <= 12_000
    assert "Shuchi Suri" in out
    assert "Chief Sales & Marketing Officer" in out


def test_window_no_hits_takes_head():
    text = "\n".join(f"line {i}" for i in range(5000))
    assert relevant_window(text, ["zzz"], max_chars=500) == text[:500]


def test_get_doc_text_caches(conn):
    fake = FakeNSE({}, {"u": (PDF / "hello.pdf").read_bytes()})
    a = get_doc_text(conn, fake, "u")
    b = get_doc_text(conn, fake, "u")
    assert "Ramesh Iyer" in a
    assert a == b
    assert fake.byte_calls == ["u"]


def test_get_doc_text_caches_empty_result(conn):
    fake = FakeNSE({}, {"u": b"not a pdf"})
    assert get_doc_text(conn, fake, "u") == ""
    assert get_doc_text(conn, fake, "u") == ""
    assert fake.byte_calls == ["u"]


def test_get_doc_text_fetch_error_not_cached(conn):
    fake = FakeNSE({}, {})
    with pytest.raises(NSEUnavailable):
        get_doc_text(conn, fake, "u")
    fake.files["u"] = (PDF / "hello.pdf").read_bytes()
    assert "Ramesh Iyer" in get_doc_text(conn, fake, "u")


def test_get_doc_text_oversize_cached_empty_never_refetched(conn):
    class Big(FakeNSE):
        def fetch_bytes(self, url, max_bytes=25_000_000):
            self.byte_calls.append(url)
            raise PayloadTooLarge(f"{url} exceeds {max_bytes} bytes")

    fake = Big({}, {})
    assert get_doc_text(conn, fake, "u") == ""
    assert get_doc_text(conn, fake, "u") == ""
    assert fake.byte_calls == ["u"]
