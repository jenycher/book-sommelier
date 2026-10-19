"""Книжный сомелье — Flask-приложение.

Запуск локально: py app.py, затем открыть http://127.0.0.1:5000
"""
import json

from flask import (Flask, Response, abort, redirect, render_template,
                   request, url_for)

from sommelier import curate, db, search, taste
from sommelier.llm import LLMError

app = Flask(__name__)


@app.route("/")
def index():
    return render_template("index.html", history=db.recent())


@app.route("/select", methods=["POST"])
def select():
    query = (request.form.get("query") or "").strip()
    favorite_books = (request.form.get("favorites") or "").strip()

    if not query:
        return render_template(
            "error.html",
            message="Опишите, что хотите почитать — хотя бы пару слов о настроении.",
            back_url=url_for("index"),
        )

    # скелет страницы прогресса рендерим заранее: внутри стрима Flask
    # теряет контекст приложения, и render_template уже нельзя вызвать
    skeleton = " " * 256 + render_template("progress.html", query=query)

    def generate():
        """Страничка прогресса, которая оживает по мере работы конвейера.

        Сервер отдаёт её кусками: скелет со списком шагов, затем по
        <script>-вставке на каждый завершённый этап.
        """
        # паддинг в начале ответа, чтобы браузер сразу начал рендерить
        yield skeleton

        try:
            yield '<script>setStep(1, "running");</script>'
            flavor = taste.analyze(query, favorite_books)
            yield (
                '<script>setStep(1, "done"); setStep(2, "running");</script>'
            )

            candidates = search.find_candidates(flavor)
            yield (
                '<script>setStep(2, "done"); setStep(3, "running");</script>'
            )

            picks = curate.curate(flavor, candidates, query)
            yield '<script>setStep(3, "done");</script>'

            selection_id = db.save_request(query, favorite_books, flavor, picks)
            # финальную карточку рисует обычная страница /history/<id>:
            # и результат, и «подобрать ещё раз» живут одинаково
            yield (
                "<script>window.location.replace('/history/%d');</script>"
                % selection_id
            )
        except (LLMError, search.SearchError, ValueError) as error:
            message = json.dumps(
                "Сомелье споткнулся: %s Подождите чуть-чуть и попробуйте ещё раз."
                % (str(error).strip() or "неизвестная ошибка."),
                ensure_ascii=False,
            )
            yield "<script>showError(%s)</script>" % message

    return Response(generate(), content_type="text/html; charset=utf-8")


@app.route("/history/<int:selection_id>")
def history(selection_id):
    record = db.get_request(selection_id)
    if record is None:
        abort(404)
    return render_template(
        "result.html",
        picks=record["picks"],
        flavor=record["taste"],
        query=record["query"],
        selection_id=record["id"],
        created_at=record["created_at"],
    )


if __name__ == "__main__":
    app.run(debug=True)