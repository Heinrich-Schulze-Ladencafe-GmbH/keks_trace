"""Paletten: NVE (SSCC) vergeben, prüfen und aus dem Scan lesen."""

import re

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import cint

from keks_trace.palette.basis import TEST_BASISNUMMER, _fehler


def pruefziffer(ziffern: str) -> int:
	"""GS1-Prüfziffer (Modulo 10, Gewichte 3/1 von rechts)."""
	summe = sum(int(z) * (3 if i % 2 == 0 else 1) for i, z in enumerate(reversed(ziffern)))
	return (10 - summe % 10) % 10


def standard_kreis() -> str | None:
	"""Standard-Nummernkreis (DocType NVE Nummernkreis); None, solange keiner angelegt ist."""
	return frappe.db.get_value("NVE Nummernkreis", {"standard": 1, "aktiv": 1})


def nve_neu(kreis: str | None = None) -> tuple[str, bool]:
	"""Nächste NVE (18 Ziffern) aus dem Nummernkreis (Standard: „Eigener“). Gibt (NVE, ist_test) zurück.

	Beim eigenen Kreis kommen Basisnummer und Reserveziffer aus dem Kreis, sonst aus den Einstellungen; der
	Zähler ist je Basisnummer derselbe wie bisher, die Nummern laufen also weiter. Nummern vom Kunden
	(Produktion für Dritte) folgen in einem späteren Schritt."""
	e = frappe.get_cached_doc("Keks Trace Einstellungen")
	k = frappe.get_cached_doc("NVE Nummernkreis", kreis) if kreis else None
	if k and not k.aktiv:
		_fehler(_("NVE-Nummernkreis {0} ist nicht aktiv.").format(kreis))
	if k and k.art != "Eigener":
		_fehler(_("NVE-Nummernkreis {0} ({1}) ist noch nicht freigeschaltet.").format(kreis, k.art))
	basis = "".join(c for c in ((k and k.basisnummer) or e.get("gs1_basisnummer") or "") if c.isdigit())
	test = not basis
	if test:
		basis = TEST_BASISNUMMER
	if not 7 <= len(basis) <= 10:
		_fehler(_("Die GS1-Basisnummer muss 7 bis 10 Ziffern haben."))
	ziffer = k.reserveziffer if k and k.reserveziffer not in (None, "") else e.get("nve_reserveziffer")
	reserve = str(cint(ziffer if ziffer is not None else 3) % 10)
	stellen = 16 - len(basis)
	laufend = getseries(f"KT-NVE-{reserve}{basis}-", stellen)
	koerper = f"{reserve}{basis}{laufend}"
	if len(koerper) != 17:
		_fehler(_("Nummernkreis für NVE ist erschöpft."))
	return koerper + str(pruefziffer(koerper)), test


def nve_aus_scan(code: str) -> str:
	"""Gescannte oder abgetippte NVE normalisieren: Leerzeichen, GS1-Präfix ]C1, (00) bzw. 00 entfernen."""
	c = re.sub(r"\s", "", code or "").replace("\x1d", "")  # auch abgetippt mit Leerzeichen
	for p in ("]C1", "]c1"):
		if c.startswith(p):
			c = c[len(p) :]
	c = c.replace("(", "").replace(")", "")
	if len(c) == 20 and c.startswith("00") and c.isdigit():
		c = c[2:]
	return c


def finde(code: str) -> str | None:
	nve = nve_aus_scan(code)
	return nve if nve and frappe.db.exists("Palette", nve) else None
