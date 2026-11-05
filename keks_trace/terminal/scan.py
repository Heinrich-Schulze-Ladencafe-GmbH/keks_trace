"""Scan auflösen: Behälter, Silo, Palette, Gebinde, Los oder Charge; Info-Scan und Akte."""

import frappe
from frappe import _
from frappe.utils import formatdate, getdate, nowdate

from keks_trace import akte as akte_modul
from keks_trace import palette as paletten
from keks_trace.buchung.basis import _fehler
from keks_trace.buchung.scan import aufloesen


@frappe.whitelist()
def info(code: str) -> dict:
	"""Info-Scan: alles Wichtige zu einem Code."""
	from keks_trace import silo as silo_modul

	r = aufloesen(code)
	if r["typ"] == "palette":
		r.update(paletten.info(r["palette"]))
		return r
	if r["typ"] == "silo":
		i = silo_modul.info(r["silo"])
		r.update({"bestand": i["bestand"], "moeglich_enthalten": i["moeglich_enthalten"]})
	if r.get("charge"):
		b = frappe.db.get_value(
			"Batch",
			r["charge"],
			[
				"item_name",
				"kt_chargen_stufe",
				"kt_status",
				"kt_sperrgrund",
				"manufacturing_date",
				"expiry_date",
				"kt_backtag",
			],
			as_dict=True,
		)
		r.update(
			{
				"artikelname": b.item_name,
				"stufe": b.kt_chargen_stufe,
				"sperrstatus": b.kt_status,
				"sperrgrund": b.kt_sperrgrund,
				"hergestellt": formatdate(b.manufacturing_date) if b.manufacturing_date else None,
				"backtag": formatdate(b.kt_backtag) if b.kt_backtag else None,
				"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
				"abgelaufen": bool(b.expiry_date and getdate(b.expiry_date) < getdate(nowdate())),
			}
		)
	if r.get("artikel") and not r.get("artikelname"):
		r["artikelname"] = frappe.get_cached_value("Item", r["artikel"], "item_name")
	if r["typ"] == "charge":
		r["fundstellen"] = akte_modul.fundstellen(r["charge"])  # „Wo ist dieses Los?“
	return r


@frappe.whitelist()
def akte(code: str) -> dict:
	"""Lebenslauf einer Palette oder eines Behälters (akte.py)."""
	return akte_modul.akte(code)


@frappe.whitelist()
def herkunft(code: str) -> dict:
	"""Woraus besteht das? Für eine Charge bzw. ein Los (auch Kartonetikett) oder einen Behälter mit Inhalt."""
	r = aufloesen(code)
	charge = r.get("charge")
	if not charge:
		_fehler(
			_("Zu {0} gibt es keine Charge. Bei einer Palette bitte das Los wählen.").format(
				frappe.bold(code)
			)
		)
	return akte_modul.herkunft(charge)
