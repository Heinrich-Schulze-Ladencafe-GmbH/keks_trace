"""Einstieg für alle Prüfungen vor einer Fertigungs- oder Umpackbuchung.

Läuft als `before_validate`, also vor den ERPNext-eigenen Prüfungen, damit der Bediener
am Terminal eine klare deutsche Meldung bekommt.
"""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate

from keks_trace import kennzeichnung, rework, silo, sperre, traeger, vollstaendigkeit
from keks_trace.utils import artikel_stufe, eingangs_zeilen, zeilen_chargen


def pruefe_stock_entry(doc, method=None):
	silo.zuteilen(doc)  # zuerst: Silo-Entnahmen bekommen ihre Chargen, dann greifen alle Prüfungen
	sperre.pruefe_stock_entry(doc)
	kennzeichnung.pruefe_stock_entry(doc)
	if doc.purpose in ("Material Receipt", "Material Issue"):
		traeger.pruefe(doc)
		return
	if doc.purpose not in ("Manufacture", "Repack"):
		return
	_pruefe_verfall(doc)
	rework.pruefe(doc)
	traeger.pruefe(doc)
	vollstaendigkeit.pruefe(doc)


def _pruefe_verfall(doc):
	"""Keine abgelaufene Charge verbrauchen: Grundteig über Standzeit, Rework über Höchstalter, Füllung über MHD."""
	stichtag = getdate(doc.posting_date)
	for r in eingangs_zeilen(doc):
		for charge, _menge in zeilen_chargen(r):
			verfall, ursprung = frappe.db.get_value("Batch", charge, ["expiry_date", "kt_ursprungsdatum"])
			if not verfall or getdate(verfall) >= stichtag:
				continue
			stufe = artikel_stufe(r.item_code)
			if stufe == "Rework":
				frappe.throw(
					_(
						"Rework-Charge {0} ist abgelaufen (verwendbar bis {1}, Ursprung {2}). "
						"Bitte entsorgen, nicht einsetzen."
					).format(
						frappe.bold(charge), formatdate(verfall), formatdate(ursprung) if ursprung else "-"
					),
					title=_("Rework abgelaufen"),
				)
			frappe.throw(
				_("{0} {1} ist abgelaufen (verwendbar bis {2}). Einsatz gesperrt.").format(
					stufe or _("Charge"), frappe.bold(charge), formatdate(verfall)
				),
				title=_("Charge abgelaufen"),
			)
