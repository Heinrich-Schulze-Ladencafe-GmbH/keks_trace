"""Schnittstelle für die Terminals (Backstube, Verpackung, Lager, Versand).

Jedes Terminal ist als seine Station angemeldet. Gescannt wird mit dem Handscanner als
Tastatureingabe: ein Code ist ein Behälter, ein Silo/Tank oder eine Charge.

Die Prüfungen am Terminal (pruefe_zeile) geben sofort grün oder rot. Beim Buchen laufen
zusätzlich alle Regeln aus keks_trace.pruefungen (Rework-Anteil, FIFO, Vollständigkeit, ...).
Die Daten vom Terminal werden beim Buchen serverseitig neu aufgelöst, nie blind übernommen.
"""

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import los as los_modul
from keks_trace import palette as paletten
from keks_trace.install import REWORK_ZIELE
from keks_trace.utils import allergene, artikel_stufe

STATION_ZIELE = {
	"Backstube": ["Grundteig", "Teig veredelt", "Backware", "Ware lose", "Halbfabrikat"],
	"Verpackung": ["Fertigware"],
}

EPS = 1e-6


class TerminalFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, TerminalFehler, title=_("Nicht möglich"))


def _silo_je_artikel():
	"""Artikel -> Silo (bei mehreren Silos für einen Artikel das zuletzt angelegte)."""
	return {
		s.artikel: s.name
		for s in frappe.get_all(
			"Silo", filters={"aktiv": 1}, fields=["name", "artikel"], order_by="creation asc"
		)
	}


def _station(station):
	if not station or not frappe.db.exists("Terminal Station", station):
		_fehler(_("Station {0} ist nicht eingerichtet.").format(station or "-"))
	return frappe.get_cached_doc("Terminal Station", station)


def _liste(wert):
	if isinstance(wert, str):
		return json.loads(wert or "[]")
	return wert or []


# ---------------------------------------------------------------------------
# Stammdaten für die Oberfläche
# ---------------------------------------------------------------------------


@frappe.whitelist()
def stationen() -> list[dict]:
	return frappe.get_all(
		"Terminal Station", filters={"aktiv": 1}, fields=["name", "typ"], order_by="station_name"
	)


@frappe.whitelist()
def start(station: str) -> dict:
	s = _station(station)
	return {"station": s.name, "typ": s.typ, "nutzer": frappe.session.user}


@frappe.whitelist()
def rezepte(station: str) -> list[dict]:
	"""Herstellbare Artikel dieser Station (mit aktiver Standard-Stückliste)."""
	s = _station(station)
	stufen = STATION_ZIELE.get(s.typ, [])
	if not stufen:
		return []
	return frappe.db.sql(
		"""
		select i.name as artikel, i.item_name as name, i.kt_chargen_stufe as stufe, b.name as bom
		from `tabItem` i
		join `tabBOM` b on b.item = i.name and b.is_default = 1 and b.is_active = 1 and b.docstatus = 1
		where i.disabled = 0 and i.kt_chargen_stufe in %(stufen)s
		order by field(i.kt_chargen_stufe, %(reihenfolge)s), i.item_name
		""",
		{"stufen": tuple(stufen), "reihenfolge": ",".join(stufen)},
		as_dict=True,
	)


@frappe.whitelist()
def rezept(artikel: str, menge: float | None = None) -> dict:
	"""Zutaten laut Standard-Stückliste, auf die Sollmenge umgerechnet."""
	bom = frappe.db.get_value("BOM", {"item": artikel, "is_default": 1, "is_active": 1, "docstatus": 1})
	if not bom:
		_fehler(_("Für {0} gibt es kein aktives Rezept (Stückliste).").format(artikel))
	b = frappe.get_cached_doc("BOM", bom)
	faktor = flt(menge or b.quantity) / flt(b.quantity or 1)
	silos = _silo_je_artikel()
	zutaten = [
		{
			"artikel": z.item_code,
			"name": z.item_name,
			"menge": flt(z.qty * faktor, 3),
			"einheit": z.stock_uom or z.uom,
			"stufe": artikel_stufe(z.item_code),
			"silo": silos.get(z.item_code),
		}
		for z in b.items
	]
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"stufe": artikel_stufe(artikel),
		"bom": bom,
		"sollmenge": flt(menge or b.quantity, 3),
		# Ausbeute nur über Zutaten in der Einheit des Produkts (kg); Packmittel in Stück zählen nicht
		"ausbeute": flt(b.quantity)
		/ (sum(flt(z.stock_qty or z.qty) for z in b.items if (z.stock_uom or z.uom) == b.uom) or 1),
		"einheit": b.uom,
		"zutaten": zutaten,
		"rework_moeglich": artikel_stufe(artikel) in REWORK_ZIELE,
		"ausgabe_silo": silos.get(artikel),
		"einheiten": paletten.einheiten(artikel) if artikel_stufe(artikel) == "Fertigware" else [],
	}


