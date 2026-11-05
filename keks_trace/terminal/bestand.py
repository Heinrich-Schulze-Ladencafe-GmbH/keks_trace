"""Bestand je Charge und Lager: Chargen im Lager, reservierte Ware, Quellen für eine Zutat."""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, nowdate

from keks_trace.terminal.basis import EPS, _fehler


def _offene_auftraege(namen) -> set:
	"""Welche dieser Kundenaufträge noch offen sind (gebucht, nicht erledigt/geschlossen)."""
	namen = [n for n in set(namen or ()) if n]
	if not namen:
		return set()
	return set(
		frappe.get_all(
			"Sales Order",
			{"name": ["in", namen], "docstatus": 1, "status": ["not in", ["Completed", "Closed"]]},
			pluck="name",
		)
	)


def _reserviert(charge: str | None) -> str | None:
	"""Für welchen offenen Kundenauftrag eine Charge hergestellt wurde (sonst frei)."""
	if not charge:
		return None
	auftrag = frappe.db.get_value("Batch", charge, "kt_kundenauftrag")
	return auftrag if auftrag in _offene_auftraege([auftrag]) else None


def _lager_chargen(artikel: str, auftrag: str | None = None) -> list[dict]:
	"""Chargen eines Artikels mit Bestand im Lager (nicht im Vorrat/Silo/Lagerverkauf), ältestes MHD zuerst.

	Zum Antippen ohne Scanner. Reserviert (für einen offenen Kundenauftrag hergestellt): nur für diesen Auftrag,
	dort zuerst. Sonderanfertigung nach Auftrag: mit Auftrag nur die eigene Ware.
	"""
	# nicht aus Silo/Vorrat, Lagerverkauf oder von einer Linie (das gehört dem Produktionsauftrag)
	aus = list(
		set(frappe.get_all("Silo", pluck="warehouse"))
		| _verkaufslager()
		| set(frappe.get_all("Linie", pluck="lagerort"))
	) or [""]
	# Linienlager zuerst: es ist der Puffer an der Linie und wird zuerst leer verpackt (F7)
	linienlager = tuple(frappe.get_all("Linie", {"linienlager": ["is", "set"]}, pluck="linienlager")) or ("",)
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, sum(sbe.qty) as menge, b.expiry_date as mhd, b.kt_kundenauftrag as auftrag,
			sum(case when sbe.warehouse in %(ll)s then sbe.qty else 0 end) > 0.000001 as linienlager
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabBatch` b on b.name = sbe.batch_no
		where b.item = %(artikel)s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			and ifnull(b.kt_status, '') != 'Gesperrt' and sbe.warehouse not in %(aus)s
		group by sbe.batch_no, b.expiry_date, b.creation, b.kt_kundenauftrag
		having sum(sbe.qty) > 0.000001
		order by linienlager desc, b.expiry_date is null, b.expiry_date, b.creation
		limit 200
		""",
		{"artikel": artikel, "aus": tuple(aus), "ll": linienlager},
		as_dict=True,
	)
	offen = _offene_auftraege(z.auftrag for z in zeilen)
	sonder = cint(frappe.get_cached_value("Item", artikel, "kt_nach_auftrag"))
	ergebnis = []
	for z in zeilen:
		reserviert = z.auftrag if z.auftrag in offen else None
		if reserviert and reserviert != auftrag:
			continue  # gehört einem anderen Auftrag
		if sonder and auftrag and reserviert != auftrag:
			continue  # Sonderanfertigung: nur die für diesen Auftrag gemachte
		ergebnis.append(
			{
				"charge": z.charge,
				"menge": flt(z.menge, 3),
				"mhd": formatdate(z.mhd) if z.mhd else None,
				"linienlager": cint(z.linienlager),
				"auftrag": reserviert,
			}
		)
	if auftrag:
		ergebnis.sort(key=lambda x: x["auftrag"] != auftrag)  # eigene zuerst, sonst Reihenfolge wie oben
	return ergebnis[:30]


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


def charge_lager(charge) -> dict[str, float]:
	"""Bestand einer Charge je Lagerort."""
	zeilen = frappe.db.sql(
		"""
		select sbe.warehouse, sum(sbe.qty) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
		group by sbe.warehouse
		""",
		charge,
		as_dict=True,
	)
	return {z.warehouse: flt(z.menge) for z in zeilen if flt(z.menge) > EPS}


def _pruefe_charge(charge, artikel):
	status, grund, verfall = frappe.db.get_value(
		"Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"]
	)
	if status == "Gesperrt":
		_fehler(_("Charge {0} ist gesperrt: {1}").format(frappe.bold(charge), grund or "-"))
	if verfall and getdate(verfall) < getdate(nowdate()):
		_fehler(
			_("Charge {0} ({1}) ist abgelaufen seit {2}. Nicht verwenden.").format(
				frappe.bold(charge), artikel, formatdate(verfall)
			)
		)


def _quellen(artikel: str, auftrag: str | None = None) -> list[dict]:
	"""Wo liegt ein Artikel (ohne Silo/Vorrat/Lagerverkauf)? Behälter einzeln, älteste Ware zuerst."""
	ergebnis = []
	for c in _lager_chargen(artikel, auftrag):
		rest = c["menge"]
		for t in frappe.get_all(
			"Produkttraeger", {"status": "Belegt", "charge": c["charge"]}, ["code", "menge"], order_by="code"
		):
			m = min(flt(t.menge), rest)
			if m > EPS:
				ergebnis.append({**c, "code": t.code, "behaelter": t.code, "menge": flt(m, 3)})
				rest -= m
		if rest > EPS:
			ergebnis.append({**c, "code": c["charge"], "behaelter": None, "menge": flt(rest, 3)})
	return ergebnis


def _verkaufslager() -> set:
	"""Lagerorte des Lagerverkaufs: daraus wird nicht geliefert oder umgelagert."""
	return set(frappe.get_all("Warehouse", filters={"kt_lagerverkauf": 1}, pluck="name"))
