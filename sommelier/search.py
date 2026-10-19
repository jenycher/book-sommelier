"""Шаг 2: сбор кандидатов из открытых каталогов (Open Library + Google Books)."""
import os
import time

import requests

import config

# Анонимный доступ к Google Books имеет общую дневную квоту (часто исчерпана).
# Бесплатный ключ console.cloud.google.com снимает её — достаточно переменной
# окружения GOOGLE_BOOKS_API_KEY.
GOOGLE_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY")


class SearchError(Exception):
    """Не удалось получить данные ни из одного каталога."""


def _openlibrary(keyword):
    url = "https://openlibrary.org/search.json"
    params = {
        "q": keyword,
        "limit": 12,
        "fields": "title,author_name,first_publish_year,subject,cover_i,key",
    }
    response = requests.get(url, params=params, timeout=config.SEARCH_TIMEOUT)
    response.raise_for_status()
    candidates = []
    for doc in response.json().get("docs", []):
        title = (doc.get("title") or "").strip()
        authors = doc.get("author_name") or []
        if not title or not authors:
            continue
        cover_i = doc.get("cover_i")
        candidates.append({
            "title": title,
            "author": authors[0],
            "year": doc.get("first_publish_year"),
            "subject": [str(s) for s in (doc.get("subject") or [])[:8]],
            "description": None,  # полные описания дёргаем только для отобранных
            "cover": (
                "https://covers.openlibrary.org/b/id/%s-M.jpg" % cover_i
                if cover_i else None
            ),
            "link": "https://openlibrary.org%s" % doc.get("key", ""),
            "source": "Open Library",
        })
    return candidates


def _google_books(keyword):
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": keyword, "maxResults": 12}
    if GOOGLE_KEY:
        params["key"] = GOOGLE_KEY
    response = requests.get(url, params=params, timeout=config.SEARCH_TIMEOUT)
    response.raise_for_status()
    candidates = []
    for item in response.json().get("items", []):
        info = item.get("volumeInfo", {})
        title = (info.get("title") or "").strip()
        if not title:
            continue
        authors = info.get("authors") or []
        image = info.get("imageLinks", {})
        snippet = (info.get("description") or "")[:600] or None
        candidates.append({
            "title": title,
            "author": authors[0] if authors else "неизвестен",
            "year": _first_year(info.get("publishedDate", "")),
            "subject": [
                str(s) for s in (info.get("categories") or [])[:8]
            ],
            "description": snippet,
            "cover": image.get("thumbnail") or image.get("smallThumbnail"),
            "link": info.get("infoLink") or info.get("canonicalVolumeLink", ""),
            "source": "Google Books",
        })
    return candidates


def _google_books_ru(keyword):
    """То же, что _google_books, но только книги на русском.

    Именно отсюда приходят русские переводы популярных книг: у Open Library
    их каталог почти полностью англоязычный.
    """
    url = "https://www.googleapis.com/books/v1/volumes"
    params = {"q": keyword, "maxResults": 12, "langRestrict": "ru"}
    if GOOGLE_KEY:
        params["key"] = GOOGLE_KEY
    response = requests.get(url, params=params, timeout=config.SEARCH_TIMEOUT)
    response.raise_for_status()
    candidates = []
    for item in response.json().get("items", []):
        info = item.get("volumeInfo", {})
        title = (info.get("title") or "").strip()
        if not title:
            continue
        authors = info.get("authors") or []
        image = info.get("imageLinks", {})
        snippet = (info.get("description") or "")[:600] or None
        candidates.append({
            "title": title,
            "author": authors[0] if authors else "неизвестен",
            "year": _first_year(info.get("publishedDate", "")),
            "subject": [
                str(s) for s in (info.get("categories") or [])[:8]
            ],
            "description": snippet,
            "cover": image.get("thumbnail") or image.get("smallThumbnail"),
            "link": info.get("infoLink") or info.get("canonicalVolumeLink", ""),
            "source": "Google Books (рус.)",
        })
    return candidates


def _first_year(date_string):
    year = (date_string or "")[:4]
    return int(year) if year.isdigit() else None


def find_candidates(taste):
    """Собирает и дедуплицирует кандидатов по всем поисковым запросам вкуса.

    Каталоги не любят серий запросов подряд, поэтому между ними паузы, а
    упавший запрос ретраится один раз. Сбой одного каталога не мешает
    собрать подборку из другого.
    """
    seen = set()
    candidates = []

    for keyword in taste["keywords_en"][: config.KEYWORDS_PER_QUERY]:
        fetchers = [_openlibrary, _google_books]
        try:
            # русский вариант Google Books опрашиваем только если обычный
            # жив: анонимная дневная квота у них общая, дёргать зря не надо
            books_probe = _google_books(keyword)
        except (requests.RequestException, ValueError):
            books_probe = None
        if books_probe is not None:
            fetchers.append(_google_books_ru)

        for fetcher in fetchers:
            for attempt in range(2):
                try:
                    books = fetcher(keyword)
                    break
                except (requests.RequestException, ValueError):
                    if attempt == 0:
                        time.sleep(3)
                        continue
                    books = []  # один каталог/ключ упал — берём что есть
            for book in books:
                key = (book["title"].lower().strip(),
                       book["author"].lower().split()[-1]
                       if book["author"].split() else "")
                if key in seen:
                    continue
                seen.add(key)
                candidates.append(book)
        time.sleep(1)  # каталоги троттлят быстрые серии запросов

    candidates = candidates[: config.CANDIDATES_LIMIT]
    if not candidates:
        raise SearchError(
            "каталоги не вернули ни одной книги по этому запросу — "
            "попробуйте сформулировать иначе"
        )
    return candidates