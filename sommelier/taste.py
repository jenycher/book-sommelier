"""Шаг 1: разбор запроса читателя на конкретные признаки вкуса."""
from .llm import chat_json


def analyze(query, favorite_books=""):
    """Свободный текст запроса -> JSON-признаки для поиска.

    Возвращает словарь с ключами:
    genres, themes, keywords_en (поисковые запросы для API, англ.), avoid.
    """
    system = (
        "Ты — книжный сомелье. Ты разбираешь желания читателя на конкретные "
        "книжные признаки. Отвечай строго валидным JSON без пояснений и без "
        "markdown-ограждений."
    )
    user = (
        "Запрос читателя: «%s»." % query
    )
    if favorite_books:
        user += " Любимые книги читателя: «%s»." % favorite_books

    user += (
        "\nВерни JSON-объект ровно такой структуры:\n"
        "{\n"
        '  "genres": ["жанры книги"],\n'
        '  "themes": ["темы и настроения"],\n'
        '  "keywords_en": ["2-4 коротких англоязычных поисковых запроса для '
        'каталогов книг: жанровые слова, темы, стили"],\n'
        '  "avoid": ["авторы, жанры или темы, которых читатель НЕ хочет"],\n'
        '  "note_ru": "краткая формулировка вкуса на русском"\n'
        "}"
    )

    result = chat_json([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ], force_schema=False)

    # страховка: незаполненные поля не должны ломать следующие шаги
    for field in ("genres", "themes", "keywords_en", "avoid"):
        if not isinstance(result.get(field), list):
            result[field] = []
    keywords = [k.strip() for k in result["keywords_en"] if isinstance(k, str) and k.strip()]
    if not keywords:
        keywords = [query]
    result["keywords_en"] = keywords
    result.setdefault("note_ru", query)
    return result