@frappe.whitelist()
def rework_artikel() -> list[dict]:
	return frappe.get_all(
		"Item",
		filters={"kt_chargen_stufe": "Rework", "disabled": 0},
		fields=["name as artikel", "item_name as name", "kt_allergengruppe as allergengruppe"],
		order_by="item_name",
	)


@frappe.whitelist()
def wareneingang_artikel() -> list[dict]:
	silos = _silo_je_artikel()
	artikel = frappe.get_all(
		"Item",
		filters={"kt_chargen_stufe": ["in", ["Rohstoff", "Packmittel"]], "disabled": 0, "has_batch_no": 1},
		fields=[
			"name as artikel",
			"item_name as name",
			"has_expiry_date",
			"kt_freigabe_pflicht",
			"stock_uom",
		],
		order_by="item_name",
	)
	for a in artikel:
		a["silo"] = silos.get(a["artikel"])
	return artikel


@frappe.whitelist()
def auftraege(station: str, kunde: str | None = None) -> list[dict]:
	"""Offene Kundenaufträge (Fertigware): was ist bestellt, verpackt, geliefert, noch offen."""
	_station(station)
	bedingung = "and so.customer = %(kunde)s" if kunde else ""
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
			and i.kt_chargen_stufe = 'Fertigware' and soi.delivered_qty < soi.qty {bedingung}
		order by termin, so.name, soi.idx
		""",
		{"kunde": kunde},
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
	return zeilen


@frappe.whitelist()
def kunden() -> list[dict]:
	return frappe.get_all(
		"Customer",
		filters={"disabled": 0},
		fields=["name", "customer_name"],
		order_by="customer_name",
		limit=200,
	)


@frappe.whitelist()
def silos() -> list[dict]:
	from keks_trace.silo import bestand

	jetzt = now_datetime()
	ergebnis = []
	for s in frappe.get_all(
		"Silo", filters={"aktiv": 1}, fields=["name", "typ", "artikel", "warehouse"], order_by="name"
	):
		ergebnis.append(
			{
				"silo": s.name,
				"typ": s.typ,
				"artikel": s.artikel,
				"bestand": flt(sum(c["menge"] for c in bestand(s.warehouse, jetzt)), 3),
			}
		)
	return ergebnis


# ---------------------------------------------------------------------------
# Scan auflösen
# ---------------------------------------------------------------------------


def charge_lager(charge) -> dict[str, float]:
	"""Bestand einer Charge je Lagerort."""
	zeilen = frappe.db.sql(
		"""
		select sbe.warehouse, sum(sbe.qty) as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
		group by sbe.warehouse
		""",
		charge,
		as_dict=True,
	)
	return {z.warehouse: flt(z.menge) for z in zeilen if flt(z.menge) > EPS}


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
			"Produkttraeger", code, ["name", "typ", "status", "charge", "artikel", "menge"], as_dict=True
		)
		erg = {
			"typ": "behaelter",
			"code": code,
			"behaelter": code,
			"behaelter_typ": t.typ,
			"status": t.status,
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

	_fehler(_("Code {0} ist unbekannt (kein Behälter, Silo, Palette oder Charge).").format(frappe.bold(code)))


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
	return r


# ---------------------------------------------------------------------------
# Prüfen einer gescannten Zutat
# ---------------------------------------------------------------------------


def _pruefe_charge(charge, artikel):
	status, grund, verfall = frappe.db.get_value(
		"Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"]
	)
	if status == "Gesperrt":
		_fehler(_("Charge {0} ist gesperrt: {1}").format(frappe.bold(charge), grund or "-"))
	if verfall and getdate(verfall) < getdate(nowdate()):
		_fehler(
			_("Charge {0} ({1}) ist abgelaufen seit {2}. Nicht verwenden.").format(
				frappe.bold(charge), artikel, formatdate(verfall)
			)
		)


def _pruefe_rework_fuer(rework, ziel):
	from keks_trace.rework import _pruefe_allergene

	if artikel_stufe(ziel) not in REWORK_ZIELE:
		_fehler(_("Rework darf nur in Grundteig oder veredelten Teig."))
	regel = frappe.db.get_value(
		"Rework Regel", {"rework_artikel": rework, "ziel_artikel": ziel, "aktiv": 1}, "max_anteil_prozent"
	)
	if regel is None:
		_fehler(_("Rework {0} ist für {1} nicht zugelassen (keine Rework-Regel).").format(rework, ziel))
	_pruefe_allergene(rework, ziel)
	return flt(regel)


def _zeile(code, menge, ziel=None, erlaubt=None):
	"""Löst einen Scan auf und prüft ihn als Zutat. Gibt die Buchungszeile zurück."""
	menge = flt(menge)
	if menge <= EPS:
		_fehler(_("Bitte eine Menge größer 0 eingeben."))
	r = aufloesen(code)
	if r["typ"] == "palette":
		_fehler(_("{0} ist eine Palette. Bitte das Los oder die Kiste scannen.").format(r["code"]))
	artikel = r.get("artikel")
	if not artikel:
		_fehler(_("Behälter {0} ist leer.").format(r["code"]))

	stufe = artikel_stufe(artikel)
	ist_rework = stufe == "Rework"
	max_anteil = None
	if erlaubt is not None and artikel not in erlaubt:
		if ist_rework and ziel:
			max_anteil = _pruefe_rework_fuer(artikel, ziel)
		else:
			_fehler(
				_("{0} ({1}) gehört nicht zum Rezept.").format(
					frappe.bold(frappe.get_cached_value("Item", artikel, "item_name")), artikel
				)
			)

	if r["typ"] == "silo":
		from keks_trace.silo import bestand

		frei, offen = bestand(r["lager"], now_datetime()), menge
		for c in frei:
			if offen <= EPS:
				break
			_pruefe_charge(c["charge"], artikel)
			offen -= c["menge"]
		if offen > EPS:
			_fehler(_("Im {0} sind rechnerisch nur {1} kg.").format(r["silo"], flt(menge - offen, 3)))
	else:
		_pruefe_charge(r["charge"], artikel)
		if r["typ"] == "behaelter" and menge > flt(r["inhalt"]) * 1.005 + EPS:
			_fehler(_("Behälter {0} enthält nur {1} kg.").format(r["behaelter"], r["inhalt"]))
		if r["typ"] == "charge" and menge > flt(r["inhalt"]) + EPS:
			_fehler(_("Von Charge {0} sind nur {1} kg am Lager.").format(r["charge"], r["inhalt"]))
		if not r.get("lager"):
			_fehler(_("Charge {0} hat keinen Bestand.").format(r["charge"]))

	return {
		"code": r["code"],
		"typ": r["typ"],
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"charge": r.get("charge") if r["typ"] != "silo" else None,
		"lager": r["lager"],
		"behaelter": r.get("behaelter"),
		"silo": r.get("silo"),
		"menge": flt(menge, 3),
		"einheit": frappe.get_cached_value("Item", artikel, "stock_uom"),
		"rework": ist_rework,
		"max_anteil": max_anteil,
	}


@frappe.whitelist()
def pruefe_zeile(station: str, ziel: str, code: str, menge: float) -> dict:
	"""Sofortprüfung einer gescannten Zutat für ein Rezept (grün/rot am Terminal)."""
	_station(station)
	erlaubt = {z["artikel"] for z in rezept(ziel)["zutaten"]}
	return _zeile(code, menge, ziel, erlaubt)


# ---------------------------------------------------------------------------
# Buchen
# ---------------------------------------------------------------------------


def _neue_charge(artikel, herstelldatum=None, charge_id=None, lieferant=None, verfall=None):
	if not charge_id:
		# Fertigware bekommt eine kurze Los-Nummer (passt auf Beutel und ins GS1-Etikett)
		kurz = artikel_stufe(artikel) == "Fertigware"
		praefix = ("L" if kurz else f"{artikel}-") + f"{now_datetime().strftime('%y%m%d')}-"
		n = frappe.db.count("Batch", {"name": ["like", praefix + "%"]}) + 1
		while frappe.db.exists("Batch", f"{praefix}{n:02d}"):
			n += 1
		charge_id = f"{praefix}{n:02d}"
	werte = {
		"doctype": "Batch",
		"item": artikel,
		"batch_id": charge_id,
		"manufacturing_date": herstelldatum,
		"supplier": lieferant,
	}
	if verfall:
		werte["expiry_date"] = verfall
	if artikel_stufe(artikel) == "Fertigware":
		werte["kt_los"] = charge_id
	return frappe.get_doc(werte).insert().name


def _se_zeile(z, s_warehouse=None, t_warehouse=None):
	uom = frappe.get_cached_value("Item", z["artikel"], "stock_uom")
	return {
		"item_code": z["artikel"],
		"qty": z["menge"],
		"transfer_qty": z["menge"],
		"uom": uom,
		"stock_uom": uom,
		"conversion_factor": 1,
		"s_warehouse": s_warehouse,
		"t_warehouse": t_warehouse,
		"use_serial_batch_fields": 1,
		"batch_no": z.get("charge"),
		"kt_traeger": z.get("behaelter"),
	}


def _neues_gebinde(gebindeart=None) -> str:
	from frappe.model.naming import getseries

	code = "G" + getseries("KT-GEBINDE-", 6)
	frappe.get_doc(
		{"doctype": "Produkttraeger", "code": code, "typ": "Gebinde", "gebindeart": gebindeart}
	).insert(ignore_permissions=True)
	return code


def _ziel_lager(s, artikel):
	silo = frappe.db.get_value(
		"Silo", {"artikel": artikel, "aktiv": 1}, "warehouse", order_by="creation desc"
	)
	if silo:
		return silo
	lager = s.fertiglager if artikel_stufe(artikel) == "Fertigware" else s.produktionslager
	if not lager:
		_fehler(_("An der Station {0} ist kein Ziellager eingerichtet.").format(s.name))
	return lager


def _ziel_behaelter(code):
	if not code:
		return None
	r = aufloesen(code)
	if r["typ"] != "behaelter":
		_fehler(_("{0} ist kein Behälter.").format(code))
	if r["status"] in ("Reinigung", "Gesperrt"):
		_fehler(_("Behälter {0} ist auf '{1}' gesetzt.").format(code, r["status"]))
	if r["behaelter_typ"] == "Gebinde":
		_fehler(_("{0} ist ein Gebinde vom Wareneingang, kein Zielbehälter.").format(code))
	if r.get("charge"):
		_fehler(_("Behälter {0} ist noch mit {1} belegt.").format(code, r["charge"]))
	return code


def _meldungen():
	"""Hinweise (msgprint) aus dem Buchen als Text einsammeln."""
	texte = []
	for m in frappe.local.message_log or []:
		try:
			m = json.loads(m) if isinstance(m, str) else m
		except ValueError:
			m = {"message": m}
		text = frappe.utils.strip_html(str(m.get("message") or m))
		if text and text not in texte:
			texte.append(text)
	frappe.local.message_log = []
	return texte


@frappe.whitelist()
def vorschau(station: str, ziel: str, zeilen) -> dict:
	"""Los und MHD, bevor gebucht wird (zum Einstellen des Beuteldruckers)."""
	from keks_trace.genealogie import daten_berechnen

	_station(station)
	if artikel_stufe(ziel) != "Fertigware":
		return {}
	eingaenge = []
	for z in _liste(zeilen):
		r = aufloesen(z["code"])
		if r.get("charge") and r["typ"] != "silo":
			eingaenge.append((r["charge"], r["artikel"], flt(z.get("menge"))))
	charge, los = None, None
	if los_modul.format_() == "JWWT":
		los = los_modul.jwwt(nowdate())
		name = f"{ziel}-{getdate(nowdate()).isocalendar()[0]}-{los}"
		charge = name if frappe.db.exists("Batch", name) else None
	werte = daten_berechnen(ziel, eingaenge, nowdate(), charge, "-")
	vorher = frappe.db.get_value("Batch", charge, "expiry_date") if charge else None
	mhd = werte.get("expiry_date")
	return {
		"los": los,
		"los_vorhanden": bool(charge),
		"mhd": formatdate(mhd) if mhd else None,
		"mhd_sinkt": bool(vorher and mhd and getdate(mhd) < getdate(vorher)),
		"mhd_bisher": formatdate(vorher) if vorher else None,
	}


@frappe.whitelist()
def herstellen(
	station: str,
	ziel: str,
	zeilen,
	ausbringung: float | None = None,
	ziel_behaelter: str | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	kundenauftrag: str | None = None,
) -> dict:
	"""Fertigung buchen: Zutaten (gescannt) -> neue Charge des Ziels, optional in einen Behälter.

	Fertigware: Ausbringung als Anzahl + Einheit (Karton/Beutel); ziel_behaelter darf eine Palette sein.
	"""
	s = _station(station)
	r = rezept(ziel)
	if r["stufe"] not in STATION_ZIELE.get(s.typ, []):
		_fehler(_("{0} wird nicht an der Station {1} hergestellt.").format(r["name"], s.name))
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	eingaenge = [_zeile(z["code"], z["menge"], ziel, erlaubt) for z in _liste(zeilen)]
	if not eingaenge:
		_fehler(_("Keine Zutaten gescannt."))

	summe = sum(z["menge"] for z in eingaenge if z.get("einheit", r["einheit"]) == r["einheit"])
	if flt(anzahl) > EPS and einheit:
		ausbringung = flt(flt(anzahl) * paletten.faktor(ziel, einheit), 6)
	else:
		anzahl, einheit = None, None
	ausbringung = flt(ausbringung) or flt(summe * r["ausbeute"], 3)
	if kundenauftrag and not frappe.db.exists(
		"Sales Order Item", {"parent": kundenauftrag, "item_code": ziel, "docstatus": 1}
	):
		_fehler(_("{0} ist im Kundenauftrag {1} nicht bestellt.").format(ziel, kundenauftrag))
	palette = paletten.finde(ziel_behaelter) if ziel_behaelter else None
	if palette and r["stufe"] != "Fertigware":
		_fehler(_("Auf eine Palette kommt nur Fertigware."))
	behaelter = None if palette else _ziel_behaelter(ziel_behaelter)
	if palette:
		paletten._offen(palette)

	if r["stufe"] == "Fertigware" and los_modul.format_() == "JWWT":
		charge, _los, _neu = los_modul.tages_charge(ziel, nowdate())
	else:
		charge = _neue_charge(ziel, getdate(nowdate()))
	jetzt = now_datetime()
	ausgabe = _se_zeile(
		{"artikel": ziel, "charge": charge, "menge": ausbringung, "behaelter": behaelter},
		t_warehouse=_ziel_lager(s, ziel),
	)
	ausgabe["is_finished_item"] = 1
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Manufacture",
			"purpose": "Manufacture",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"kt_kundenauftrag": kundenauftrag,
			"items": [_se_zeile(z, s_warehouse=z["lager"]) for z in eingaenge] + [ausgabe],
		}
	)
	se.insert()
	se.submit()
	if palette and kundenauftrag:
		frappe.db.set_value(
			"Palette",
			palette,
			{
				"kundenauftrag": kundenauftrag,
				"kunde": frappe.db.get_value("Sales Order", kundenauftrag, "customer"),
			},
		)
	if palette:
		paletten.beladen(
			palette, charge, anzahl or ausbringung, einheit or frappe.get_cached_value("Item", ziel, "stock_uom"),
			s.name, "Verpackung", "Stock Entry", se.name,
		)  # fmt: skip

	hinweise = list(se.flags.kt_fifo_warnungen or [])
	if se.flags.kt_fehlende_zutaten:
		hinweise.append(_("Laut Rezept nicht gescannt: {0}").format(", ".join(se.flags.kt_fehlende_zutaten)))
	b = frappe.db.get_value("Batch", charge, ["expiry_date", "kt_status", "kt_los"], as_dict=True)
	return {
		"charge": charge,
		"los": b.kt_los,
		"artikel": ziel,
		"name": r["name"],
		"menge": ausbringung,
		"anzahl": anzahl,
		"einheit": einheit,
		"behaelter": behaelter,
		"palette": palette,
		"kundenauftrag": kundenauftrag,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"buchung": se.name,
		"hinweise": [h for h in dict.fromkeys(hinweise + _meldungen())],
	}


@frappe.whitelist()
def rework_erfassen(
	station: str, quelle: str, menge: float, rework_artikel: str, ziel_behaelter: str | None = None
) -> dict:
	"""Teigreste oder Bruch in einen Rework-Behälter umfüllen (neue Rework-Charge)."""
	s = _station(station)
	if artikel_stufe(rework_artikel) != "Rework":
		_fehler(_("{0} ist kein Rework-Artikel.").format(rework_artikel))
	q = _zeile(quelle, menge)
	if q["typ"] == "silo":
		_fehler(_("Aus einem Silo kann kein Rework erfasst werden."))

	zuviel = allergene(frappe.get_cached_value("Item", q["artikel"], "kt_allergengruppe")) - allergene(
		frappe.get_cached_value("Item", rework_artikel, "kt_allergengruppe")
	)
	if zuviel:
		_fehler(
			_(
				"{0} enthält Allergene, die {1} nicht hat: {2}. Bitte den passenden Rework-Behälter wählen."
			).format(q["name"], rework_artikel, ", ".join(sorted(a.capitalize() for a in zuviel)))
		)
	behaelter = _ziel_behaelter(ziel_behaelter)
	charge = _neue_charge(rework_artikel, getdate(nowdate()))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Repack",
			"purpose": "Repack",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile(q, s_warehouse=q["lager"]),
				_se_zeile(
					{
						"artikel": rework_artikel,
						"charge": charge,
						"menge": q["menge"],
						"behaelter": behaelter,
					},
					t_warehouse=_ziel_lager(s, rework_artikel),
				),
			],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", rework_artikel, "item_name"),
		"menge": q["menge"],
		"behaelter": behaelter,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"buchung": se.name,
		"hinweise": _meldungen(),
	}


@frappe.whitelist()
def wareneingang(
	station: str,
	artikel: str,
	lieferantencharge: str,
	menge: float,
	mhd: str | None = None,
	lieferant: str | None = None,
	silo: str | None = None,
	gebinde: int | None = None,
	gebindeart: str | None = None,
) -> dict:
	"""Wareneingang mit Lieferantencharge, ins Rohstofflager oder direkt ins Silo.

	gebinde = Anzahl Gebinde (Sack, Fass, IBC, ...); menge ist dann die Menge JE Gebinde. Jedes Gebinde
	bekommt einen eigenen Code (Etikett) und wird später in der Backstube gescannt.
	"""
	s = _station(station)
	menge = flt(menge)
	gebinde = cint(gebinde) if not silo else 0
	lieferantencharge = (lieferantencharge or "").strip()
	if menge <= EPS:
		_fehler(_("Bitte eine Menge größer 0 eingeben."))
	if not lieferantencharge:
		_fehler(_("Bitte die Charge des Lieferanten scannen oder eingeben."))
	if frappe.get_cached_value("Item", artikel, "has_expiry_date") and not mhd:
		_fehler(_("Bitte das MHD eingeben."))

	if silo:
		silo_doc = frappe.get_cached_doc("Silo", silo)
		if silo_doc.artikel != artikel:
			_fehler(_("{0} ist für {1}, nicht für {2}.").format(silo, silo_doc.artikel, artikel))
		lager = silo_doc.warehouse
	else:
		lager = s.rohstofflager
		if not lager:
			_fehler(_("An der Station {0} ist kein Rohstofflager eingerichtet.").format(s.name))

	charge_id = lieferantencharge
	if frappe.db.exists("Batch", charge_id):
		if frappe.db.get_value("Batch", charge_id, "item") != artikel:
			charge_id = f"{artikel}-{lieferantencharge}"
	charge = (
		charge_id
		if frappe.db.exists("Batch", charge_id)
		else _neue_charge(artikel, None, charge_id, lieferant, getdate(mhd) if mhd else None)
	)

	jetzt = now_datetime()
	codes = [_neues_gebinde(gebindeart) for _i in range(gebinde)]
	rate = flt(frappe.get_cached_value("Item", artikel, "valuation_rate"))
	zeilen = []
	for code in codes or [None]:
		zeile = _se_zeile(
			{"artikel": artikel, "charge": charge, "menge": menge, "behaelter": code}, t_warehouse=lager
		)
		if rate:
			zeile["basic_rate"] = rate
		else:
			zeile["allow_zero_valuation_rate"] = 1
		zeilen.append(zeile)
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Receipt",
			"purpose": "Material Receipt",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": zeilen,
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"menge": flt(menge * (len(codes) or 1), 3),
		"gebinde": codes,
		"lager": silo or lager,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund,
		"buchung": se.name,
		"hinweise": _meldungen(),
	}


def _lieferpositionen(z):
	"""Eine Lieferzeile vom Terminal in Positionen auflösen.

	{"palette": NVE, "ganz": 1}                          ganze Palette
	{"palette": NVE, "charge": Los, "anzahl", "einheit"}   einzelne Kartons von einer Palette
	{"code": Los, "anzahl", "einheit"}                     lose Kartons (auf keiner Palette)
	"""
	if z.get("palette") and z.get("ganz"):
		nve = paletten.finde(z["palette"])
		if not nve:
			_fehler(_("Palette {0} gibt es nicht.").format(z["palette"]))
		status = frappe.db.get_value("Palette", nve, "status")
		if status not in paletten.AKTIV:
			_fehler(_("Palette {0} ist {1}.").format(nve, status.lower()))
		pos = paletten.inhalt(nve)
		if not pos:
			_fehler(_("Palette {0} ist leer.").format(nve))
		return [_lieferposition(p["charge"], p["anzahl"], p["einheit"], nve) for p in pos]
	if z.get("palette"):
		nve = paletten.finde(z["palette"])
		pos = paletten._position(nve, z.get("charge"), z.get("einheit")) if nve else None
		if not pos or flt(z.get("anzahl")) > pos["anzahl"] + EPS:
			_fehler(
				_("Auf Palette {0} sind von Los {1} nur {2} {3}.").format(
					z["palette"], z.get("charge"), flt(pos["anzahl"]) if pos else 0, z.get("einheit")
				)
			)
		return [_lieferposition(z["charge"], z["anzahl"], z["einheit"], nve)]
	r = aufloesen(z.get("code"))
	if r["typ"] == "palette":
		return _lieferpositionen({"palette": r["palette"], "ganz": 1})
	if r["typ"] != "charge":
		_fehler(_("Bitte ein Los oder eine Palette scannen."))
	anzahl = flt(z.get("anzahl") if z.get("anzahl") is not None else z.get("menge"))
	einheit = z.get("einheit") or frappe.get_cached_value("Item", r["artikel"], "stock_uom")
	menge = anzahl * paletten.faktor(r["artikel"], einheit)
	frei = paletten.lose(r["charge"])
	if menge > frei + 1e-4:
		_fehler(
			_(
				"Von Los {0} sind nur {1} {2} lose. Der Rest steht auf Paletten: bitte die Palette scannen."
			).format(r["charge"], paletten._anzahl_text(r["artikel"], frei, einheit), einheit)
		)
	return [_lieferposition(r["charge"], anzahl, einheit, None)]


def _lieferposition(charge, anzahl, einheit, palette):
	artikel = frappe.db.get_value("Batch", charge, "item")
	if artikel_stufe(artikel) != "Fertigware":
		_fehler(_("{0} ist keine Fertigware.").format(frappe.get_cached_value("Item", artikel, "item_name")))
	if flt(anzahl) <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	_pruefe_charge(charge, artikel)
	lager = charge_lager(charge)
	if not lager:
		_fehler(_("Los {0} hat keinen Bestand.").format(charge))
	f = paletten.faktor(artikel, einheit)
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"charge": charge,
		"anzahl": flt(anzahl, 3),
		"einheit": einheit,
		"faktor": f,
		"menge": flt(flt(anzahl) * f, 3),
		"palette": palette,
		"lager": max(lager, key=lager.get),
	}


@frappe.whitelist()
def pruefe_lieferzeile(
	station: str,
	code: str | None = None,
	menge: float | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	palette: str | None = None,
	charge: str | None = None,
	ganz: int = 0,
) -> list[dict]:
	"""Sofortprüfung am Versand. Gibt die Positionen zurück (ganze Palette = mehrere)."""
	_station(station)
	return _lieferpositionen(
		{"code": code, "menge": menge, "anzahl": anzahl, "einheit": einheit, "palette": palette,
		 "charge": charge, "ganz": cint(ganz)}
	)  # fmt: skip


def _lieferzeile(p, kundenauftrag, auftrag_pos) -> dict:
	"""Lieferscheinposition. Mit Auftrag in dessen Einheit (z. B. 0,48 Palette), gezählt bleibt 20 Karton."""
	zeile = {
		"item_code": p["artikel"],
		"qty": p["anzahl"],
		"uom": p["einheit"],
		"conversion_factor": p["faktor"],
		"rate": flt(frappe.get_cached_value("Item", p["artikel"], "standard_rate")) * p["faktor"],
		"warehouse": p["lager"],
		"use_serial_batch_fields": 1,
		"batch_no": p["charge"],
		"kt_palette": p["palette"],
		"kt_anzahl": p["anzahl"],
		"kt_einheit": p["einheit"],
	}
	if kundenauftrag and auftrag_pos.get(p["artikel"]):
		uom, cf, rate = auftrag_pos[("einheit", p["artikel"])]
		zeile.update(
			{
				"qty": flt(p["menge"] / cf, 6),
				"uom": uom,
				"conversion_factor": cf,
				"rate": rate,
				"against_sales_order": kundenauftrag,
				"so_detail": auftrag_pos[p["artikel"]],
			}
		)
	return zeile


@frappe.whitelist()
def lieferung(station: str, kunde: str, zeilen, kundenauftrag: str | None = None) -> dict:
	"""Lieferschein an einen Kunden mit gescannten Paletten und Losen, optional zu einem Kundenauftrag."""
	s = _station(station)
	if not frappe.db.exists("Customer", kunde):
		_fehler(_("Kunde {0} unbekannt.").format(kunde))
	positionen = [p for z in _liste(zeilen) for p in _lieferpositionen(z)]
	if not positionen:
		_fehler(_("Nichts gescannt."))
	auftrag_pos = {}
	if kundenauftrag:
		if frappe.db.get_value("Sales Order", kundenauftrag, "customer") != kunde:
			_fehler(_("Kundenauftrag {0} gehört nicht zu {1}.").format(kundenauftrag, kunde))
		for r in frappe.get_all(
			"Sales Order Item",
			{"parent": kundenauftrag},
			["name", "item_code", "rate", "conversion_factor", "uom"],
			order_by="idx",
		):
			auftrag_pos.setdefault(r.item_code, r.name)
			# ERPNext verlangt im Lieferschein dieselbe Einheit wie im Auftrag (z. B. Palette)
			auftrag_pos.setdefault(
				("einheit", r.item_code), (r.uom, flt(r.conversion_factor) or 1, flt(r.rate))
			)
		fremd = sorted({p["artikel"] for p in positionen if p["artikel"] not in auftrag_pos})
		if fremd:
			_fehler(_("Nicht im Kundenauftrag {0} bestellt: {1}").format(kundenauftrag, ", ".join(fremd)))
	jetzt = now_datetime()
	dn = frappe.get_doc(
		{
			"doctype": "Delivery Note",
			"customer": kunde,
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [_lieferzeile(p, kundenauftrag, auftrag_pos) for p in positionen],
		}
	)
	dn.insert()
	dn.submit()
	return {
		"lieferschein": dn.name,
		"kundenauftrag": kundenauftrag,
		"kunde": dn.customer_name,
		"positionen": len(positionen),
		"menge": flt(sum(p["menge"] for p in positionen), 3),
		"paletten": sorted({p["palette"] for p in positionen if p["palette"]}),
		"hinweise": _meldungen(),
	}


# ---------------------------------------------------------------------------
# Paletten
# ---------------------------------------------------------------------------


def _palette(code):
	nve = paletten.finde(code)
	if not nve:
		_fehler(_("{0} ist keine Palette.").format(code))
	return nve


@frappe.whitelist()
def einheiten(artikel: str) -> list[dict]:
	return paletten.einheiten(artikel)


@frappe.whitelist()
def palette_neu(station: str, typ: str = "Lagerpalette", kunde: str | None = None) -> dict:
	s = _station(station)
	nve = paletten.anlegen(typ, s.name, kunde)
	return paletten.info(nve)


@frappe.whitelist()
def palette_info(code: str) -> dict:
	return paletten.info(_palette(code))


@frappe.whitelist()
def palette_beladen(station: str, palette: str, code: str, anzahl: float, einheit: str) -> dict:
	"""Lose Kartons eines Loses auf die Palette (Los-Etikett scannen)."""
	s = _station(station)
	r = aufloesen(code)
	if r["typ"] != "charge":
		_fehler(_("Bitte das Los scannen."))
	return paletten.beladen(_palette(palette), r["charge"], anzahl, einheit, s.name)


@frappe.whitelist()
def palette_umpacken(station: str, von: str, nach: str, charge: str, anzahl: float, einheit: str) -> dict:
	s = _station(station)
	return paletten.umpacken(_palette(von), _palette(nach), charge, anzahl, einheit, s.name)


@frappe.whitelist()
def palette_schliessen(station: str, palette: str) -> dict:
	_station(station)
	return paletten.schliessen(_palette(palette))


@frappe.whitelist()
def palette_oeffnen(station: str, palette: str) -> dict:
	_station(station)
	return paletten.oeffnen(_palette(palette))


@frappe.whitelist()
def silo_leer(station: str, silo: str) -> dict:
	from keks_trace.silo import leermeldung

	s = _station(station)
	erg = leermeldung(silo, bemerkung=_("Leermeldung am Terminal {0}").format(s.name))
	if erg.get("ausbuchung"):
		frappe.db.set_value("Stock Entry", erg["ausbuchung"], "kt_station", s.name)
	erg["hinweise"] = _meldungen()
	return erg
