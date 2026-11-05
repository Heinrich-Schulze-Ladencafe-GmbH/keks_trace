"""Gemeinsame Hilfen der Terminals: Station, Rechte, Fehler, Buchungszeilen."""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from keks_trace.utils import artikel_stufe

EPS = 1e-6


class TerminalFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, TerminalFehler, title=_("Nicht möglich"))


def _silo_je_artikel():
	"""Artikel -> Silo (bei mehreren Silos für einen Artikel das zuletzt angelegte)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all(
			"Silo", filters={"aktiv": 1}, fields=["name", "artikel"], order_by="creation asc"
		)
	}


VORRAT = "Vorrat am Tisch"


def _vorraete():
	"""Artikel -> Vorrat am Tisch (offener Karton, Rolle, Behälter ohne Code)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all("Silo", filters={"aktiv": 1, "typ": VORRAT}, fields=["name", "artikel"])
	}


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


def _neue_charge(artikel, herstelldatum=None, charge_id=None, lieferant=None, verfall=None):
	if not charge_id:
		# Fertigware bekommt eine kurze Los-Nummer (passt auf Beutel und ins GS1-Etikett)
		kurz = artikel_stufe(artikel) == "Fertigware"
		praefix = ("L" if kurz else f"{artikel}-") + f"{now_datetime().strftime('%y%m%d')}-"
		n = frappe.db.count("Batch", {"name": ["like", praefix + "%"]}) + 1
		while frappe.db.exists("Batch", f"{praefix}{n:02d}"):
			n += 1
		charge_id = f"{praefix}{n:02d}"
	werte = {
		"doctype": "Batch",
		"item": artikel,
		"batch_id": charge_id,
		"manufacturing_date": herstelldatum,
		"supplier": lieferant,
	}
	if verfall:
		werte["expiry_date"] = verfall
	if artikel_stufe(artikel) == "Fertigware":
		werte["kt_los"] = charge_id
	return frappe.get_doc(werte).insert().name


def _se_zeile(z, s_warehouse=None, t_warehouse=None):
	uom = frappe.get_cached_value("Item", z["artikel"], "stock_uom")
	return {
		"item_code": z["artikel"],
		"qty": z["menge"],
		"transfer_qty": z["menge"],
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": z.get("charge"),
		"kt_traeger": z.get("behaelter"),
	}


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
