"""Maandoverzicht om te printen: hele weken (ma-zo) per blok, plus maandtotalen."""
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import db
from .calc import DAGEN_KORT, build_year, fmt_euro, fmt_hours

_env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                   autoescape=select_autoescape())
_env.filters["uur"] = fmt_hours
_env.filters["euro"] = fmt_euro


def print_context(conn, year: int, months: list[int]) -> dict:
    Y = build_year(conn, year)
    return dict(Y=Y, months=[Y["months"][m - 1] for m in months], dagen=DAGEN_KORT,
                naam=db.get_meta(conn, "naam", "") or "")


def render_html(conn, year: int, months: list[int]) -> str:
    return _env.get_template("print.html").render(**print_context(conn, year, months))


def render_pdf(conn, year: int, months: list[int]) -> bytes:
    from weasyprint import HTML  # traag om te laden, alleen als nodig
    return HTML(string=render_html(conn, year, months)).write_pdf()
