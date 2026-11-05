"""Linie: gemeinsame Konstanten, Fehler, Station und Linie, laufender Auftrag, Hinweise vom Büro."""

import frappe
from frappe import _

from keks_trace import palette as paletten

EPS = 1e-6


AUF_DER_LINIE = ("Backware", "Ware lose")  # entstehen auf der Linie ohne eigene Buchung


LINIENREST = "Linienrest"


class LinienFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, LinienFehler, title=_("Linie"))


def _station(name):
	return frappe.get_cached_doc("Terminal Station", name)


def _linie(s):
	if not s.linie:
		_fehler(_("Station {0} ist keiner Linie zugeordnet.").format(s.name))
	return frappe.get_cached_doc("Linie", s.linie)


def _menge_text(artikel, kg):
	return paletten.zerlegen(artikel, kg) if kg else "0"


def _laufender(s):
	name = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	if not name:
		_fehler(_("Bitte zuerst den Produktionsauftrag wählen."))
	pa = frappe.get_doc("Produktionsauftrag", name)
	if pa.status != "Läuft":
		_fehler(_("Auftrag {0} ist {1}. Bitte einen laufenden Auftrag wählen.").format(pa.name, pa.status))
	return pa


def hinweise(pa) -> list[dict]:
	"""Hinweise vom Büro zum Auftrag: am Produktionsauftrag und am Kundenauftrag. Das Terminal zeigt sie groß."""
	out = []
	if (pa.bemerkung or "").strip():
		out.append({"von": _("Produktionsauftrag"), "text": pa.bemerkung.strip()})
	if pa.kundenauftrag:
		text = (frappe.db.get_value("Sales Order", pa.kundenauftrag, "kt_hinweis_produktion") or "").strip()
		if text:
			out.append({"von": _("Kundenauftrag {0}").format(pa.kundenauftrag), "text": text})
	return out


def _hat(artikel, uom):
	return bool(frappe.db.exists("UOM Conversion Detail", {"parent": artikel, "uom": uom}))
