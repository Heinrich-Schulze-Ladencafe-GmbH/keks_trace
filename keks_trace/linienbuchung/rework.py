"""Linie: Rework von der Linie (Flussschema F18/F19), Sorten, Höchstanteil."""

import frappe
from frappe import _
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import buchung
from keks_trace.linienbuchung.basis import EPS, _fehler, _station
from keks_trace.linienbuchung.rezept import bestand, linienrezept, rework_ersatz
from keks_trace.utils import artikel_stufe


def _rework_ziel(artikel, rezept, pa) -> str:
	"""Der Teig im Linienrezept, den dieses Rework ersetzt (Filter: Regel und Allergene)."""
	from keks_trace.rework import _pruefe_allergene

	ziele = [z for z in rework_ersatz().get(artikel, ()) if z in rezept]
	if not ziele:
		_fehler(
			_("{0} passt nicht zu {1}: keine Rework-Regel für einen Teig dieses Artikels.").format(
				frappe.bold(frappe.get_cached_value("Item", artikel, "item_name")), pa.artikelname
			)
		)
	_pruefe_allergene(artikel, ziele[0])
	return ziele[0]


def _pruefe_rework_anteil(pa, artikel, ziel, menge):
	"""Rework-Anteil am Teig, der für diesen Auftrag auf der Linie liegt, höchstens laut Regel."""
	maximum = flt(
		frappe.db.get_value(
			"Rework Regel",
			{"rework_artikel": artikel, "ziel_artikel": ziel, "aktiv": 1},
			"max_anteil_prozent",
		)
	)
	ersatz = rework_ersatz()
	teig = rework = 0.0
	for z in bestand(pa.name):
		if z["artikel"] == ziel:
			teig += z["menge"]
		elif ziel in ersatz.get(z["artikel"], ()):
			rework += z["menge"]
	gesamt = teig + rework + menge
	if gesamt <= EPS or (rework + menge) / gesamt * 100 > maximum + 1e-9:
		erlaubt = (
			max(maximum / 100 * (teig + rework) - rework, 0) / (1 - maximum / 100) if maximum < 100 else 0
		)
		_fehler(
			_(
				"Zu viel Rework: höchstens {0} % in {1}. Auf der Linie liegen {2} kg Teig und {3} kg Rework, "
				"dazu passen noch {4} kg Rework. Erst Teig zuführen."
			).format(
				flt(maximum, 1),
				frappe.get_cached_value("Item", ziel, "item_name"),
				flt(teig, 1),
				flt(rework, 1),
				flt(erlaubt, 1),
			)
		)


def rework_sorten(auftrag: str) -> list[dict]:
	"""Rework-Sorten, die von diesem Auftrag abgenommen werden dürfen: es gibt eine Regel zu einem Teig
	im Linienrezept, und die Ware hat keine Allergene, die das Rework nicht hat. Nach Entnahmepunkt."""
	from keks_trace.utils import allergene

	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	rezept = linienrezept(pa.artikel)
	ware = allergene(frappe.get_cached_value("Item", pa.artikel, "kt_allergengruppe"))
	ergebnis = []
	for artikel, ziele in rework_ersatz().items():
		if not ziele & set(rezept) or frappe.get_cached_value("Item", artikel, "disabled"):
			continue
		if ware - allergene(frappe.get_cached_value("Item", artikel, "kt_allergengruppe")):
			continue
		ergebnis.append(
			{
				"artikel": artikel,
				"name": frappe.get_cached_value("Item", artikel, "item_name"),
				"punkt": frappe.get_cached_value("Item", artikel, "kt_entnahmepunkt") or "",
			}
		)
	reihenfolge = {"Nach dem Ofen": 0, "Nach dem Sprühen": 1, "Am Ende der Linie": 2}
	return sorted(ergebnis, key=lambda x: (reihenfolge.get(x["punkt"], 3), x["name"]))


