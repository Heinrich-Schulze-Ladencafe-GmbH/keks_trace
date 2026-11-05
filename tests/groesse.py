"""Größen-Check: keine Datei wächst wieder zum Sammelbecken.

Ab HINWEIS Zeilen steht die Datei in der Ausgabe (Zeit, sie nach Bereichen aufzuteilen, wie terminal,
palette, linienbuchung). Ab GRENZE schlägt der Check fehl. Nicht gezählt: Tests, Fremdbibliotheken.

	python3 tests/groesse.py
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HINWEIS = 600
GRENZE = 700
ENDUNGEN = {".py", ".js", ".html"}
AUSGENOMMEN = {
	"keks_trace/public/js/bwip-js-min.js",  # Fremdbibliothek (Strichcodes), minifiziert
}

zu_gross, hinweise = [], []
for p in sorted((REPO / "keks_trace").rglob("*")):
	rel = str(p.relative_to(REPO))
	if p.suffix not in ENDUNGEN or "tests" in p.parts or "__pycache__" in p.parts or rel in AUSGENOMMEN:
		continue
	n = sum(1 for _ in p.open(encoding="utf-8", errors="ignore"))
	if n > GRENZE:
		zu_gross.append(f"{rel}: {n} Zeilen (Grenze {GRENZE})")
	elif n > HINWEIS:
		hinweise.append(f"{rel}: {n} Zeilen")

if hinweise:
	print(f"Über {HINWEIS} Zeilen (bald aufteilen):\n  " + "\n  ".join(hinweise))
if zu_gross:
	print("Zu groß, bitte nach Bereichen aufteilen:\n  " + "\n  ".join(zu_gross))
print("Größen in Ordnung" if not zu_gross else "")
sys.exit(1 if zu_gross else 0)
