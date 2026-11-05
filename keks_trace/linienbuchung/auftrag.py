"""Linie: Produktionsaufträge an der Station wählen, Hinweise, Auftragsinfo, nächste Kübel."""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, formatdate, now_datetime, nowdate

from keks_trace import palette as paletten
from keks_trace.linienbuchung.basis import _fehler, _hat, _linie, _menge_text, _station, hinweise
from keks_trace.linienbuchung.lose import im_linienlager, lose_artikel, lose_einheit
from keks_trace.linienbuchung.rezept import bestand, linienrezept
from keks_trace.utils import artikel_stufe


def auftraege(station: str) -> list[dict]:
	"""Freigegebene und laufende Aufträge der Linie, in Planungsreihenfolge (die Freigabe ist das Tor)."""
	s = _station(station)
	_linie(s)
	liste = frappe.get_all(
		"Produktionsauftrag",
		filters={"linie": s.linie, "status": ["in", ["Freigegeben", "Läuft"]]},
		fields=[
			"name", "datum", "reihenfolge", "status", "artikel", "artikelname", "menge", "einheit", "menge_kg",
			"gebucht_kg", "kunde", "kundenauftrag", "verpackungsanlage", "engpass", "dauer_stunden", "bemerkung",
		],
		order_by="datum, reihenfolge, creation",
	)  # fmt: skip
	aktuell = frappe.db.get_value("Terminal Station", s.name, "aktueller_auftrag")
	for a in liste:
		a["aktuell"] = a["name"] == aktuell
		a["menge_text"] = _menge_text(a["artikel"], a["menge_kg"])
		a["gebucht_text"] = _menge_text(a["artikel"], a["gebucht_kg"])
		a["datum_text"] = formatdate(a["datum"])
		a["kundenname"] = frappe.db.get_value("Customer", a["kunde"], "customer_name") if a["kunde"] else None
		a["hinweis"] = " · ".join(h["text"] for h in hinweise(frappe._dict(a)))
	return liste


def waehlen(station: str, auftrag: str) -> dict:
	s = _station(station)
	_linie(s)
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	if pa.linie != s.linie:
		_fehler(_("Auftrag {0} ist für {1}, nicht für {2}.").format(pa.name, pa.linie, s.linie))
	if pa.status not in ("Freigegeben", "Läuft"):
		_fehler(_("Auftrag {0} ist {1}. Nur freigegebene Aufträge können laufen.").format(pa.name, pa.status))
	if pa.status == "Freigegeben":
		pa.db_set({"status": "Läuft", "gestartet_am": now_datetime()})
	frappe.db.set_value("Terminal Station", s.name, "aktueller_auftrag", pa.name)
	frappe.clear_document_cache("Terminal Station", s.name)
	return info(pa.name)


def info(auftrag: str) -> dict:
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	rezept = linienrezept(pa.artikel)
	auf_linie = bestand(pa.name)
	je_artikel = defaultdict(float)
	for z in auf_linie:
		je_artikel[z["artikel"]] += z["menge"]
	rest_kg = max(flt(pa.menge_kg) - flt(pa.gebucht_kg), 0)
	zutaten = []
	for artikel, je in rezept.items():
		zutaten.append(
			{
				"artikel": artikel,
				"name": frappe.get_cached_value("Item", artikel, "item_name"),
				"stufe": artikel_stufe(artikel),
				"einheit": frappe.get_cached_value("Item", artikel, "stock_uom"),
				"auf_linie": flt(je_artikel.get(artikel), 3),
				"bedarf_rest": flt(je * rest_kg, 3),
				"reicht_fuer": flt(je_artikel.get(artikel, 0) / je, 1) if je else None,
			}
		)
	beutel = paletten.faktor(pa.artikel, "Beutel") if _hat(pa.artikel, "Beutel") else None
	karton = paletten.faktor(pa.artikel, "Karton") if _hat(pa.artikel, "Karton") else None
	lose = lose_artikel(pa.artikel)
	return {
		"auftrag": pa.name,
		"status": pa.status,
		"hinweise": hinweise(pa),
		"artikel": pa.artikel,
		"name": pa.artikelname,
		"datum": formatdate(pa.datum),
		"kunde": frappe.db.get_value("Customer", pa.kunde, "customer_name") if pa.kunde else None,
		"kundenauftrag": pa.kundenauftrag,
		"menge_text": _menge_text(pa.artikel, pa.menge_kg),
		"gebucht_text": _menge_text(pa.artikel, pa.gebucht_kg),
		"offen_text": _menge_text(pa.artikel, rest_kg),
		"gebucht_kg": flt(pa.gebucht_kg, 3),
		"lagereinheit": frappe.get_cached_value("Item", pa.artikel, "stock_uom"),
		"menge_kg": flt(pa.menge_kg, 3),
		"verpackungsanlage": pa.verpackungsanlage,
		"engpass": pa.engpass,
		"beutel_je_karton": round(karton / beutel) if beutel and karton else None,
		"einheiten": paletten.einheiten(pa.artikel),
		"los": pa.los,
		"spezifikation": frappe.get_cached_value("Item", pa.artikel, "kt_spezifikation"),
		"karton_je_palette": round(paletten.faktor(pa.artikel, "Palette") / karton)
		if karton and _hat(pa.artikel, "Palette")
		else None,
		"lose_artikel": lose,
		"lose_name": frappe.get_cached_value("Item", lose, "item_name") if lose else None,
		"lose_einheit": lose_einheit(lose) if lose else None,
		"lose_je_einheit": paletten.faktor(lose, lose_einheit(lose)) if lose else None,
		"linienlager": frappe.get_cached_value("Linie", pa.linie, "linienlager"),
		"im_linienlager": im_linienlager(pa.linie),
		"zutaten": zutaten,
		"kuebel": kuebel_vorschlag(
			[z["artikel"] for z in zutaten if z["stufe"] in ("Teig veredelt", "Grundteig")]
		),
	}


def kuebel_vorschlag(artikel: list[str], anzahl: int = 5) -> list[dict]:
	"""Belegte Kübel mit diesen Artikeln, ältester Teig zuerst (kein fester Lagerplatz nötig)."""
	if not artikel:
		return []
	zeilen = frappe.db.sql(
		"""
		select t.code, t.artikel, t.menge, t.charge, b.manufacturing_date as datum, b.expiry_date as verfall
		from `tabProdukttraeger` t join `tabBatch` b on b.name = t.charge
		where t.status = 'Belegt' and t.artikel in %(a)s and ifnull(b.kt_status, '') != 'Gesperrt'
			and (b.expiry_date is null or b.expiry_date >= %(heute)s)
		order by coalesce(b.kt_ursprungsdatum, b.manufacturing_date), b.creation, t.code
		limit %(n)s
		""",
		{"a": tuple(artikel), "heute": nowdate(), "n": anzahl},
		as_dict=True,
	)
	return [
		{
			"code": z.code,
			"name": frappe.get_cached_value("Item", z.artikel, "item_name"),
			"menge": flt(z.menge, 1),
			"datum": formatdate(z.datum) if z.datum else None,
			"charge": z.charge,
		}
		for z in zeilen
	]
