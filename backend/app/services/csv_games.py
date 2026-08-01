import ast
import csv
import html
import re
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from app.domain.game import Game

_HTML_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def _integer(value: object) -> int:
    try:
        return max(0, int(float(str(value or 0).replace(",", ""))))
    except (TypeError, ValueError):
        return 0


def _boolean(value: object) -> bool:
    return str(value or "").strip().casefold() in {"1", "true", "yes", "y"}


def _clean_text(value: object) -> str:
    text = html.unescape(str(value or ""))
    return _SPACE.sub(" ", _HTML_TAG.sub(" ", text)).strip()


def _list(value: object) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    items: object = raw
    if raw[:1] in "[({" and raw[-1:] in "])}":
        try:
            items = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            items = raw
    if isinstance(items, dict):
        values = list(items)
    elif isinstance(items, list | tuple | set):
        values = list(items)
    else:
        values = re.split(r"[,;|]", str(items))
    result: list[str] = []
    seen: set[str] = set()
    for item in values:
        cleaned = _clean_text(item).strip(" '\"")
        key = cleaned.casefold()
        if cleaned and key not in seen:
            result.append(cleaned)
            seen.add(key)
    return result


def _date(value: object):
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d", "%b %d, %Y", "%d %b, %Y", "%B %d, %Y", "%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _image_url(value: object) -> str | None:
    raw = str(value or "").strip()
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.netloc else None


def normalize_row(row: dict[str, object], max_retrieval_chars: int = 3000) -> Game:
    app_id = int(str(row.get("AppID") or "").strip())
    name = _clean_text(row.get("Name")) or f"Steam app {app_id}"
    positive = _integer(row.get("Positive"))
    negative = _integer(row.get("Negative"))
    reviews = positive + negative
    rating = round(positive / reviews * 100, 2) if reviews else None
    about = _clean_text(row.get("About the game"))
    developers = _list(row.get("Developers"))
    publishers = _list(row.get("Publishers"))
    categories = _list(row.get("Categories"))
    genres = _list(row.get("Genres"))
    tags = _list(row.get("Tags"))
    supported_languages = _list(row.get("Supported languages"))
    parts = [
        f"Name: {name}",
        f"Genres: {', '.join(genres)}" if genres else "",
        f"Tags: {', '.join(tags)}" if tags else "",
        f"Categories: {', '.join(categories)}" if categories else "",
        f"Developers: {', '.join(developers)}" if developers else "",
        f"Publishers: {', '.join(publishers)}" if publishers else "",
        f"Description: {about}" if about else "",
    ]
    retrieval_text = "\n".join(part for part in parts if part)[:max_retrieval_chars]
    return Game(
        app_id=app_id,
        name=name,
        release_date=_date(row.get("Release date")),
        about=about,
        header_image=_image_url(row.get("Header image")),
        windows=_boolean(row.get("Windows")),
        mac=_boolean(row.get("Mac")),
        linux=_boolean(row.get("Linux")),
        positive=positive,
        negative=negative,
        rating_percent=rating,
        reviews_count=reviews,
        supported_languages=supported_languages,
        developers=developers,
        publishers=publishers,
        categories=categories,
        genres=genres,
        tags=tags,
        retrieval_text=retrieval_text,
    )


def stream_games(
    path: Path,
    max_retrieval_chars: int,
    on_failure: Callable[[int, str], None] | None = None,
) -> Iterator[Game]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required = {"AppID", "Name", "About the game"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV is missing required columns: {', '.join(sorted(missing))}")
        seen: set[int] = set()
        for line_number, row in enumerate(reader, 2):
            try:
                game = normalize_row(row, max_retrieval_chars)
            except (TypeError, ValueError) as exc:
                if on_failure:
                    on_failure(line_number, str(exc))
                continue
            if game.app_id in seen:
                if on_failure:
                    on_failure(line_number, f"duplicate AppID {game.app_id}")
                continue
            seen.add(game.app_id)
            yield game
