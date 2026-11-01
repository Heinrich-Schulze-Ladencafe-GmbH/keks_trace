"""Artikelvarianten mit eigenem Rezept, z. B. Lebkuchenherzen: Vorlage je Größe, Variante je Spruch.

Das Rezept pflegt man einmal an der Vorlage („Lebkuchenherz Gr. 9“: garniertes Herz Gr. 9, Folie, Etikett,
Schleife). Jede Variante („Gr. 9 · Ich liebe Dich“) bekommt daraus ihr eigenes Rezept; Zutaten, die selbst
Vorlagen sind (garniertes Herz Gr. 9), werden durch die Variante mit demselben Merkmal ersetzt. Ändert sich
das Rezept der Vorlage, werden alle Varianten nachgezogen (Hook BOM on_submit).

Gezählt, gebucht und rückverfolgt wird je Variante, Bestand hat nur die Variante.
"""

import re

import frappe
from frappe import _
from frappe.utils import flt

# Felder, die eine Variante von der Vorlage übernimmt (zusätzlich zu den ERPNext-Standardfeldern)
KT_FELDER = (
	"kt_chargen_stufe",
	"kt_allergengruppe",
	"kt_linie",
	"kt_mhd_monate",
	"kt_mhd_bezug",
	"kt_nach_auftrag",
	"kt_mhd_nicht_begrenzend",
	"has_batch_no",
	"has_expiry_date",
	"shelf_life_in_days",
	"weight_per_unit",
	"weight_uom",
	"stock_uom",
	"is_stock_item",
	"include_item_in_manufacturing",
	"valuation_rate",
)


def kuerzel(text: str) -> str:
	"""„Ich liebe Dich“ -> „ICH-LIEBE-DICH“ (für die Artikelnummer der Variante)."""
	text = text.upper().replace("Ä", "AE").replace("Ö", "OE").replace("Ü", "UE").replace("ß", "SS")
	return re.sub(r"[^A-Z0-9]+", "-", text).strip("-")[:30]


def merkmal(attribut: str, werte: list[str]):
	"""Merkmal (Item Attribute) mit diesen Werten anlegen bzw. ergänzen."""
	if frappe.db.exists("Item Attribute", attribut):
		doc = frappe.get_doc("Item Attribute", attribut)
	else:
		doc = frappe.get_doc({"doctype": "Item Attribute", "attribute_name": attribut})
	vorhanden = {w.attribute_value for w in doc.item_attribute_values}
	for wert in werte:
		if wert not in vorhanden:
			doc.append("item_attribute_values", {"attribute_value": wert, "abbr": kuerzel(wert)})
	if doc.is_new():
		doc.insert()
	else:
		doc.save()


def _merkmale(item) -> dict[str, str]:
	return {a.attribute: a.attribute_value for a in item.get("attributes") or [] if a.attribute_value}


def variante(vorlage: str, werte: dict[str, str]) -> str:
	"""Die Variante der Vorlage mit diesen Merkmalen (anlegen, falls es sie noch nicht gibt), mit Rezept."""
	from erpnext.controllers.item_variant import create_variant, get_variant

	name = get_variant(vorlage, werte)
	if name:
		return name
	v = frappe.get_doc("Item", vorlage)
	doc = create_variant(vorlage, werte)
	for feld in KT_FELDER:
		doc.set(feld, v.get(feld))
	doc.item_name = f"{v.item_name} · {' · '.join(werte.values())}"[:140]
	doc.set("uoms", [{"uom": u.uom, "conversion_factor": u.conversion_factor} for u in v.uoms])
	doc.set("kt_linienleistung", [])
	doc.insert()
	if v.get("kt_linienleistung"):  # erst nach dem Anlegen: die Umrechnung braucht den gespeicherten Artikel
		for x in v.kt_linienleistung:
			doc.append(
				"kt_linienleistung", {"abschnitt": x.abschnitt, "leistung": x.leistung, "einheit": x.einheit}
			)
		doc.save()
	rezept_uebertragen(doc.name)
	return doc.name


def _standard_rezept(artikel):
	return frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})


def rezept_uebertragen(variante_name: str) -> str | None:
	"""Rezept der Vorlage auf die Variante übertragen; Zutaten-Vorlagen werden zur passenden Variante."""
	item = frappe.get_doc("Item", variante_name)
	if not item.variant_of:
		return None
	quelle = _standard_rezept(item.variant_of)
	if not quelle:
		return None
	q = frappe.get_doc("BOM", quelle)
	werte = _merkmale(item)
	zeilen = []
	for z in q.items:
		code = z.item_code
		if frappe.get_cached_value("Item", code, "has_variants"):
			# gleiche Merkmale, soweit die Zutat sie hat (garniertes Herz Gr. 9 -> Spruch der Variante)
			eigene = [a.attribute for a in frappe.get_doc("Item", code).attributes]
			code = variante(code, {k: werte[k] for k in eigene if k in werte})
		zeilen.append((code, flt(z.qty), z.uom))
	alt = _standard_rezept(item.name)
	if alt:
		bisher = {
			(x.item_code, flt(x.qty))
			for x in frappe.get_all("BOM Item", {"parent": alt}, ["item_code", "qty"])
		}
		if bisher == {(c, m) for c, m, _u in zeilen} and flt(
			frappe.db.get_value("BOM", alt, "quantity")
		) == flt(q.quantity):
			return alt
	bom = frappe.get_doc(
		{
			"doctype": "BOM",
			"item": item.name,
			"quantity": q.quantity,
			"company": q.company,
			"is_active": 1,
			"is_default": 1,
			"rm_cost_as_per": q.rm_cost_as_per or "Valuation Rate",
			"items": [{"item_code": c, "qty": m, "uom": u} for c, m, u in zeilen],
		}
	)
	bom.insert()
	bom.submit()
	return bom.name


def bom_on_submit(doc, method=None):
	"""Neues Rezept an einer Vorlage: alle Varianten bekommen es auch."""
	if not frappe.get_cached_value("Item", doc.item, "has_variants") or not doc.is_default:
		return
	for name in frappe.get_all("Item", {"variant_of": doc.item, "disabled": 0}, pluck="name"):
		rezept_uebertragen(name)
	frappe.msgprint(_("Rezept auf die Varianten von {0} übertragen.").format(doc.item), alert=True)
