"""Zyklen-Check: hängen die Kernmodule nur in eine Richtung voneinander ab?

Zählt jeden Import zwischen Modulen von keks_trace, auch Imports innerhalb von Funktionen (die
sonst nur verdecken, dass zwei Module sich gegenseitig brauchen). Ein Paket (terminal, palette,
buchung, ...) zählt als ein Knoten. Nicht betrachtet: Demo, Tests, Patches, DocType-Controller.
Schichten von oben nach unten, grob: terminal -> linienbuchung -> buchung -> palette, silo, ...

	python3 tests/zyklen.py
"""

import ast
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AUSSEN = {"demo", "tests", "patches", "keks_trace", "www", "config", "templates"}


def knoten(modul: str) -> str | None:
	teile = modul.split(".")
	if teile[0] != "keks_trace" or len(teile) < 2 or teile[1] in AUSSEN:
		return None
	return "keks_trace." + teile[1]


kanten = defaultdict(set)
for p in (REPO / "keks_trace").rglob("*.py"):
	modul = ".".join(p.relative_to(REPO).with_suffix("").parts).removesuffix(".__init__")
	von = knoten(modul)
	if not von:
		continue
	for n in ast.walk(ast.parse(p.read_text(encoding="utf-8"))):
		ziele = []
		if isinstance(n, ast.ImportFrom) and n.module:
			ziele = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
		elif isinstance(n, ast.Import):
			ziele = [a.name for a in n.names]
		for z in ziele:
			# "from keks_trace import palette" ergibt auch "keks_trace.palette"; nur echte Module zählen
			nach = knoten(z)
			if not nach or nach == von:
				continue
			ort = REPO / nach.replace(".", "/")
			if ort.with_suffix(".py").exists() or ort.is_dir():
				kanten[von].add(nach)

# starke Zusammenhangskomponenten (Tarjan)
index, low, stapel, auf, zyklen, zaehler = {}, {}, [], set(), [], [0]
sys.setrecursionlimit(10000)


def besuche(v):
	index[v] = low[v] = zaehler[0]
	zaehler[0] += 1
	stapel.append(v)
	auf.add(v)
	for w in sorted(kanten.get(v, ())):
		if w not in index:
			besuche(w)
			low[v] = min(low[v], low[w])
		elif w in auf:
			low[v] = min(low[v], index[w])
	if low[v] == index[v]:
		gruppe = []
		while True:
			w = stapel.pop()
			auf.discard(w)
			gruppe.append(w)
			if w == v:
				break
		if len(gruppe) > 1:
			zyklen.append(sorted(gruppe))


for v in sorted(kanten):
	if v not in index:
		besuche(v)

print(f"{len(kanten)} Module mit Imports geprüft")
for g in zyklen:
	namen = [x.removeprefix("keks_trace.") for x in g]
	wege = [
		f"{a.removeprefix('keks_trace.')} -> {b.removeprefix('keks_trace.')}"
		for a in g
		for b in sorted(kanten[a])
		if b in g
	]
	print(f"Zyklus: {', '.join(namen)}\n  " + "\n  ".join(wege))
print("keine Zyklen" if not zyklen else "")
sys.exit(1 if zyklen else 0)
