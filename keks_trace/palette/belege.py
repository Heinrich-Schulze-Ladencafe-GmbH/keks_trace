"""Paletten: Hooks an Lieferschein und Lagerbuchung (Prüfen, Buchen, Storno), Abgleich."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace.palette.basis import AKTIV, EPS, _fehler
from keks_trace.palette.bestand import _status_pruefen, auf_paletten, inhalt, kartons, lagerbestand
from keks_trace.palette.bewegung import _bewegung, _position
from keks_trace.palette.einheit import faktor
from keks_trace.palette.versandkarton import karton_abnehmen
from keks_trace.utils import versandfaehig


def pruefe_lieferung(doc, method=None):
	"""Positionen mit Palette: so viel muss drauf sein. Ohne Palette: so viel muss lose da sein."""
	if doc.get("is_return"):
		return
	von_palette, lose_bedarf = defaultdict(float), defaultdict(float)
	for r in doc.items:
		if not r.batch_no:
			continue
		menge = flt(r.qty) * (flt(r.conversion_factor) or 1)
		if r.get("kt_palette"):
			status = frappe.db.get_value("Palette", r.kt_palette, "status")
			if status not in AKTIV:
				_fehler(_("Palette {0} ist {1}.").format(r.kt_palette, (status or "unbekannt").lower()))
			anzahl, einheit = _gezaehlt(r)
			von_palette[(r.kt_palette, r.batch_no, einheit)] += anzahl
		elif versandfaehig(r.item_code):
			lose_bedarf[r.batch_no] += menge

	for (palette, charge, einheit), anzahl in von_palette.items():
		pos = _position(palette, charge, einheit)
		if not pos or anzahl > pos["anzahl"] + EPS:
			_fehler(
				_("Auf Palette {0} sind von Los {1} nur {2} {3}, geliefert werden sollen {4}.").format(
					palette, charge, flt(pos["anzahl"], 3) if pos else 0, einheit, flt(anzahl, 3)
				)
			)
	for charge, menge in lose_bedarf.items():
		frei = flt(lagerbestand(charge) - auf_paletten(charge, ohne_beleg=doc.name))
		if menge > frei + 1e-4:
			paletten = frappe.db.sql_list(
				"""select distinct palette from `tabPaletten Bewegung` where charge = %s""", charge
			)
			paletten = [p for p in paletten if _position_charge(p, charge)]
			if not paletten:
				_fehler(_("Von Los {0} sind nur {1} am Lager.").format(charge, flt(frei, 3)))
			_fehler(
				_(
					"Von Los {0} sind nur {1} lose am Lager, der Rest steht auf Palette {2}. Bitte die Palette angeben."
				).format(charge, flt(frei, 3), ", ".join(paletten) or "-")
			)


def _gezaehlt(r):
	"""Am Terminal gezählte Anzahl und Einheit einer Lieferscheinposition (sonst Menge/Einheit der Zeile)."""
	if r.get("kt_einheit") and flt(r.get("kt_anzahl")):
		return flt(r.kt_anzahl), r.kt_einheit
	return flt(r.qty), r.uom


def _position_charge(palette, charge):
	return any(x["charge"] == charge for x in inhalt(palette))


def lieferung_on_submit(doc, method=None):
	if doc.get("is_return"):
		return
	betroffen = set()
	for r in doc.items:
		if r.get("kt_palette") and r.batch_no:
			anzahl, einheit = _gezaehlt(r)
			_bewegung(
				r.kt_palette, "Abgang", "Lieferung", r.batch_no, anzahl, einheit,
				doc.get("kt_station"), "Delivery Note", doc.name,
			)  # fmt: skip
			betroffen.add(r.kt_palette)
	versendet = {"status": "Versendet", "lieferschein": doc.name, "kunde": doc.customer}
	for palette in betroffen:
		if not inhalt(palette) and not kartons(palette):
			frappe.db.set_value("Palette", palette, versendet)
	# Versandkartons von einer Palette: ganze Palette weg → auch sie versendet; sonst Karton von ihr abnehmen
	aussen = defaultdict(list)
	for k in betroffen:
		a = frappe.db.get_value("Palette", k, "auf_palette")
		if a:
			aussen[a].append(k)
	for a, ks in aussen.items():
		if not inhalt(a) and not kartons(a):
			frappe.db.set_value("Palette", a, versendet)
		else:
			for k in ks:
				if frappe.db.get_value("Palette", k, "status") == "Versendet":
					karton_abnehmen(k, doc.get("kt_station"), doc.name)


def lieferung_on_cancel(doc, method=None):
	bewegungen = frappe.get_all(
		"Paletten Bewegung",
		filters={"beleg_typ": "Delivery Note", "beleg": doc.name, "art": "Lieferung"},
		fields=["palette", "charge", "anzahl", "einheit"],
	)
	for b in bewegungen:
		_bewegung(
			b.palette, "Zugang", "Storno Lieferung", b.charge, b.anzahl, b.einheit,
			beleg_typ="Delivery Note", beleg=doc.name,
		)  # fmt: skip
	zurueck = {b.palette for b in bewegungen} | set(
		frappe.get_all("Palette", filters={"lieferschein": doc.name}, pluck="name")
	)  # auch Paletten, die nur Versandkartons trugen
	for palette in zurueck:
		if frappe.db.get_value("Palette", palette, "status") in ("Versendet", "Leer"):
			frappe.db.set_value("Palette", palette, {"status": "Geschlossen", "lieferschein": None})


VERBRAUCH = ("Manufacture", "Repack", "Material Issue")


def se_on_submit(doc, method=None):
	"""Verbrauch eines Loses, das auf Paletten steht (z. B. lose Ware im Karton nach Bedarf verpackt, Rohlinge
	garniert): was am Lager fehlt, geht von den Paletten ab (älteste Position zuerst), damit Palette und Lager
	übereinstimmen. Umlagern und Lieferung buchen ihre Paletten selbst."""
	if doc.purpose not in VERBRAUCH:
		return
	for charge in {r.batch_no or _charge_aus_bundle(r) for r in doc.items if r.s_warehouse}:
		if not charge:
			continue
		zuviel = auf_paletten(charge) - lagerbestand(charge)
		if zuviel <= 1e-4:
			continue
		paletten = frappe.db.sql_list(
			"""select palette from `tabPaletten Bewegung` where charge = %s
			group by palette having sum(if(richtung = 'Zugang', menge, -menge)) > 0.000001
			order by min(zeitpunkt)""",
			charge,
		)
		for palette in paletten:
			for pos in inhalt(palette):
				if zuviel <= 1e-4:
					break
				if pos["charge"] != charge:
					continue
				f = faktor(pos["artikel"], pos["einheit"])
				nimm = min(zuviel, pos["menge"])
				_bewegung(palette, "Abgang", "Verbrauch", charge, nimm / f, pos["einheit"],
						  doc.get("kt_station"), "Stock Entry", doc.name)  # fmt: skip
				zuviel -= nimm
			_status_pruefen(palette)


def abgleich() -> int:
	"""Einmalig: Lose, die laut Paletten mehr sind als am Lager (Verbrauch vor diesem Abgleich gebucht),
	auf den Paletten korrigieren. Gibt die Zahl der korrigierten Lose zurück."""
	zahl = 0
	for charge in frappe.db.sql_list(
		"""select charge from `tabPaletten Bewegung` group by charge
		having sum(if(richtung = 'Zugang', menge, -menge)) > 0.000001"""
	):
		zuviel = auf_paletten(charge) - lagerbestand(charge)
		if zuviel <= 1e-4:
			continue
		zahl += 1
		for palette in frappe.db.sql_list(
			"select distinct palette from `tabPaletten Bewegung` where charge = %s order by palette", charge
		):
			for pos in inhalt(palette):
				if zuviel <= 1e-4 or pos["charge"] != charge:
					continue
				nimm = min(zuviel, pos["menge"])
				_bewegung(palette, "Abgang", "Korrektur", charge, nimm / faktor(pos["artikel"], pos["einheit"]),
						  pos["einheit"])  # fmt: skip
				zuviel -= nimm
			_status_pruefen(palette)
	return zahl


def se_on_cancel(doc, method=None):
	for b in frappe.get_all(
		"Paletten Bewegung",
		filters={"beleg_typ": "Stock Entry", "beleg": doc.name, "art": "Verbrauch"},
		fields=["palette", "charge", "anzahl", "einheit"],
	):
		_bewegung(b.palette, "Zugang", "Storno Verbrauch", b.charge, b.anzahl, b.einheit,
				  beleg_typ="Stock Entry", beleg=doc.name)  # fmt: skip
		if frappe.db.get_value("Palette", b.palette, "status") == "Leer":
			frappe.db.set_value("Palette", b.palette, "status", "Offen")


def se_before_cancel(doc, method=None):
	"""Eine Fertigung kann nicht storniert werden, solange ihr Los auf einer Palette steht."""
	for r in doc.items:
		charge = r.batch_no or _charge_aus_bundle(r)
		if not (r.t_warehouse and charge):
			continue
		auf = auf_paletten(charge)
		if auf > EPS and lagerbestand(charge) - flt(r.transfer_qty or r.qty) < auf - 1e-4:
			paletten = sorted(
				{
					b.palette
					for b in frappe.get_all(
						"Paletten Bewegung", filters={"charge": charge}, fields=["palette"]
					)
					if _position_charge(b.palette, charge)
				}
			)
			_fehler(
				_("Los {0} steht auf Palette {1}. Erst von der Palette nehmen, dann stornieren.").format(
					charge, ", ".join(paletten)
				)
			)


def _charge_aus_bundle(r):
	if not r.get("serial_and_batch_bundle"):
		return None
	return frappe.db.get_value("Serial and Batch Entry", {"parent": r.serial_and_batch_bundle}, "batch_no")
