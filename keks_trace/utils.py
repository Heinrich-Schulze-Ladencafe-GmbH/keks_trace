"""Gemeinsame Hilfsfunktionen für Stock-Entry-Zeilen und Chargen."""

import frappe
from frappe.utils import flt


def zeilen_menge(row) -> float:
	"""Menge einer Zeile in Lagereinheit, auch wenn ERPNext transfer_qty noch nicht gesetzt hat."""
	if flt(row.get("transfer_qty")):
		return flt(row.transfer_qty)
	return flt(row.get("qty")) * flt(row.get("conversion_factor") or 1)


def eingangs_zeilen(doc):
	"""Verbrauchte Zeilen: nur Quelllager."""
	return [r for r in doc.items if r.s_warehouse and not r.t_warehouse]


def ausgangs_zeilen(doc):
	"""Erzeugte Zeilen: nur Ziellager."""
	return [r for r in doc.items if r.t_warehouse and not r.s_warehouse]


def zeilen_chargen(row) -> list[tuple[str, float]]:
	"""(Charge, Menge) einer Zeile.

	Bevorzugt das Serial-and-Batch-Bundle (nach dem Buchen immer vorhanden,
	kann mehrere Chargen je Zeile enthalten), sonst das Feld batch_no.
	"""
	bundle = row.get("serial_and_batch_bundle")
	if bundle:
		eintraege = frappe.get_all(
			"Serial and Batch Entry",
			filters={"parent": bundle},
			fields=["batch_no", "qty"],
		)
		chargen = [(e.batch_no, abs(flt(e.qty))) for e in eintraege if e.batch_no]
		if chargen:
			return chargen
	if row.get("batch_no"):
		return [(row.batch_no, zeilen_menge(row))]
	return []


def artikel_stufe(item_code: str) -> str | None:
	return frappe.get_cached_value("Item", item_code, "kt_chargen_stufe")


def allergene(gruppe: str | None) -> set[str]:
	"""Allergene einer Allergengruppe als Menge (Groß-/Kleinschreibung egal)."""
	if not gruppe:
		return set()
	text = frappe.get_cached_value("Allergengruppe", gruppe, "allergene") or ""
	return {a.strip().lower() for a in text.replace(";", ",").split(",") if a.strip()}
