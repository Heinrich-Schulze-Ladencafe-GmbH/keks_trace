"""Paletten: betroffene Paletten für Rückverfolgung und Rückruf, Daten fürs Etikett."""

import frappe
from frappe.utils import flt, formatdate, getdate, now_datetime

from keks_trace.palette.bestand import info


def paletten_fuer(chargen) -> list[dict]:
	"""Alle Paletten, auf denen eines der Lose stand oder steht."""
	chargen = list(chargen)
	if not chargen:
		return []
	zeilen = frappe.db.sql(
		"""
		select b.charge, b.palette, p.status, p.kunde, p.lieferschein,
			sum(if(b.richtung = 'Zugang', b.anzahl, -b.anzahl)) as anzahl_jetzt, b.einheit
		from `tabPaletten Bewegung` b join `tabPalette` p on p.name = b.palette
		where b.charge in %(c)s
		group by b.charge, b.palette, b.einheit
		order by b.charge, b.palette
		""",
		{"c": tuple(chargen)},
		as_dict=True,
	)
	for z in zeilen:
		z["anzahl_jetzt"] = max(flt(z.anzahl_jetzt, 3), 0)
	return zeilen


def _yymmdd(datum):
	return getdate(datum).strftime("%y%m%d") if datum else None


def etikett(nve: str) -> dict:
	"""Daten für das GS1-Paletten-Etikett."""
	i = info(nve)
	e = frappe.get_cached_doc("Keks Trace Einstellungen")
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	daten = {
		**i,
		"absender": e.get("absender") or company or "",
		"datum": formatdate(now_datetime()),
		"barcode_sscc": "00" + nve,
		"text_sscc": f"(00) {nve}",
		"inhalt_barcode": None,
		"inhalt_text": None,
	}
	# Palette mit Versandkartons: das Etikett zeigt alles zusammen (die Kartons tragen ihr eigenes)
	pos = daten["positionen"] = i["positionen_gesamt"]
	# Bio nur, wenn alles auf der Palette Bio ist (Artikel verspricht es und das Los trägt es)
	from keks_trace import kennzeichnung as kz

	if pos and all(
		kz.BIO in kz.artikel_kennzeichen(p["artikel"])
		and kz.BIO in kz.charge_kennzeichen(p["charge"], p["artikel"])
		for p in pos
	):
		daten["bio"] = True
		daten["oeko_nr"] = e.get("oeko_kontrollnummer")
	# Sortenreine Palette (ein Los, eine Einheit): GTIN, Anzahl, MHD, Charge als zweiter Strichcode
	if len(pos) == 1:
		p = pos[0]
		gtin = frappe.db.get_value(
			"Item Barcode", {"parent": p["artikel"], "uom": p["einheit"]}, "barcode"
		) or frappe.db.get_value("Item Barcode", {"parent": p["artikel"]}, "barcode")
		if gtin and gtin.isdigit() and len(gtin) in (8, 12, 13, 14) and float(p["anzahl"]).is_integer():
			gtin14 = gtin.zfill(14)
			mhd = _yymmdd(p["mhd_datum"])
			anzahl = str(int(p["anzahl"]))
			fnc1 = "Ï"  # FNC1 in JsBarcode
			los = p["los"] if len(p["los"]) <= 20 else None  # GS1 (10) wie auf dem Karton, max. 20 Zeichen
			roh = (
				f"02{gtin14}"
				+ (f"15{mhd}" if mhd else "")
				+ f"37{anzahl}"
				+ (f"{fnc1}10{los}" if los else "")
			)
			daten["inhalt_barcode"] = roh
			daten["inhalt_text"] = (
				f"(02) {gtin14}"
				+ (f" (15) {mhd}" if mhd else "")
				+ f" (37) {anzahl}"
				+ (f" (10) {los}" if los else "")
			)
			daten["gtin"] = gtin14
			# Für den Etikettendrucker in zwei Codes (je kürzer, also breitere Striche): Was und wie viel,
			# dann MHD und Los. Variable Felder stehen jeweils am Ende, ein Trennzeichen ist nicht nötig.
			daten["inhalt_zeilen"] = [(f"02{gtin14}37{anzahl}", f"(02) {gtin14} (37) {anzahl}")]
			if mhd or los:
				daten["inhalt_zeilen"].append(
					(
						(f"15{mhd}" if mhd else "") + (f"10{los}" if los else ""),
						" ".join(
							x for x in ((f"(15) {mhd}" if mhd else ""), (f"(10) {los}" if los else "")) if x
						),
					)
				)
	return daten
