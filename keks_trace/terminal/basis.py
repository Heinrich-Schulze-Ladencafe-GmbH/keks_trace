"""Gemeinsame Hilfen der Terminals: Station, Rechte, Fehler, Buchungszeilen."""

import json

import frappe
from frappe import _

from keks_trace.buchung.basis import _fehler


def _silo_filter(s) -> dict:
	"""Behälter, die eine Station sieht: die ihrer Linie; Stationen ohne Linie die ohne Linie."""
	return {"aktiv": 1, "linie": s.linie if s.linie else ["is", "not set"]}


def _station(station):
	if not station or not frappe.db.exists("Terminal Station", station):
		_fehler(_("Station {0} ist nicht eingerichtet.").format(station or "-"))
	return frappe.get_cached_doc("Terminal Station", station)


FUNKTIONSNAMEN = {
	"herstellen": "Herstellen",
	"rework": "Rework",
	"silo": "Silo leer melden",
	"wareneingang": "Wareneingang",
	"paletten": "Paletten",
	"lieferung": "Lieferung",
	"umlagern": "Umlagern",
	"linie": "An die Linie geben",
	"packstation": "Packstation",
	"palette_fertig": "Palette fertig",
}


def _darf(s, funktion):
	"""Serverseitig prüfen, dass die Station die Funktion hat (nicht nur Knöpfe ausblenden)."""
	if not s.get("f_" + funktion):
		_fehler(
			_("{0} ist an der Station {1} nicht freigeschaltet.").format(
				FUNKTIONSNAMEN.get(funktion, funktion), s.name
			)
		)


def _liste(wert):
	if isinstance(wert, str):
		return json.loads(wert or "[]")
	return wert or []


def _mit_hinweis(zeilen: list[dict]) -> None:
	"""Hinweis des Büros am Kundenauftrag („mit Clip“ …) an jede Zeile hängen (Feld kt_hinweis_produktion)."""
	namen = {z["auftrag"] for z in zeilen if z.get("auftrag")}
	if not namen:
		return
	text = dict(
		frappe.get_all(
			"Sales Order",
			filters={"name": ["in", list(namen)]},
			fields=["name", "kt_hinweis_produktion"],
			as_list=True,
		)
	)
	for z in zeilen:
		z["hinweis"] = (text.get(z.get("auftrag")) or "").strip() or None


def _meldungen():
	"""Hinweise (msgprint) aus dem Buchen als Text einsammeln."""
	texte = []
	for m in frappe.local.message_log or []:
		try:
			m = json.loads(m) if isinstance(m, str) else m
		except ValueError:
			m = {"message": m}
		text = frappe.utils.strip_html(str(m.get("message") or m))
		if text and text not in texte:
			texte.append(text)
	frappe.local.message_log = []
	return texte
