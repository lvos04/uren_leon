"""Importeer het oude Excel-bestand vanaf de command line.

Gebruik (in de container):  python -m scripts.import_xlsx /data/salaris_bijhouden.xlsx
Kan ook via de web-UI: Instellingen -> Importeer oud Excel-bestand.
"""
import sys

from app import db
from app.importer import import_into, parse_workbook


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    db.init_db()
    parsed = parse_workbook(open(sys.argv[1], "rb").read())
    with db.get_conn() as conn:
        for year, s in import_into(conn, parsed).items():
            print(year, s)


if __name__ == "__main__":
    main()
