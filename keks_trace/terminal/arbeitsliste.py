"""Aufgaben und Aufträge: was die Station heute tun soll, was zum Verpacken wartet."""

import frappe
from frappe.utils import cint, flt, formatdate

from keks_trace import palette as paletten
from keks_trace.buchung.basis import EPS
from keks_trace.buchung.bestand import _quellen
from keks_trace.terminal.basis import _mit_hinweis, _station
from keks_trace.terminal.bestand import _lager_chargen_alle
from keks_trace.terminal.einwaage import rezept
from keks_trace.utils import artikel_stufe


def _hauptzutat(artikel: str) -> str | None:
	"""Woraus ein Artikel hauptsächlich besteht (Herz verpackt: garniertes Herz; garniert: Rohling)."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		return None
	zeilen = [
		z
		for z in frappe.get_all("BOM Item", {"parent": bom}, ["item_code", "stock_qty"], order_by="idx")
		if artikel_stufe(z.item_code) not in ("Packmittel", "Rohstoff")
	]
	return max(zeilen, key=lambda z: flt(z.stock_qty)).item_code if zeilen else None


def _fertig_fuer(auftrag: str, artikel: str) -> float:
	"""Wie viel von artikel mit diesem Kundenauftrag hergestellt wurde (Lagereinheit)."""
	return flt(
		frappe.db.sql(
			"""select sum(sed.transfer_qty) from `tabStock Entry Detail` sed
			join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and se.kt_kundenauftrag = %s and sed.item_code = %s and sed.is_finished_item = 1""",
			(auftrag, artikel),
		)[0][0]
	)


def _vorrat_je_auftrag(artikel: str) -> tuple[dict, float]:
	"""({Auftrag: reservierter Bestand}, freier Bestand) eines Artikels im Lager."""
	reserviert, frei = {}, 0.0
	for c in _lager_chargen_alle(artikel):
		if c["auftrag"]:
			reserviert[c["auftrag"]] = reserviert.get(c["auftrag"], 0) + c["menge"]
		else:
			frei += c["menge"]
	return reserviert, frei


@frappe.whitelist()
def aufgaben(station: str) -> list[dict]:
	"""Offene Kundenaufträge als Arbeitsliste der Station (Herzenboden: Garnieren und Verpacken).

	Ein Auftrag läuft am Herzenboden durch: was beim Garnieren für ihn gemacht wird, ist für ihn reserviert und
	wird beim Verpacken zuerst genommen. Je Auftragsposition: was diese Station dafür herstellt, bestellt, erledigt
	(Verpacken: verpackt; Garnieren: schon verpackt plus für den Auftrag garniert und noch im Lager), ToDo und
	Vorrat der Vorstufe: erst die für den Auftrag reservierte, dann freie Ware nach Liefertermin verteilt
	(Sonderanfertigungen nur reserviert).
	"""
	s = _station(station)
	stufen = s.stufen_liste()
	ergebnis = []
	frei_rest, reserviert_je = {}, {}
	for z in frappe.db.sql(
		"""
		select so.name as auftrag, so.customer_name as kunde, soi.item_code as artikel, soi.stock_qty as menge,
			coalesce(soi.delivery_date, so.delivery_date) as termin
		from `tabSales Order Item` soi join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed', 'On Hold')
			and i.kt_chargen_stufe = 'Fertigware' and soi.delivered_qty < soi.qty
			and ifnull(i.kt_linie, '') = %(linie)s
		order by termin, so.name, soi.idx
		""",
		{"linie": s.linie or ""},
		as_dict=True,
	):
		ziel, faktor = z.artikel, 1.0
		if "Fertigware" not in stufen:
			r = rezept(z.artikel, 1)
			passend = [x for x in r["zutaten"] if x["stufe"] in stufen]
			if not passend:
				continue
			ziel, faktor = passend[0]["artikel"], flt(passend[0]["menge"]) or 1
		bestellt = flt(z.menge) * faktor
		if ziel == z.artikel:
			erledigt = _fertig_fuer(z.auftrag, ziel)
		else:  # Vorstufe: was schon verpackt ist, plus was für den Auftrag gemacht im Lager liegt
			if ziel not in reserviert_je:
				reserviert_je[ziel] = _vorrat_je_auftrag(ziel)[0]
			erledigt = _fertig_fuer(z.auftrag, z.artikel) * faktor + reserviert_je[ziel].get(z.auftrag, 0)
		erledigt = flt(min(erledigt, bestellt), 3)
		todo = max(flt(bestellt - erledigt, 3), 0)
		if todo <= EPS:
			continue
		vor = _hauptzutat(ziel)
		eigen = zugeteilt = 0.0
		if vor:
			if vor not in frei_rest:
				reserviert_je[vor], frei_rest[vor] = _vorrat_je_auftrag(vor)
			eigen = flt(reserviert_je[vor].get(z.auftrag, 0), 3)
			if not cint(frappe.get_cached_value("Item", vor, "kt_nach_auftrag")):
				zugeteilt = flt(min(frei_rest[vor], max(todo - eigen, 0)), 3)
				frei_rest[vor] -= zugeteilt
		ergebnis.append(
			{
				"auftrag": z.auftrag,
				"kunde": z.kunde,
				"artikel": ziel,
				"name": frappe.get_cached_value("Item", ziel, "item_name"),
				"einheit": frappe.get_cached_value("Item", ziel, "stock_uom"),
				"bestellt": bestellt,
				"erledigt": erledigt,
				"todo": todo,
				"vorstufe": frappe.get_cached_value("Item", vor, "item_name") if vor else None,
				"verfuegbar": eigen + zugeteilt if vor else None,
				"vorrat_eigen": eigen,
				"vorrat_frei": zugeteilt,
				"termin": formatdate(z.termin) if z.termin else None,
			}
		)
	_mit_hinweis(ergebnis)
	return ergebnis


@frappe.whitelist()
def zum_verpacken(station: str) -> list[dict]:
	"""Lose Ware im Lager, die verpackt werden kann (nach Bedarf, ohne Auftrag): je Kiste bzw. Charge,
	älteste zuerst, mit den Fertigartikeln, in die sie verpackt werden kann."""
	s = _station(station)
	# Linien mit eigener Verpackung (Herzenboden: Herzen Verpackung) packen ihre Ware selbst
	eigene = {
		x.linie
		for x in frappe.get_all(
			"Terminal Station",
			{"aktiv": 1, "f_herstellen": 1, "linie": ["is", "set"], "name": ["!=", s.name]},
			["name", "linie", "stufen"],
		)
		if "Fertigware" in (x.stufen or "")
	}
	ziele = {}
	for b in frappe.db.sql(
		"""select bi.item_code as lose, bom.item as fertig, bom.quantity as menge, bi.stock_qty as je
		from `tabBOM Item` bi join `tabBOM` bom on bom.name = bi.parent
		join `tabItem` i on i.name = bom.item
		where bom.is_default = 1 and bom.is_active = 1 and bom.docstatus = 1 and i.kt_chargen_stufe = 'Fertigware'
			and i.disabled = 0""",
		as_dict=True,
	):
		if (
			artikel_stufe(b.lose) == "Ware lose"
			and frappe.get_cached_value("Item", b.fertig, "kt_linie") not in eigene
		):
			ziele.setdefault(b.lose, []).append(
				{"artikel": b.fertig, "name": frappe.get_cached_value("Item", b.fertig, "item_name")}
			)
	ergebnis = []
	for lose, fertig in ziele.items():
		for q in _quellen(lose):
			ergebnis.append(
				{
					**q,
					"lose": lose,
					"name": frappe.get_cached_value("Item", lose, "item_name"),
					"einheit": frappe.get_cached_value("Item", lose, "stock_uom"),
					"menge_text": paletten.zerlegen(lose, q["menge"]),
					"backtag": formatdate(frappe.db.get_value("Batch", q["charge"], "kt_backtag") or "")
					or "",
					"ziele": fertig,
				}
			)
	return ergebnis


@frappe.whitelist()
def verpacken_ziele(station: str, lose: str) -> dict:
	"""Was aus dieser losen Ware werden kann: erst offene Kundenaufträge, die sie brauchen, dann alle Artikel
	(jedes Gebinde, jeder Kundenartikel mit dieser losen Ware im Rezept)."""
	ziele = {}
	for b in frappe.db.sql(
		"""select distinct bom.item as artikel from `tabBOM Item` bi join `tabBOM` bom on bom.name = bi.parent
		join `tabItem` i on i.name = bom.item
		where bi.item_code = %s and bom.is_default = 1 and bom.is_active = 1 and bom.docstatus = 1
			and i.kt_chargen_stufe = 'Fertigware' and i.disabled = 0""",
		lose,
		as_dict=True,
	):
		ziele[b.artikel] = {
			"artikel": b.artikel,
			"name": frappe.get_cached_value("Item", b.artikel, "item_name"),
		}
	auftraege_ = [
		{
			"auftrag": z["auftrag"],
			"kunde": z["kundenname"],
			"artikel": z["artikel"],
			"name": z["name"],
			"bestellt": z["menge"],
			"erledigt": z["verpackt"],
			"todo": z["offen_verpacken"],
			"einheit": z["einheit"],
			"offen_text": z["offen_text"],
			"termin": z["termin"],
		}
		for z in auftraege(station)
		if z["artikel"] in ziele and z["offen_verpacken"] > EPS
	]
	return {"auftraege": auftraege_, "artikel": sorted(ziele.values(), key=lambda x: x["name"])}


@frappe.whitelist()
def auftraege(station: str, kunde: str | None = None) -> list[dict]:
	"""Offene Kundenaufträge (Fertigware und lose Ware/Kiloware): bestellt, verpackt, geliefert, offen."""
	s = _station(station)
	bedingung = "and so.customer = %(kunde)s" if kunde else ""
	if s.f_herstellen:
		# Verpacken: nur Aufträge über Artikel dieser Linie (Versand sieht alle)
		bedingung += " and ifnull(i.kt_linie, '') = %(linie)s"
	zeilen = frappe.db.sql(
		f"""
		select so.name as auftrag, so.customer as kunde, so.customer_name as kundenname,
			soi.name as position, soi.item_code as artikel, soi.item_name as name,
			soi.qty as menge, soi.uom as einheit, soi.conversion_factor as faktor,
			soi.stock_qty, soi.delivered_qty * soi.conversion_factor as geliefert,
			coalesce(soi.delivery_date, so.delivery_date) as termin
		from `tabSales Order Item` soi
		join `tabSales Order` so on so.name = soi.parent
		join `tabItem` i on i.name = soi.item_code
		where so.docstatus = 1 and so.status not in ('Completed', 'Closed', 'On Hold')
			and i.kt_chargen_stufe in ('Fertigware', 'Ware lose') and soi.delivered_qty < soi.qty {bedingung}
		order by termin, so.name, soi.idx
		""",
		{"kunde": kunde, "linie": s.linie or ""},
		as_dict=True,
	)
	verpackt = {}
	if zeilen:
		for v in frappe.db.sql(
			"""
			select se.kt_kundenauftrag as auftrag, sed.item_code as artikel, sum(sed.transfer_qty) as menge
			from `tabStock Entry Detail` sed join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and se.kt_kundenauftrag in %(a)s and sed.is_finished_item = 1
			group by se.kt_kundenauftrag, sed.item_code
			""",
			{"a": tuple({z.auftrag for z in zeilen})},
			as_dict=True,
		):
			verpackt[(v.auftrag, v.artikel)] = flt(v.menge)
	for z in zeilen:
		f = flt(z.faktor) or 1
		verpackt_kg = flt(verpackt.get((z.auftrag, z.artikel), 0))
		z["verpackt"] = flt(verpackt_kg / f, 3)
		geliefert_kg = flt(z.geliefert)
		z["geliefert"] = flt(geliefert_kg / f, 3)
		z["offen_verpacken"] = max(flt(z.menge - z.verpackt, 3), 0)
		z["termin"] = formatdate(z.termin) if z.termin else None
		# Klartext in gemischten Einheiten, z. B. „3 Paletten + 5 Karton“
		z["menge_text"] = paletten.zerlegen(z.artikel, z.stock_qty)
		z["verpackt_text"] = paletten.zerlegen(z.artikel, verpackt_kg)
		z["offen_text"] = paletten.zerlegen(z.artikel, max(flt(z.stock_qty) - verpackt_kg, 0))
		z["offen_liefern_text"] = paletten.zerlegen(z.artikel, max(flt(z.stock_qty) - geliefert_kg, 0))
		z["offen_kg"] = max(flt(z.stock_qty) - verpackt_kg, 0)
		z["einheiten"] = paletten.einheiten(z.artikel, alle=True)
	_mit_hinweis(zeilen)
	return zeilen
