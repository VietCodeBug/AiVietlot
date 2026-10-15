from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
import pytest

from mega_collector.source import (
    LATEST_URL, MinhNgocSource, SourceError, parse_minhngoc, parse_vietmy, safe_url,
)


FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 10, 14, 20, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))


def real_html():
    return (FIXTURES / "minhngoc-index.html").read_text(encoding="utf-8")


def first_block_html(change=None):
    soup = BeautifulSoup(real_html(), "html.parser")
    for block in soup.select(".boxkqxsdientoan")[1:]:
        block.decompose()
    if change:
        change(soup.select_one(".box-result-detail"))
    return str(soup)


def parse(html, now=NOW):
    return parse_minhngoc(html, LATEST_URL, now=now)


def test_real_latest_fixture_preserves_canonical_links_and_navigation():
    page = parse(real_html())
    assert not page.issues
    assert not page.pending
    assert [r["draw_id"] for r in page.records] == list(range(1575, 1565, -1))
    latest = page.records[0]
    assert latest["draw_date"] == "2026-10-14"
    assert [latest[f"n{i}"] for i in range(1, 7)] == [6, 16, 19, 21, 34, 43]
    assert latest["source_name"] == "minhngoc"
    assert latest["verification_status"] == "secondary"
    assert latest["source_url"].endswith("/14-10-2026.html")
    assert page.older_url.endswith("/23-09-2026.html")
    assert page.first_url.endswith("/20-07-2016.html")


@pytest.mark.parametrize("numbers", [
    ["06", "16", "19", "21", "34"],
    ["06", "16", "19", "21", "34", "43", "44"],
    ["06", "16", "19", "21", "34", "-"],
    ["06", "16", "19", "21", "34", "34"],
    ["00", "16", "19", "21", "34", "43"],
    ["06", "16", "19", "21", "34", "46"],
])
def test_historical_missing_duplicate_or_out_of_range_numbers_are_issues(numbers):
    def change(block):
        ul = block.select_one("ul.result-number")
        ul.clear()
        for number in numbers:
            li = BeautifulSoup("<li></li>", "html.parser").li
            li.string = number
            ul.append(li)

    page = parse(first_block_html(change), datetime(2026, 10, 15, 20, tzinfo=NOW.tzinfo))
    assert not page.records
    assert not page.pending
    assert len(page.issues) == 1
    assert page.issues[0]["kind"] == "invalid"
    assert page.issues[0]["draw_id"] == 1575


def test_unsorted_source_numbers_are_canonicalized():
    def change(block):
        nodes = block.select("ul.result-number > li")
        for node, value in zip(nodes, [43, 6, 34, 16, 21, 19]):
            node.string = str(value)

    page = parse(first_block_html(change))
    assert [page.records[0][f"n{i}"] for i in range(1, 7)] == [6, 16, 19, 21, 34, 43]


@pytest.mark.parametrize("id_text", ["", "1575", "#0", "#unknown"])
def test_blank_or_invalid_draw_id_is_never_inferred(id_text):
    def change(block):
        block.select_one('[id="DT6X45_KY_VE"]').string = id_text

    page = parse(first_block_html(change))
    assert not page.records
    assert len(page.issues) == 1
    assert page.issues[0]["kind"] == "invalid"


def test_missing_draw_id_node_reports_structure_issue():
    page = parse(first_block_html(lambda b: b.select_one('[id="DT6X45_KY_VE"]').decompose()))
    assert not page.records
    assert page.issues[0]["kind"] == "structure"


@pytest.mark.parametrize("html", [
    "<html><title>Access denied</title></html>",
    "<html><title>Mega 6/45</title><main>Different structure</main></html>",
])
def test_blocked_or_changed_page_fails_loudly(html):
    with pytest.raises(SourceError):
        parse(html)


@pytest.mark.parametrize("now", [
    datetime(2026, 10, 13, 20, tzinfo=NOW.tzinfo),
    datetime(2026, 10, 14, 18, 4, tzinfo=NOW.tzinfo),
])
def test_future_or_pre_draw_results_remain_pending(now):
    page = parse(first_block_html(), now)
    assert not page.records
    assert not page.issues
    assert page.pending == 1


