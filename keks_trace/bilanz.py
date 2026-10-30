"""Mengenbilanz je Charge (IFS Food 4.18.2).

Quelle sind die gebuchten ERPNext-Belege (Serial and Batch Bundles). Für jede Charge:

- Zugang: Wareneingang bzw. hergestellte Menge
- Abgang: verbraucht in Produktion, zu Rework umgefüllt, ausgeliefert, ausgebucht/entsorgt, Inventur
- Bestand: aktueller Lagerbestand der Charge
- Differenz Lager = Zugang - Abgang - Bestand (muss 0 sein)
- Abgleich Genealogie: Was laut Lager in Produktion verbraucht wurde, muss als Kante in der
  Genealogie stehen. Eine Differenz bedeutet eine Lücke in der Rückverfolgung.
- Ausbeute: bei hergestellten Chargen Einsatzmenge gegen Ausbringung (z. B. Backverlust).
"""

from collections import defaultdict

import frappe
from frappe.utils import flt

KATEGORIEN = {
	"Wareneingang": "zugang",
	"Hergestellt": "zugang",
	"Retoure": "zugang",
	"Verbraucht in Produktion": "abgang",
	"Zu Rework umgefüllt": "abgang",
	"Ausgeliefert": "abgang",
	"Ausgebucht / entsorgt": "abgang",
	"Inventur": "inventur",
	"Umlagerung": "umlagerung",
	"Sonstiges": "sonstig",
}


def mengenbilanz(charge: str, toleranz_prozent: float | None = None) -> dict:
	if toleranz_prozent is None:
		toleranz_prozent = flt(
			frappe.db.get_single_value("Keks Trace Einstellungen", "bilanz_toleranz_prozent") or 0.5
		)
	info = frappe.db.get_value(
		"Batch",
		charge,
		["name", "item", "item_name", "batch_qty", "stock_uom", "kt_chargen_stufe"],
		as_dict=True,
	)
	if not info:
		frappe.throw(frappe._("Charge {0} existiert nicht.").format(charge))

	bewegungen = _bewegungen(charge)
	summen = defaultdict(float)
	for b in bewegungen:
		summen[b["kategorie"]] += b["menge"]

	zugang = sum(v for k, v in summen.items() if KATEGORIEN[k] == "zugang")
	abgang = -sum(v for k, v in summen.items() if KATEGORIEN[k] == "abgang")
	inventur = summen.get("Inventur", 0.0)
	sonstig = summen.get("Sonstiges", 0.0)
	bestand = flt(info.batch_qty)
	differenz_lager = zugang - abgang + inventur + sonstig - bestand

	verbraucht_lager = -(summen.get("Verbraucht in Produktion", 0.0) + summen.get("Zu Rework umgefüllt", 0.0))
	verbraucht_genealogie = flt(
		frappe.db.sql(
			"""select coalesce(sum(menge), 0) from `tabChargen Genealogie`
			where input_batch = %s and storniert = 0""",
			charge,
		)[0][0]
	)
	differenz_genealogie = verbraucht_lager - verbraucht_genealogie

	einsatz = flt(
		frappe.db.sql(
			"""select coalesce(sum(menge), 0) from `tabChargen Genealogie`
			where output_batch = %s and storniert = 0""",
			charge,
		)[0][0]
	)
	hergestellt = summen.get("Hergestellt", 0.0)
	ausbeute = hergestellt / einsatz * 100 if einsatz and hergestellt else None

	grenze = max(zugang, 1) * toleranz_prozent / 100
	abweichungen = []
	if abs(differenz_lager) > max(grenze, 1e-6):
		abweichungen.append(frappe._("Lagerbilanz geht nicht auf ({0})").format(flt(differenz_lager, 3)))
	if abs(differenz_genealogie) > max(grenze, 1e-6):
		abweichungen.append(
			frappe._("Verbrauch laut Lager {0}, laut Genealogie {1}").format(
				flt(verbraucht_lager, 3), flt(verbraucht_genealogie, 3)
			)
		)

	return {
		"charge": charge,
		"artikel": info.item,
		"artikelname": info.item_name,
		"stufe": info.kt_chargen_stufe,
		"einheit": info.stock_uom,
		"bewegungen": bewegungen,
		"summen": {k: flt(v, 3) for k, v in summen.items()},
		"zugang": flt(zugang, 3),
		"abgang": flt(abgang, 3),
		"inventur": flt(inventur, 3),
		"bestand": flt(bestand, 3),
		"differenz_lager": flt(differenz_lager, 3),
		"verbraucht_lager": flt(verbraucht_lager, 3),
		"verbraucht_genealogie": flt(verbraucht_genealogie, 3),
		"differenz_genealogie": flt(differenz_genealogie, 3),
		"einsatz": flt(einsatz, 3),
		"ausbeute_prozent": flt(ausbeute, 1) if ausbeute is not None else None,
		"abweichungen": abweichungen,
		"ok": not abweichungen,
	}


def _bewegungen(charge):
	zeilen = frappe.db.sql(
		"""
		select sbe.qty, sbe.warehouse, sbb.voucher_type, sbb.voucher_no, sbb.posting_datetime,
			se.purpose, dn.is_return as dn_return
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		left join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		left join `tabDelivery Note` dn on sbb.voucher_type = 'Delivery Note' and dn.name = sbb.voucher_no
		where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
		order by sbb.posting_datetime, sbb.creation
		""",
		charge,
		as_dict=True,
	)
	rework_ziele = _rework_ziele(charge)
	ergebnis = []
	for z in zeilen:
		menge = flt(z.qty)
		ergebnis.append(
			{
				"kategorie": _kategorie(z, menge, rework_ziele),
				"beleg_typ": z.voucher_type,
				"beleg": z.voucher_no,
				"zeitpunkt": z.posting_datetime,
				"lager": z.warehouse,
				"menge": menge,
			}
		)
	return ergebnis


def _rework_ziele(charge):
	"""Buchungen, in denen die Charge zu Rework umgefüllt wurde."""
	return {
		r.stock_entry
		for r in frappe.db.sql(
			"""select g.stock_entry from `tabChargen Genealogie` g
			join `tabBatch` b on b.name = g.output_batch
			where g.input_batch = %s and b.kt_chargen_stufe = 'Rework' and g.storniert = 0""",
			charge,
			as_dict=True,
		)
	}


def _kategorie(z, menge, rework_ziele):
	vt, zweck = z.voucher_type, z.purpose
	if vt == "Stock Entry" and zweck in ("Material Transfer", "Material Transfer for Manufacture"):
		return "Umlagerung"
	if vt == "Stock Reconciliation":
		return "Inventur"
	if menge > 0:
		if vt in ("Purchase Receipt", "Purchase Invoice") or zweck == "Material Receipt":
			return "Wareneingang"
		if zweck in ("Manufacture", "Repack"):
			return "Hergestellt"
		if vt == "Delivery Note" and z.dn_return:
			return "Retoure"
		return "Sonstiges"
	if zweck in ("Manufacture", "Repack"):
		return "Zu Rework umgefüllt" if z.voucher_no in rework_ziele else "Verbraucht in Produktion"
	if vt in ("Delivery Note", "Sales Invoice"):
		return "Ausgeliefert"
	if zweck == "Material Issue":
		return "Ausgebucht / entsorgt"
	return "Sonstiges"
