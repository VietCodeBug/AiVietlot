from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from .models import utc_now, validate_draw

LATEST_URL = "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45.html"
OFFICIAL_URL = "https://vietlott.vn/vi/trung-thuong/ket-qua-trung-thuong/645.html"
DATE_LINK = re.compile(r"/mega-6x45/(\d{2}-\d{2}-\d{4})\.html$")
VIETMY_DATE_LINK = re.compile(r"^/xs-mega-ngay-(\d{2}-\d{2}-\d{4})\.html$")


class SourceError(RuntimeError):
    pass


@dataclass
class Page:
    url: str
    records: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)
    pending: int = 0
    older_url: str | None = None
    first_url: str | None = None
    date_urls: dict[str, str] = field(default_factory=dict)


def safe_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "www.minhngoc.net.vn" or parts.username:
        raise SourceError("Liên kết nguồn không thuộc HTTPS Minh Ngọc")
    if not (parts.path.endswith("/mega-6x45.html") or DATE_LINK.search(parts.path)):
        raise SourceError("Liên kết không phải trang Mega 6/45 theo ngày")
    return url


def parse_minhngoc(html: str, url: str, *, now: datetime | None = None) -> Page:
    """Parse observed Minh Ngoc HTML and navigation; do not guess archive APIs."""
    safe_url(url)
    now = now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))
    now = now.astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if "mega" not in title or "6/45" not in title:
        raise SourceError("Trang nguồn không có tiêu đề Mega 6/45")
    page = Page(url=url)
    blocks = soup.select(".box-result-detail")
    if not blocks:
        raise SourceError("Cấu trúc HTML đã đổi: không tìm thấy .box-result-detail")
    for block in blocks:
        id_node = block.select_one('[id="DT6X45_KY_VE"]')
        if id_node is None:
            page.issues.append({"kind": "structure", "message": "Thiếu mã kỳ Mega", "payload": {"source_url": url}})
            continue
        draw_id = None
        try:
            id_text = id_node.get_text(strip=True)
            if not re.fullmatch(r"#\d+", id_text):
                raise ValueError("Mã kỳ Mega không hợp lệ")
            draw_id = int(id_text[1:])
            text = block.get_text(" ", strip=True)
            match = re.search(r"Ngày quay thưởng\s+(\d{2}/\d{2}/\d{4})", text)
            if not match:
                raise ValueError("Thiếu ngày quay thưởng")
            draw_date = datetime.strptime(match.group(1), "%d/%m/%Y").date()
            raw_numbers = [n.get_text(strip=True) for n in block.select("ul.result-number > li")]
            complete = len(raw_numbers) == 6 and all(re.fullmatch(r"\d{1,2}", n) for n in raw_numbers)
            if draw_date > now.date() or (draw_date == now.date() and (now.hour, now.minute) < (18, 5)):
                page.pending += 1
                continue
            if not complete:
                if draw_date == now.date():
                    page.pending += 1
                    continue
                raise ValueError("Kỳ lịch sử thiếu sáu số hoàn chỉnh")
            numbers = sorted(int(n) for n in raw_numbers)
            canonical = url
            container = block.find_parent(class_="boxkqxsdientoan")
            if container:
                for link in container.select("h4 a[href]"):
                    candidate = urljoin(url, link["href"])
                    m = DATE_LINK.search(urlsplit(candidate).path)
                    if m and datetime.strptime(m.group(1), "%d-%m-%Y").date() == draw_date:
                        canonical = safe_url(candidate)
                        break
            record = {"draw_id": draw_id, "draw_date": draw_date.isoformat(),
                      **{f"n{i}": n for i, n in enumerate(numbers, 1)},
                      "source_name": "minhngoc", "source_url": canonical,
                      "fetched_at": utc_now(), "verification_status": "secondary"}
            validate_draw(record, today=now.date())
            page.records.append(record)
        except (ValueError, KeyError) as exc:
            text = block.get_text(" ", strip=True)
            day = re.search(r"Ngày quay thưởng\s+(\d{2}/\d{2}/\d{4})", text)
            values = [n.get_text(strip=True) for n in block.select("ul.result-number > li")]
            page.issues.append({"kind": "invalid", "draw_id": draw_id, "message": str(exc),
                                "payload": {"source_url": url, "text": text[:500],
                                            "draw_date": datetime.strptime(day.group(1), "%d/%m/%Y").date().isoformat() if day else None,
                                            "numbers": sorted(int(n) for n in values) if len(values) == 6 and all(n.isdigit() for n in values) else None}})
    for link in soup.select("a[href]"):
        candidate = urljoin(url, link["href"])
        m = DATE_LINK.search(urlsplit(candidate).path)
        if not m:
            continue
        candidate = safe_url(candidate)
        day = datetime.strptime(m.group(1), "%d-%m-%Y").date()
        page.date_urls[day.isoformat()] = candidate
        if link.get_text(strip=True) == "<<<<":
            page.first_url = candidate
    visible_dates = []
    for link in soup.select(".boxkqxsdientoan h4 a[href]"):
        m = DATE_LINK.search(urlsplit(urljoin(url, link["href"])).path)
        if m:
            visible_dates.append(datetime.strptime(m.group(1), "%d-%m-%Y").date().isoformat())
    if page.records or visible_dates:
        oldest_date = min(visible_dates or [r["draw_date"] for r in page.records])
        candidate = page.date_urls.get(oldest_date)
        if candidate and candidate != url:
            page.older_url = candidate
        else:
            older_dates = [d for d in page.date_urls if d < oldest_date]
            if older_dates:
                page.older_url = page.date_urls[max(older_dates)]
    return page


