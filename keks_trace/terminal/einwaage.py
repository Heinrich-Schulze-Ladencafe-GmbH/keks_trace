"""Rezepte am Teigmacher: Sollmengen, Lagerort, Gebinde, Toleranz der Einwaage."""

import frappe
from frappe import _
from frappe.utils import flt

from keks_trace import kennzeichnung, pruefung
from keks_trace import palette as paletten
from keks_trace.install import REWORK_ZIELE
from keks_trace.terminal.basis import _fehler, _silo_je_artikel, _station, _vorraete
from keks_trace.utils import artikel_stufe, einstellung


@frappe.whitelist()
def rezepte(station: str) -> list[dict]:
	"""Herstellbare Artikel dieser Station (mit aktiver Standard-Stückliste)."""
	s = _station(station)
	stufen = s.stufen_liste()
	if not stufen:
		return []
	return frappe.db.sql(
		"""
		select i.name as artikel, i.item_name as name, i.kt_chargen_stufe as stufe, b.name as bom
		from `tabItem` i
		join `tabBOM` b on b.item = i.name and b.is_default = 1 and b.is_active = 1 and b.docstatus = 1
		where i.disabled = 0 and i.kt_chargen_stufe in %(stufen)s
			and ifnull(i.kt_linie, '') = %(linie)s
		order by field(i.kt_chargen_stufe, %(reihenfolge)s), i.item_name
		""",
		# Station einer Linie: nur Artikel dieser Linie; Station ohne Linie: nur Artikel ohne Linie
		{"stufen": tuple(stufen), "reihenfolge": ",".join(stufen), "linie": s.linie or ""},
		as_dict=True,
	)


