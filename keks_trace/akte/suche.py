"""Akte: Wo ist dieses Los? Alle offenen Paletten mit einem Los."""

from collections import defaultdict

import frappe

from keks_trace import druckprotokoll
from keks_trace import palette as paletten
from keks_trace.akte.basis import EPS, MAX_FUNDSTELLEN, _bis, _los, _person, _zeit
from keks_trace.akte.lebenslauf import _bewegungen


def _kurz(nve: str) -> dict:
	"""Lebenslauf in einer Zeile: wann und von wem gepackt, letzte Bewegung, letzter Etikettendruck."""
	zeilen = _bewegungen(nve)
	zu = [z for z in zeilen if z.richtung == "Zugang"]
	letzte = zeilen[-1] if zeilen else None
	personen = sorted({_person(z.nutzer) for z in zu if z.nutzer})
	stationen = sorted({z.station for z in zu if z.station})
	druck = druckprotokoll.drucke(palette=nve, anzahl=1)
	return {
		"gepackt": (_zeit(zu[0].zeitpunkt) + _bis(zu[0].zeitpunkt, zu[-1].zeitpunkt) if zu else None),
		"stationen": ", ".join(stationen),
		"personen": ", ".join(personen),
		"letzte": (
			f"{letzte.art} {_zeit(letzte.zeitpunkt)}" + (f" · {letzte.station}" if letzte.station else "")
		)
		if letzte
		else None,
		"letzter_druck": (f"{_zeit(druck[0].zeitpunkt)} ({druck[0].grund})" if druck else None),
	}


def fundstellen(charge: str) -> dict:
	"""Alle Stellen, an denen das Los gerade liegt: aktive Paletten, Behälter, lose Ware."""
	if not charge:
		return {"paletten": [], "behaelter": [], "lose": None}
	je_palette = defaultdict(list)
	for z in paletten.paletten_fuer([charge]):
		if z.anzahl_jetzt > EPS and z.status in paletten.AKTIV:
			je_palette[z.palette].append(z)
	liste = []
	for nve, zeilen in list(je_palette.items())[:MAX_FUNDSTELLEN]:
		i = paletten.info(nve)
		liste.append(
			{
				"nve": nve,
				"status": i["status"],
				"art": i["art"],
				"kunde": i["kunde"],
				"dieses_los": ", ".join(paletten._n(z.anzahl_jetzt, z.einheit) for z in zeilen),
				"auf_palette": i.get("auf_palette"),
				# Gesamtinhalt nur, wenn noch andere Lose auf der Palette stehen
				"inhalt": i["kartons"] if len(i["positionen"]) > 1 else None,
				"etikett_aktuell": i["etikett_aktuell"],
				**_kurz(nve),
			}
		)
	behaelter = frappe.get_all(
		"Produkttraeger",
		filters={"charge": charge},
		fields=["name as code", "typ", "status", "menge"],
		limit=MAX_FUNDSTELLEN,
	)
	artikel = frappe.db.get_value("Batch", charge, "item")
	lose = paletten.lose(charge)
	return {
		"los": _los(charge),
		"paletten": liste,
		"mehr_paletten": max(0, len(je_palette) - MAX_FUNDSTELLEN),
		"behaelter": behaelter,
		"lose": paletten.zerlegen(artikel, lose) if lose > EPS and artikel else None,
	}