def parse_vietmy(html: str, url: str, *, now: datetime | None = None) -> list[dict]:
    """Supplement blank early Minh Ngoc draw IDs with an explicit second-source ID."""
    parts = urlsplit(url)
    match = VIETMY_DATE_LINK.fullmatch(parts.path)
    if parts.scheme != "https" or parts.hostname != "xosovietmy.vn" or not match:
        raise SourceError("Liên kết bổ sung không phải kết quả Mega theo ngày của Việt Mỹ")
    expected_date = datetime.strptime(match.group(1), "%d-%m-%Y").date()
    today = (now or datetime.now(ZoneInfo("Asia/Ho_Chi_Minh"))).astimezone(ZoneInfo("Asia/Ho_Chi_Minh"))
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True).lower() if soup.title else ""
    if "mega" not in title or "6/45" not in title:
        raise SourceError("Nguồn bổ sung không phải Mega 6/45")
    results = []
    for box in soup.select(".div-xsmega-num"):
        section = box.find_parent("section", class_="section")
        if section is None:
            raise SourceError("Cấu trúc kết quả Việt Mỹ đã thay đổi")
        head = section.select_one("h2")
        if head is None or expected_date.strftime("%d/%m/%Y") not in head.get_text(" ", strip=True):
            continue
        id_match = re.search(r"Kỳ:\s*#(\d+)", section.get_text(" ", strip=True))
        raw_numbers = [n.get_text(strip=True) for n in box.select(".xsmega-num")]
        if not id_match or len(raw_numbers) != 6 or not all(re.fullmatch(r"\d{1,2}", n) for n in raw_numbers):
            raise SourceError("Nguồn bổ sung thiếu mã kỳ hoặc sáu số hoàn chỉnh")
        numbers = sorted(int(n) for n in raw_numbers)
        record = {"draw_id": int(id_match.group(1)), "draw_date": expected_date.isoformat(),
                  **{f"n{i}": n for i, n in enumerate(numbers, 1)},
                  "source_name": "xosovietmy", "source_url": url,
                  "fetched_at": utc_now(), "verification_status": "secondary"}
        try:
            validate_draw(record, today=today.date())
        except ValueError:
            raise SourceError("Nguồn bổ sung trả kết quả không hợp lệ") from None
        if expected_date == today.date() and (today.hour, today.minute) < (18, 5):
            continue
        results.append(record)
    if len(results) != 1:
        raise SourceError("Không xác định được duy nhất kết quả Việt Mỹ theo ngày")
    return results


class MinhNgocSource:
    def __init__(self, *, delay: float = 1.0, retries: int = 3, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "MegaLabCollector/1.0 (academic statistics; 1 request/second)"})
        self.delay = max(delay, 0.5)
        self.retries = retries
        self._last_request = 0.0

    def navigation_url(self, record: dict) -> str:
        if record["source_url"].startswith("https://xosovietmy.vn/"):
            day = datetime.fromisoformat(record["draw_date"]).strftime("%d-%m-%Y")
            return "https://www.minhngoc.net.vn/ket-qua-xo-so/dien-toan-vietlott/mega-6x45/" + day + ".html"
        return record["source_url"]

    def fetch(self, url: str = LATEST_URL) -> Page:
        safe_url(url)
        try:
            page = parse_minhngoc(self._read_html(url), url)
        except (ValueError, KeyError, IndexError):
            raise SourceError("Cấu trúc hoặc ngày của trang nguồn không hợp lệ") from None
        remaining = []
        for issue in page.issues:
            payload = issue["payload"]
            if issue["message"] != "Mã kỳ Mega không hợp lệ" or not payload.get("draw_date") or not payload.get("numbers"):
                remaining.append(issue)
                continue
            # Date route confirmed by the site's live canonical links and tested
            # HTML. The draw ID must come from this page, never the date schedule.
            day = datetime.fromisoformat(payload["draw_date"]).strftime("%d-%m-%Y")
            fallback_url = f"https://xosovietmy.vn/xs-mega-ngay-{day}.html"
            try:
                record = parse_vietmy(self._read_html(fallback_url), fallback_url)[0]
            except (ValueError, KeyError, IndexError):
                raise SourceError("Cấu trúc hoặc ngày của nguồn bổ sung không hợp lệ") from None
            if [record[f"n{i}"] for i in range(1, 7)] != payload["numbers"]:
                remaining.append({**issue, "kind": "conflict", "draw_id": record["draw_id"],
                                  "message": "Hai nguồn không khớp sáu số",
                                  "payload": {**payload, "second_source": record}})
                continue
            record["verification_status"] = "cross_checked"
            record["source_name"] = "xosovietmy+minhngoc"
            page.records.append(record)
        page.issues = remaining
        return page

    def _read_html(self, url: str) -> str:
        for attempt in range(self.retries + 1):
            time.sleep(max(0, self.delay - (time.monotonic() - self._last_request)))
            self._last_request = time.monotonic()
            try:
                response = self.session.get(url, timeout=(10, 40), allow_redirects=True)
            except requests.RequestException:
                if attempt == self.retries:
                    raise SourceError("Không kết nối được nguồn sau các lần thử lại") from None
                time.sleep(min(2 ** attempt, 16))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 16))
                    continue
            if response.status_code != 200:
                raise SourceError(f"Nguồn trả HTTP {response.status_code}")
            redirected = urlsplit(response.url)
            requested = urlsplit(url)
            if redirected.scheme != "https" or redirected.hostname != requested.hostname:
                raise SourceError("Nguồn chuyển hướng sang host không được xác minh")
            response.encoding = "utf-8"
            return response.text
        raise SourceError("Nguồn không phản hồi")
