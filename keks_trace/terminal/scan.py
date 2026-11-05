"""Scan auflösen: Behälter, Silo, Palette, Gebinde, Los oder Charge; Info-Scan und Akte."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, nowdate

from keks_trace import akte as akte_modul
from keks_trace import gs1
from keks_trace import palette as paletten
from keks_trace.terminal.basis import _fehler
from keks_trace.terminal.bestand import charge_lager
from keks_trace.utils import artikel_stufe


def _artikel_zur_gtin(gtin: str) -> dict | None:
	"""Artikel und Einheit zu einer GTIN/EAN aus der Barcode-Tabelle am Artikel (ERPNext-Standard)."""
	for g in gs1.gtin_varianten(gtin):
		z = frappe.db.get_value("Item Barcode", {"barcode": g}, ["parent", "uom"], as_dict=True)
		if z:
			return {"artikel": z.parent, "einheit": z.uom}
	return None


def _charge_name(artikel: str, lieferantencharge: str) -> str:
	"""Name unserer Charge zu einer Lieferanten-Charge: die Lieferanten-Charge selbst, bei gleicher Nummer
	eines anderen Artikels <Artikel>-<Lieferanten-Charge>. Eine Nummer je Sache, keine Zweitnummer."""
	if frappe.db.exists("Batch", lieferantencharge) and (
		frappe.db.get_value("Batch", lieferantencharge, "item") != artikel
	):
		return f"{artikel}-{lieferantencharge}"
	return lieferantencharge


def aufloesen(code: str) -> dict:
	"""Was wurde gescannt? Behälter, Silo/Tank oder Charge."""
	code = (code or "").strip()
	if not code:
		_fehler(_("Leerer Scan."))

	nve = paletten.finde(code)
	if nve:
		return {"typ": "palette", "code": nve, "palette": nve}

	if frappe.db.exists("Produkttraeger", code):
		t = frappe.db.get_value(
			"Produkttraeger",
			code,
			["name", "typ", "status", "charge", "artikel", "menge", "gereinigt_am"],
			as_dict=True,
		)
		erg = {
			"typ": "behaelter",
			"code": code,
			"behaelter": code,
			"behaelter_typ": t.typ,
			"status": t.status,
			"gereinigt_am": frappe.utils.format_datetime(t.gereinigt_am, "dd.MM.yyyy HH:mm")
			if t.gereinigt_am
			else None,
		}
		if t.charge:
			lager = charge_lager(t.charge)
			erg.update(
				{
					"charge": t.charge,
					"artikel": t.artikel,
					"inhalt": flt(t.menge, 3),
					"lager": max(lager, key=lager.get) if lager else None,
				}
			)
		return erg

	if frappe.db.exists("Silo", code):
		s = frappe.get_cached_doc("Silo", code)
		return {"typ": "silo", "code": code, "silo": code, "artikel": s.artikel, "lager": s.warehouse}

	if frappe.db.exists("Batch", code):
		artikel = frappe.db.get_value("Batch", code, "item")
		lager = charge_lager(code)
		return {
			"typ": "charge",
			"code": code,
			"charge": code,
			"artikel": artikel,
			"lager": max(lager, key=lager.get) if lager else None,
			"inhalt": flt(sum(lager.values()), 3),
		}

	# Etikett des Lieferanten (GS1-128 mit GTIN und Charge) oder nur seine EAN
	g = gs1.lesen(code)
	if g and g.get("sscc") and not g.get("gtin"):
		nve = paletten.finde(g["sscc"])
		if nve:
			return aufloesen(nve)
	gtin = g.get("gtin") if g else gs1.ean(code)
	treffer = _artikel_zur_gtin(gtin) if gtin else None
	if treffer:
		name = frappe.get_cached_value("Item", treffer["artikel"], "item_name")
		if not (g and g.get("charge")):
			_fehler(
				_(
					"Das ist {0} ({1}), aber ohne Charge im Strichcode. Bitte das Gebinde-Etikett scannen oder die Charge eingeben."
				).format(treffer["artikel"], name)
			)
		if artikel_stufe(treffer["artikel"]) in ("Rohstoff", "Packmittel"):
			charge = _charge_name(treffer["artikel"], g["charge"])
			if not frappe.db.exists("Batch", charge):
				_fehler(
					_("{0} ({1}) Charge {2} ist nicht im Wareneingang gebucht.").format(
						treffer["artikel"], name, frappe.bold(g["charge"])
					)
				)
			return aufloesen(charge)
		return aufloesen(_charge_zum_eigenen_los(treffer["artikel"], name, g))

	# Ohne Scanner: aufgedruckte Los-Nummer oder Buchungsnummer (MAT-STE-...) eingetippt
	charge = _charge_aus_los_oder_buchung(code)
	if charge:
		return aufloesen(charge)

	_fehler(
		_("Code {0} ist unbekannt (kein Behälter, Silo, Palette, Charge, Los oder Buchungsnummer).").format(
			frappe.bold(code)
		)
	)


def _charge_zum_eigenen_los(artikel: str, name: str, g: dict) -> str:
	"""Eigenes GS1-Etikett (Karton): Los (10) und ggf. MHD (15) -> unsere Charge dieses Artikels mit Bestand."""
	kandidaten = frappe.get_all(
		"Batch", {"item": artikel, "kt_los": g["charge"]}, ["name", "expiry_date"], order_by="creation desc"
	)
	if g.get("mhd"):
		passend = [b for b in kandidaten if b.expiry_date and getdate(b.expiry_date) == g["mhd"]]
		kandidaten = passend or kandidaten
	mit_bestand = [b for b in kandidaten if charge_lager(b.name)]
	kandidaten = mit_bestand or kandidaten
	if not kandidaten:
		_fehler(_("{0} ({1}) Los {2} gibt es nicht.").format(artikel, name, frappe.bold(g["charge"])))
	if len(kandidaten) > 1:
		_fehler(
			_("{0} Los {1} gibt es mehrfach: {2}. Bitte die Charge wählen.").format(
				name, g["charge"], ", ".join(b.name for b in kandidaten[:6])
			)
		)
	return kandidaten[0].name


def _charge_aus_los_oder_buchung(code: str) -> str | None:
	"""Los-Nummer (Aufdruck) bzw. Buchungsnummer in die Charge übersetzen; bei mehreren: Rückfrage."""
	if frappe.db.exists("Stock Entry", code):
		chargen = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": code, "is_finished_item": 1, "batch_no": ["is", "set"]},
			pluck="batch_no",
		)
		if not chargen:
			_fehler(_("In Buchung {0} ist keine neue Charge entstanden.").format(code))
		chargen = list(dict.fromkeys(chargen))
		if len(chargen) > 1:
			_fehler(_("In Buchung {0} sind mehrere Chargen entstanden: {1}").format(code, ", ".join(chargen)))
		return chargen[0]
	chargen = [
		b.name
		for b in frappe.get_all("Batch", filters={"kt_los": code}, fields=["name"], order_by="creation desc")
		if charge_lager(b.name)
	]
	if len(chargen) > 1:
		texte = [
			f"{c} ({frappe.get_cached_value('Item', frappe.db.get_value('Batch', c, 'item'), 'item_name')})"
			for c in chargen[:6]
		]
		_fehler(
			_("Los {0} gibt es bei mehreren Artikeln: {1}. Bitte die Charge wählen.").format(
				code, ", ".join(texte)
			)
		)
	return chargen[0] if chargen else None


@frappe.whitelist()
def info(code: str) -> dict:
	"""Info-Scan: alles Wichtige zu einem Code."""
	from keks_trace import silo as silo_modul

	r = aufloesen(code)
	if r["typ"] == "palette":
		r.update(paletten.info(r["palette"]))
		return r
	if r["typ"] == "silo":
		i = silo_modul.info(r["silo"])
		r.update({"bestand": i["bestand"], "moeglich_enthalten": i["moeglich_enthalten"]})
	if r.get("charge"):
		b = frappe.db.get_value(
			"Batch",
			r["charge"],
			[
				"item_name",
				"kt_chargen_stufe",
				"kt_status",
				"kt_sperrgrund",
				"manufacturing_date",
				"expiry_date",
				"kt_backtag",
			],
			as_dict=True,
		)
		r.update(
			{
				"artikelname": b.item_name,
				"stufe": b.kt_chargen_stufe,
				"sperrstatus": b.kt_status,
				"sperrgrund": b.kt_sperrgrund,
				"hergestellt": formatdate(b.manufacturing_date) if b.manufacturing_date else None,
				"backtag": formatdate(b.kt_backtag) if b.kt_backtag else None,
				"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
				"abgelaufen": bool(b.expiry_date and getdate(b.expiry_date) < getdate(nowdate())),
			}
		)
	if r.get("artikel") and not r.get("artikelname"):
		r["artikelname"] = frappe.get_cached_value("Item", r["artikel"], "item_name")
	if r["typ"] == "charge":
		r["fundstellen"] = akte_modul.fundstellen(r["charge"])  # „Wo ist dieses Los?“
	return r


@frappe.whitelist()
def akte(code: str) -> dict:
	"""Lebenslauf einer Palette oder eines Behälters (akte.py)."""
	return akte_modul.akte(code)


@frappe.whitelist()
def herkunft(code: str) -> dict:
	"""Woraus besteht das? Für eine Charge bzw. ein Los (auch Kartonetikett) oder einen Behälter mit Inhalt."""
	r = aufloesen(code)
	charge = r.get("charge")
	if not charge:
		_fehler(
			_("Zu {0} gibt es keine Charge. Bei einer Palette bitte das Los wählen.").format(
				frappe.bold(code)
			)
		)
	return akte_modul.herkunft(charge)
