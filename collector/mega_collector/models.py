from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

DRAW_FIELDS = ["draw_id", "draw_date", *[f"n{i}" for i in range(1, 7)],
               "source_name", "source_url", "fetched_at", "verification_status"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def validate_draw(record: dict[str, Any], *, today: date | None = None) -> None:
    if type(record.get("draw_id")) is not int or record["draw_id"] < 1:
        raise ValueError("Mã kỳ phải là số nguyên dương")
    draw_date = date.fromisoformat(record["draw_date"])
    if today is not None and draw_date > today:
        raise ValueError("Không nhập kỳ trong tương lai")
    numbers = [record.get(f"n{i}") for i in range(1, 7)]
    if any(type(n) is not int for n in numbers):
        raise ValueError("Kết quả phải có đúng sáu số nguyên")
    if not (1 <= numbers[0] < numbers[1] < numbers[2] < numbers[3]
            < numbers[4] < numbers[5] <= 45):
        raise ValueError("Sáu số phải khác nhau, tăng dần và nằm trong 1–45")
    if record.get("verification_status") not in {"official", "secondary", "cross_checked"}:
        raise ValueError("Trạng thái xác minh không hợp lệ")
    if not record.get("source_name") or not str(record.get("source_url", "")).startswith("https://"):
        raise ValueError("Thiếu nguồn HTTPS")
    stamp = datetime.fromisoformat(record["fetched_at"].replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("Thời điểm lấy phải có múi giờ")
