"""Linie: Linienrezept (Stückliste durch die Stufen auf der Linie aufgelöst), Bestand und Verbrauch auf der Linie."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from keks_trace import buchung
from keks_trace.linienbuchung.basis import AUF_DER_LINIE, EPS
from keks_trace.utils import artikel_stufe


def linienrezept(artikel: str, tiefe: int = 0) -> dict[str, float]:
	"""{Zutat: Menge je 1 Lagereinheit Fertigware}, durch Backware und lose Ware aufgelöst."""
	ergebnis = defaultdict(float)
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom or tiefe > 6:
		return ergebnis
	menge = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"]):
		je = flt(z.stock_qty) / menge
		if artikel_stufe(z.item_code) in AUF_DER_LINIE:
			for k, v in linienrezept(z.item_code, tiefe + 1).items():
				ergebnis[k] += je * v
		else:
			ergebnis[z.item_code] += je
	return dict(ergebnis)


def bestand(auftrag: str) -> list[dict]:
	"""Was für diesen Auftrag auf der Linie liegt: je Charge, älteste Zuführung zuerst."""
	lager = frappe.db.get_value(
		"Linie", frappe.db.get_value("Produktionsauftrag", auftrag, "linie"), "lagerort"
	)
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no as charge, b.item as artikel, sum(sbe.qty) as menge,
			min(case when sbe.qty > 0 then sbb.posting_datetime end) as zugefuehrt
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		join `tabBatch` b on b.name = sbe.batch_no
		where sbe.warehouse = %(lager)s and se.kt_produktionsauftrag = %(pa)s
			and sbb.docstatus = 1 and sbb.is_cancelled = 0
		group by sbe.batch_no, b.item
		having sum(sbe.qty) > 0.000001
		order by zugefuehrt, sbe.batch_no
		""",
		{"lager": lager, "pa": auftrag},
		as_dict=True,
	)
	return [{**z, "menge": flt(z.menge, 6)} for z in zeilen]


def rework_ersatz() -> dict[str, set]:
	"""{Rework-Artikel: Teige, die es laut aktiver Rework-Regel ersetzen darf}."""
	ersatz = defaultdict(set)
	for r in frappe.get_all("Rework Regel", {"aktiv": 1}, ["rework_artikel", "ziel_artikel"]):
		ersatz[r.rework_artikel].add(r.ziel_artikel)
	return ersatz


def _verbrauch(pa, artikel_aus, kg, linie):
	"""Verbrauch für kg von artikel_aus laut Linienrezept: erst was für diesen Auftrag auf der Linie liegt
	(Teig vom Kneter), der Rest (Füllung, Glasur, Schokolade, Packmittel) automatisch aus dem Lager bzw.
	Tank, älteste zuerst. Nachgefüllt wird an der Linie nicht gebucht. Gibt (zeilen, hinweise, vom_teig)."""

	vorrat = defaultdict(list)
	ersatz = rework_ersatz()
	for z in bestand(pa.name):
		vorrat[z["artikel"]].append(z)
		for ziel in ersatz.get(z["artikel"], ()):
			vorrat[ziel].append(z)  # Rework am Kneter zugeführt: wird mit dem Teig verbraucht
	for liste in vorrat.values():
		liste.sort(key=lambda z: (z["zugefuehrt"] or now_datetime(), z["charge"]))
	silos = buchung._silo_je_artikel()
	zeilen, hinweise, vom_teig = [], [], False
	for artikel, je in linienrezept(artikel_aus).items():
		bedarf = je * kg
		offen = bedarf
		for z in vorrat.get(artikel, []):
			if offen <= EPS:
				break
			nimm = min(offen, z["menge"])
			if nimm <= EPS:
				continue
			z["menge"] -= nimm  # dieselbe Charge kann für mehrere Zutaten stehen (Rework)
			zeilen.append(
				{
					"artikel": z["artikel"],
					"charge": z["charge"],
					"menge": flt(nimm, 6),
					"lager": linie.lagerort,
				}
			)
			offen -= nimm
			vom_teig = vom_teig or artikel_stufe(artikel) != "Packmittel"
		quellen = (
			[{"code": silos[artikel], "menge": offen}] if artikel in silos else buchung._quellen(artikel)
		)
		for q in quellen:
			if offen <= EPS:
				break
			nimm = min(offen, q["menge"])
			try:
				z = buchung._zeile(q["code"], nimm)
			except frappe.ValidationError:
				continue
			zeilen.append({**z, "menge": flt(nimm, 6)})
			offen -= nimm
		if offen > max(bedarf * 0.005, EPS):
			hinweise.append(
				_("{0}: laut Rezept {1} {3}, im Lager nur {2} {3}. Bestand prüfen.").format(
					frappe.get_cached_value("Item", artikel, "item_name"),
					flt(bedarf, 2),
					flt(bedarf - offen, 2),
					frappe.get_cached_value("Item", artikel, "stock_uom"),
				)
			)
	frappe.local.message_log = []
	return zeilen, hinweise, vom_teig
