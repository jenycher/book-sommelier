"""Шаг 3: отбор финальной подборки из кандидатов и обоснование выбора."""
from .llm import chat_json

import config


def _shorten(text, limit=400):
    if not text:
        return ""
    text = text.strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _catalogue(candidates):
    """Кандидаты -> пронумерованный список для промпта отборщика."""
    lines = []
    for index, candidate in enumerate(candidates, start=1):
        description = _shorten(candidate.get("description"))
        subjects = ", ".join(candidate.get("subject")[:5])
        lines.append(
            "%d. «%s» — %s (%s)%s%s" % (
                index,
                candidate["title"],
                candidate["author"],
                candidate.get("year") or "год неизвестен",
                "; темы: %s" % subjects if subjects else "",
                "; о книге: %s" % description if description else "",
            )
        )
    return "\n".join(lines)


def _valid_picks(answer, candidates):
    """Собирает корректные picks: их индексы должны быть внутри каталога."""
    picks_data = answer.get("picks") or []
    if not isinstance(picks_data, list):
        return []

    picks = []
    for pick in picks_data[: config.MAX_PICKS]:
        index = pick.get("index")
        if not isinstance(index, int) or not 1 <= index <= len(candidates):
            continue
        book = dict(candidates[index - 1])
        for field in ("why", "vibe_like", "caveat"):
            book[field] = (pick.get(field) or "").strip()
        picks.append(book)
    return picks


def curate(taste, candidates, query):
    """Признаки вкуса + список кандидатов -> список книг подборки.

    Модель выбирает по индексам кандидатов, поэтому выдумать несуществующую
    книгу или перепутать автора не может. Нестабильную бесплатную модель
    переспрашиваем: если подборка не собралась — вторая попытка.
    """
    system = (
        "Ты — книжный сомелье, который отбирает настоящую винную карту "
        "под настроение читателя. Отвечай строго валидным JSON без пояснений "
        "и без markdown-ограждений. Все тексты полей — только на русском языке."
    )
    user = (
        "Вкус читателя: %s\n"
        "Запрос читателя: «%s»\n"
        "Чего точно не надо: %s\n\n"
        "Кандидаты из каталогов:\n%s\n\n"
        "Читатель русскоязычный: кандидаты с источником «Google Books (рус.)» "
        "издания на русском языке, при равном вайбе они приоритетны.\n"
        "Отбери ровно %d кандидатов (не меньше — список picks должен "
        "насчитывать ровно %d объектов), которые точнее всего попадают в "
        "настроение. Отказывайся от тех, кто «формально похож, но не по "
        "вайбу». Ответ держи сжатым: одно короткое предложение на каждое "
        "поле, без лишних оборотов. "
        "Верни JSON-объект ровно такой структуры:\n"
        "{\n"
        '  "picks": [\n'
        "    {\n"
        '      "index": 3,\n'
        '      "why": "почему книга под этот запрос, одно предложение на русском",\n'
        '      "vibe_like": "на какую книгу или автора похожа, одно короткое предложение",\n'
        '      "caveat": "чем может не подойти, одно короткое предложение, или пустая строка"\n'
        "    }\n"
        "  ]\n"
        "}"
    ) % (
        taste.get("note_ru", ""),
        query,
        ", ".join(taste.get("avoid") or []) or "ничего конкретного",
        _catalogue(candidates),
        config.MAX_PICKS,
        config.MAX_PICKS,
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]

    picks = []
    for _ in range(2):
        answer = chat_json(messages)
        picks = _valid_picks(answer, candidates)
        if picks:
            break

    if len(picks) < config.MIN_PICKS:
        raise ValueError(
            "модель отобрала слишком мало кандидатов (%d)" % len(picks)
        )
    return picks