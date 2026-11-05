"""Verweis-Check: alle Module importieren und jeden Pfad keks_trace.a.b im Repo auflösen.

Findet, was beim Umbenennen oder Verschieben von Modulen liegen bleibt: Pfade in hooks.py, in
frappe.enqueue, in /api/method/-Aufrufen im JavaScript, im Testserver-Skript und in der Doku.
Läuft ohne Frappe: frappe und erpnext sind Attrappen, die jeden Namen liefern.

	python3 tests/verweise.py
"""

import importlib
import importlib.abc
import importlib.machinery
import pkgutil
import re
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Beschrieben, aber noch nicht gebaut (docs/SCHNITTSTELLE-MESSGERAETE.md)
GEPLANT = ("keks_trace.messung",)


class Auto(types.ModuleType):
	def __getattr__(self, n):
		if n.startswith("__"):
			raise AttributeError(n)
		m = Auto(self.__name__ + "." + n)
		sys.modules[m.__name__] = m
		setattr(self, n, m)
		return m

	def __call__(self, *a, **k):
		if a and callable(a[0]) and not k:
			return a[0]
		return lambda f: f

	def __mro_entries__(self, bases):
		return (object,)


class Loader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
	def find_spec(self, name, path, target=None):
		if name.split(".")[0] in ("frappe", "erpnext"):
			return importlib.machinery.ModuleSpec(name, self, is_package=True)

	def create_module(self, spec):
		return Auto(spec.name)

	def exec_module(self, m):
		pass


sys.meta_path.insert(0, Loader())
sys.path.insert(0, str(REPO))
import frappe

frappe.ValidationError = type("ValidationError", (Exception,), {})
frappe.whitelist = lambda *a, **k: a[0] if a and callable(a[0]) else (lambda f: f)

fehler = []
import keks_trace

for info in pkgutil.walk_packages(keks_trace.__path__, "keks_trace."):
	try:
		importlib.import_module(info.name)
	except Exception as e:
		fehler.append(f"Import {info.name}: {type(e).__name__}: {e}")

pfade = {}
for p in REPO.rglob("*"):
	if not p.is_file() or p.suffix not in {".py", ".js", ".html", ".md", ".sh", ".txt", ".json"}:
		continue
	if (
		any(t in p.parts for t in (".git", "__pycache__", ".ruff_cache", "node_modules"))
		or p == Path(__file__).resolve()
	):
		continue
	for m in re.finditer(r"keks_trace(?:\.\w+)+", p.read_text(encoding="utf-8", errors="ignore")):
		pfade.setdefault(m[0].rstrip("."), set()).add(str(p.relative_to(REPO)))


def aufloesen(pfad):
	teile = pfad.split(".")
	for i in range(len(teile), 0, -1):
		try:
			obj = importlib.import_module(".".join(teile[:i]))
		except ModuleNotFoundError:
			continue
		for t in teile[i:]:
			obj = getattr(obj, t)
		return True
	return False


for pfad, wo in sorted(pfade.items()):
	# Präfixe wie "keks_trace.terminal." + methode sind Module: auch ok
	if pfad.startswith(GEPLANT):
		continue
	try:
		ok = aufloesen(pfad)
	except AttributeError:
		ok = False
	if not ok:
		fehler.append(f"Pfad {pfad} nicht auflösbar (in {', '.join(sorted(wo))})")
print(f"{len(pfade)} Pfade geprüft")
print("\n".join(fehler) or "alles auflösbar")
sys.exit(1 if fehler else 0)