@frappe.whitelist()
def rezept(artikel: str, menge: float | None = None, station: str | None = None) -> dict:
	"""Zutaten laut Standard-Stückliste, auf die Sollmenge umgerechnet."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		_fehler(_("Für {0} gibt es kein aktives Rezept (Stückliste).").format(artikel))
	b = frappe.get_cached_doc("BOM", bom)
	faktor = flt(menge or b.quantity) / flt(b.quantity or 1)
	silos = _silo_je_artikel()
	vorraete = _vorraete()
	gebinde = _gebinde_einheiten([z.item_code for z in b.items])
	zutaten = [
		{
			"artikel": z.item_code,
			"name": z.item_name,
			"menge": flt(z.qty * faktor, 3),
			"einheit": z.stock_uom or z.uom,
			"stufe": artikel_stufe(z.item_code),
			"silo": silos.get(z.item_code),
			"vorrat": silos.get(z.item_code) if z.item_code in vorraete else None,
			"toleranz": _toleranz(z, flt(z.qty * faktor, 3)),
			# Wo die Zutat liegt (wie „Kostenstelle“ bei FOBIS) und in welchen Gebinden sie gezählt werden kann
			"lager": silos.get(z.item_code) or _lagerort(z, b.company),
			"gebinde": gebinde.get(z.item_code, []),
		}
		for z in b.items
	]
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"stufe": artikel_stufe(artikel),
		"bom": bom,
		"sollmenge": flt(menge or b.quantity, 3),
		# Ausbeute nur über Zutaten in der Einheit des Produkts, ohne Packmittel (Herz in Stück:
		# 1 garniertes Herz + Folie + Etikett + Schleife = 1 Herz, nicht 4)
		"ausbeute": flt(b.quantity)
		/ (
			sum(
				flt(z.stock_qty or z.qty)
				for z in b.items
				if (z.stock_uom or z.uom) == b.uom and artikel_stufe(z.item_code) != "Packmittel"
			)
			or 1
		),
		"einheit": b.uom,
		"zutaten": zutaten,
		"rework_moeglich": artikel_stufe(artikel) in REWORK_ZIELE,
		# Einwaage gegen Soll prüfen (Grundteig, Teig, Halbfabrikat), siehe _pruefe_rezept
		"rezept_pruefen": artikel_stufe(artikel) in REZEPT_STUFEN and _rezept_modus() != "Aus",
		"rezept_pflicht": _rezept_modus() == "Grund Pflicht",
		"ausgabe_silo": silos.get(artikel),
		"einheiten": paletten.einheiten(artikel) if artikel_stufe(artikel) == "Fertigware" else [],
		"pruefungen": [pruefung.beschreibung(p) for p in pruefung.fuer_herstellen(artikel, station)],
		"kennzeichen": sorted(kennzeichnung.artikel_kennzeichen(artikel), key=kennzeichnung.ALLE.index),
		"kuebel": _kuebel_fuer(zutaten),
		"umstellung_bio": bool(station and kennzeichnung.umstellung_noetig(station, artikel)),
	}


REZEPT_STUFEN = ("Grundteig", "Teig veredelt", "Halbfabrikat")


def _lagerort(bom_zeile, company: str | None) -> str | None:
	"""Lagerort einer Rezeptzeile: Quelllager der Stückliste, sonst Standardlager des Artikels (ohne Firmenkürzel)."""
	lager = bom_zeile.get("source_warehouse") or frappe.db.get_value(
		"Item Default", {"parent": bom_zeile.item_code, "company": company}, "default_warehouse"
	)
	return (frappe.get_cached_value("Warehouse", lager, "warehouse_name") or lager) if lager else None


def _gebinde_einheiten(artikel: list[str]) -> dict[str, list[dict]]:
	"""Gebinde mit festem Inhalt je Artikel aus der Maßeinheit-Umrechnung am Artikel, z. B. 1 Sack = 25 kg.
	Nur Einheiten größer als die Lagereinheit (Sack, Kollo, Karton); gezählt wird am Terminal in ganzen Gebinden."""
	if not artikel:
		return {}
	lagereinheit = dict(
		frappe.get_all("Item", filters={"name": ["in", artikel]}, fields=["name", "stock_uom"], as_list=True)
	)
	je = {}
	for u in frappe.get_all(
		"UOM Conversion Detail",
		filters={"parenttype": "Item", "parent": ["in", artikel], "conversion_factor": [">", 1]},
		fields=["parent", "uom", "conversion_factor"],
		order_by="conversion_factor asc",
	):
		if u.uom != lagereinheit.get(u.parent):
			je.setdefault(u.parent, []).append({"einheit": u.uom, "faktor": flt(u.conversion_factor, 6)})
	return je


def _rezept_modus() -> str:
	return einstellung("rezept_abweichung") or "Grund Pflicht"


def _toleranz(bom_zeile, soll: float) -> float:
	"""Erlaubte Abweichung in der Lagereinheit: % an der Rezeptzeile, sonst Standard; nie unter dem Minimum."""
	prozent = flt(bom_zeile.get("kt_toleranz_prozent")) or flt(einstellung("rezept_toleranz_prozent") or 5)
	return flt(max(abs(soll) * prozent / 100, flt(einstellung("rezept_toleranz_min") or 0.01)), 4)


def _pruefe_rezept(ziel: str, sollmenge, eingaenge: list[dict], grund: str | None) -> str | None:
	"""Einwaage gegen das Rezept, umgerechnet auf die Sollmenge (z. B. halbe Masse = halbe Sollmenge).

	Nur mit Sollmenge vom Terminal (Teigmacher), nur für REZEPT_STUFEN. Rework zählt nicht (eigene Regel).
	Gibt den Text fürs Protokoll zurück (None = alles in der Toleranz).
	"""
	modus = _rezept_modus()
	if not flt(sollmenge) or modus == "Aus" or artikel_stufe(ziel) not in REZEPT_STUFEN:
		return None
	r = rezept(ziel, flt(sollmenge))
	ist = {}
	for z in eingaenge:
		ist[z["artikel"]] = ist.get(z["artikel"], 0) + flt(z["menge"])
	texte = []
	for z in r["zutaten"]:
		menge = flt(ist.get(z["artikel"]), 3)
		if abs(menge - z["menge"]) <= z["toleranz"] + 1e-9:
			continue
		prozent = f"{(menge / z['menge'] - 1) * 100:+.0f} %" if z["menge"] else ""
		texte.append(
			_("{0}: {1} statt {2} ({3}, erlaubt ± {4})").format(
				z["name"],
				paletten._n(menge, z["einheit"]),
				paletten._n(z["menge"], z["einheit"]),
				prozent,
				paletten._n(z["toleranz"], z["einheit"]),
			)
		)
	if not texte:
		return None
	kopf = _("Sollmenge {0}").format(paletten._n(flt(sollmenge), r["einheit"]))
	grund = (grund or "").strip()
	if not grund:
		if modus == "Grund Pflicht":
			_fehler(
				_("Einwaage außerhalb der Toleranz. Bitte korrigieren oder einen Grund angeben.")
				+ "<br>"
				+ "<br>".join(texte)
			)
		frappe.msgprint("<br>".join(texte), title=_("Einwaage"), indicator="orange", alert=True)
		return _("Ohne Grund (Einstellung: nur Hinweis)") + "\n" + kopf + "\n" + "\n".join(texte)
	return _("Grund: {0}").format(grund) + "\n" + kopf + "\n" + "\n".join(texte)


def _kuebel_fuer(zutaten) -> list[dict]:
	"""Älteste belegte Kübel mit dem Grundteig des Rezepts (Vorschlag am Kneter bzw. bei der Veredelung)."""
	from keks_trace.linienbuchung import kuebel_vorschlag

	return kuebel_vorschlag([z["artikel"] for z in zutaten if z["stufe"] == "Grundteig"])


def _fuer_auftrag(kundenauftrag: str, ziel: str) -> bool:
	"""Ist der Artikel bestellt oder eine Vorstufe davon (garniertes Herz für ein bestelltes Herz)?"""
	bestellt = frappe.get_all(
		"Sales Order Item", {"parent": kundenauftrag, "docstatus": 1}, pluck="item_code"
	)
	if ziel in bestellt:
		return True
	for artikel in bestellt:
		if ziel in {z["artikel"] for z in rezept(artikel, 1)["zutaten"]}:
			return True
	return False
