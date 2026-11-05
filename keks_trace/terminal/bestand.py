"""Bestand je Charge und Lager: Chargen im Lager, reservierte Ware, Quellen für eine Zutat."""

import frappe
from frappe.utils import flt

from keks_trace.buchung.bestand import _lager_chargen, _offene_auftraege


def _reserviert(charge: str | None) -> str | None:
	"""Für welchen offenen Kundenauftrag eine Charge hergestellt wurde (sonst frei)."""
	if not charge:
		return None
	auftrag = frappe.db.get_value("Batch", charge, "kt_kundenauftrag")
	return auftrag if auftrag in _offene_auftraege([auftrag]) else None


def _verfuegbar(artikel: str) -> float:
	return flt(sum(c["menge"] for c in _lager_chargen(artikel)), 3)


def _lager_chargen_alle(artikel: str) -> list[dict]:
	"""Wie _lager_chargen, aber auch die für andere Aufträge reservierte Ware (zum Zählen)."""
	ergebnis = []
	for auftrag in [
		None,
		*_offene_auftraege(
			frappe.get_all(
				"Batch", {"item": artikel, "kt_kundenauftrag": ["is", "set"]}, pluck="kt_kundenauftrag"
			)
		),
	]:
		ergebnis += [c for c in _lager_chargen(artikel, auftrag) if c["auftrag"] == auftrag]
	return ergebnis
