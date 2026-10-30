"""Vollständigkeit einer Fertigungsbuchung gegen die Stückliste (Rezept).

Wird eine Zutat laut Rezept nicht gescannt, sieht die Kette vollständig aus, ist es aber nicht.
Diese Prüfung meldet fehlende Zutaten je nach Einstellung als Warnung oder blockiert die Buchung.
Zusätzliche Zutaten (z. B. Rework) sind immer erlaubt.
"""

import frappe
from frappe import _

from keks_trace.utils import ausgangs_zeilen, eingangs_zeilen


def modus() -> str:
	return frappe.db.get_single_value("Keks Trace Einstellungen", "vollstaendigkeit") or "Warnen"


def pruefe(doc):
	doc.flags.kt_fehlende_zutaten = []
	if doc.purpose != "Manufacture" or modus() == "Aus":
		return

	ausgaenge = [r for r in ausgangs_zeilen(doc) if r.is_finished_item] or ausgangs_zeilen(doc)
	if not ausgaenge:
		return
	ziel = ausgaenge[0]
	bom = (
		ziel.get("bom_no")
		or doc.get("bom_no")
		or frappe.db.get_value(
			"BOM", {"item": ziel.item_code, "is_active": 1, "is_default": 1, "docstatus": 1}
		)
	)
	if not bom:
		return

	rezept = {
		z.item_code: z.item_name
		for z in frappe.get_all("BOM Item", filters={"parent": bom}, fields=["item_code", "item_name"])
	}
	gescannt = {r.item_code for r in eingangs_zeilen(doc)}
	fehlend = [code for code in rezept if code not in gescannt]
	if not fehlend:
		return

	doc.flags.kt_fehlende_zutaten = fehlend
	text = _("Laut Rezept {0} fehlen diese Zutaten in der Buchung von {1}: {2}").format(
		bom, frappe.bold(ziel.item_code), ", ".join(f"{c} ({rezept[c]})" for c in fehlend)
	)
	if modus() == "Blockieren":
		frappe.throw(text + ". " + _("Bitte nachscannen."), title=_("Zutat nicht gescannt"))
	frappe.msgprint(text, title=_("Zutat nicht gescannt"), indicator="orange", alert=True)