def test_incomplete_same_day_draw_remains_pending_after_broadcast_time():
    page = parse(first_block_html(lambda b: b.select("ul.result-number > li")[-1].decompose()))
    assert not page.records
    assert not page.issues
    assert page.pending == 1


@pytest.mark.parametrize("url", [
    "http://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html",
    "https://evil.test/mega-6x45/14-10-2026.html",
    "https://user:password@www.minhngoc.net.vn/mega-6x45/14-10-2026.html",
    "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/power-6x55.html",
])
def test_source_links_reject_foreign_hosts_credentials_or_wrong_games(url):
    with pytest.raises(SourceError):
        safe_url(url)


VIETMY_FIRST_URL = "https://xosovietmy.vn/xs-mega-ngay-20-07-2016.html"


def vietmy_html():
    return (FIXTURES / "vietmy-first.html").read_text(encoding="utf-8")


def test_real_vietmy_first_fixture_has_explicit_id_date_and_six_numbers():
    records = parse_vietmy(vietmy_html(), VIETMY_FIRST_URL, now=NOW)
    assert len(records) == 1
    first = records[0]
    assert first["draw_id"] == 1
    assert first["draw_date"] == "2016-07-20"
    assert [first[f"n{i}"] for i in range(1, 7)] == [2, 17, 33, 37, 38, 45]
    assert first["source_url"] == VIETMY_FIRST_URL
    assert first["source_name"] == "xosovietmy"
    assert first["verification_status"] == "secondary"


@pytest.mark.parametrize("change", [
    lambda s: setattr(s.title, "string", "Power 6/55"),
    lambda s: setattr(s.select_one("strong"), "string", "Kỳ:"),
    lambda s: s.select_one(".xsmega-num").decompose(),
    lambda s: setattr(s.select_one(".xsmega-num"), "string", "46"),
    lambda s: setattr(s.select_one(".xsmega-num"), "string", "17"),
    lambda s: setattr(s.select_one(".xsmega-num"), "string", "-"),
    lambda s: setattr(s.select_one("h2"), "string", "Xổ số Mega 6/45 22/07/2016"),
])
def test_supplement_rejects_wrong_game_missing_id_bad_numbers_or_date_mismatch(change):
    soup = BeautifulSoup(vietmy_html(), "html.parser")
    change(soup)
    with pytest.raises(SourceError):
        parse_vietmy(str(soup), VIETMY_FIRST_URL, now=NOW)


def blank_early_minhngoc_html(numbers):
    # Mutation of observed markup models the blank-ID case without deriving an ID.
    soup = BeautifulSoup(first_block_html(), "html.parser")
    block = soup.select_one(".box-result-detail")
    block.select_one('[id="DT6X45_KY_VE"]').string = ""
    for text in list(block.find_all(string=True)):
        if "14/10/2026" in text:
            text.replace_with(text.replace("14/10/2026", "20/07/2016"))
    for node, value in zip(block.select("ul.result-number > li"), numbers):
        node.string = str(value)
    for anchor in soup.select(".boxkqxsdientoan h4 a[href]"):
        anchor["href"] = "/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/20-07-2016.html"
    return str(soup)


@pytest.mark.parametrize("match", [True, False])
def test_fetch_supplements_blank_id_only_when_independent_numbers_match(monkeypatch, match):
    numbers = [2, 17, 33, 37, 38, 45] if match else [1, 17, 33, 37, 38, 45]
    called = []
    source = MinhNgocSource()

    def read_html(url):
        called.append(url)
        if url == LATEST_URL:
            return blank_early_minhngoc_html(numbers)
        assert url == VIETMY_FIRST_URL
        return vietmy_html()

    monkeypatch.setattr(source, "_read_html", read_html)
    page = source.fetch()
    assert called == [LATEST_URL, VIETMY_FIRST_URL]
    if match:
        assert len(page.records) == 1
        assert not page.issues
        assert page.records[0]["draw_id"] == 1
        assert page.records[0]["verification_status"] == "cross_checked"
        assert page.records[0]["source_name"] == "xosovietmy+minhngoc"
    else:
        assert not page.records
        assert len(page.issues) == 1
        assert page.issues[0]["kind"] == "conflict"
        assert page.issues[0]["draw_id"] == 1