def laufende_auftraege() -> list[dict]:
	"""Was gerade auf den Linien läuft (für die Backstube: von welchem Auftrag kommt das Rework?).

	Zuerst die Aufträge, an denen eine Station gerade arbeitet (Kneter, Verpackungs-PC); ältere, nie beendete
	Aufträge nur, wenn es keine solchen gibt."""
	liste = frappe.get_all(
		"Produktionsauftrag",
		{"status": "Läuft"},
		["name as auftrag", "linie", "artikel", "artikelname as name", "datum"],
		order_by="linie, gestartet_am desc",
	)
	aktiv = set(
		frappe.get_all(
			"Terminal Station", {"aktiv": 1, "aktueller_auftrag": ["is", "set"]}, pluck="aktueller_auftrag"
		)
	)
	an_station = [a for a in liste if a.auftrag in aktiv]
	return [{**a, "datum": formatdate(a.datum)} for a in (an_station or liste)]


def rework_von_linie(station: str, auftrag: str, rework_artikel: str, kg: float, behaelter: str) -> dict:
	"""Backstube: Rework-Behälter von der Linie gewogen. Der Teig dieses Auftrags auf der Linie wird zu
	Rework (neue Rework-Charge im Behälter, Herkunft = Teigchargen). So zählt Rework nicht als Linienrest."""

	s = _station(station)
	pa = frappe.get_doc("Produktionsauftrag", auftrag)
	if pa.status != "Läuft":
		_fehler(_("Auftrag {0} ist {1}. Rework nur von laufenden Aufträgen.").format(pa.name, pa.status))
	if rework_artikel not in {x["artikel"] for x in rework_sorten(pa.name)}:
		_fehler(
			_("{0} passt nicht zu {1} (Regel oder Allergene).").format(
				frappe.get_cached_value("Item", rework_artikel, "item_name"), pa.artikelname
			)
		)
	kg = flt(kg, 6)
	if kg <= EPS:
		_fehler(_("Bitte das Gewicht von der Waage eingeben."))
	if not behaelter:
		_fehler(_("Bitte den Rework-Behälter scannen oder antippen."))
	behaelter = buchung._ziel_behaelter(behaelter)
	if frappe.db.get_value("Produkttraeger", behaelter, "typ") != "Rework-Behälter":
		_fehler(_("{0} ist kein Rework-Behälter.").format(behaelter))
	linie = frappe.get_cached_doc("Linie", pa.linie)
	ersatz = rework_ersatz()
	teig = [
		z
		for z in bestand(pa.name)
		if artikel_stufe(z["artikel"]) in ("Grundteig", "Teig veredelt") or z["artikel"] in ersatz
	]
	vorhanden = sum(z["menge"] for z in teig)
	if kg > vorhanden + 1e-4:
		_fehler(
			_("Für Auftrag {0} liegen nur {1} kg Teig auf der Linie. Am Kneter gebucht?").format(
				pa.name, flt(vorhanden, 1)
			)
		)
	zeilen, offen = [], kg
	for z in teig:
		if offen <= EPS:
			break
		nimm = min(offen, z["menge"])
		zeilen.append({"artikel": z["artikel"], "charge": z["charge"], "menge": flt(nimm, 6)})
		offen -= nimm
	charge = buchung._neue_charge(rework_artikel, getdate(nowdate()))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"purpose": "Repack",
			"company": linie.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_produktionsauftrag": pa.name,
			"remarks": _("Rework von der Linie, Auftrag {0}").format(pa.name),
			"items": [buchung._se_zeile(z, s_warehouse=linie.lagerort) for z in zeilen]
			+ [
				buchung._se_zeile(
					{"artikel": rework_artikel, "charge": charge, "menge": kg, "behaelter": behaelter},
					t_warehouse=buchung._ziel_lager(s, rework_artikel),
				)
			],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", rework_artikel, "item_name"),
		"punkt": frappe.get_cached_value("Item", rework_artikel, "kt_entnahmepunkt") or "",
		"menge": kg,
		"behaelter": behaelter,
		"auftrag": pa.name,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"buchung": se.name,
	}
