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
from frappe.utils import flt, formatdate, getdate, now_datetime, nowdate

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
		"ausbeute": flt(b.quantity) / (sum(flt(z.qty) for z in b.items) or 1),
		"zutaten": zutaten,
		"rework_moeglich": artikel_stufe(artikel) in REWORK_ZIELE,
		"ausgabe_silo": silos.get(artikel),
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
		fields=["name as artikel", "item_name as name", "has_expiry_date", "kt_freigabe_pflicht"],
		order_by="item_name",
	)
	for a in artikel:
		a["silo"] = silos.get(a["artikel"])
	return artikel


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

	_fehler(_("Code {0} ist unbekannt (kein Behälter, Silo oder Charge).").format(frappe.bold(code)))


@frappe.whitelist()
def info(code: str) -> dict:
	"""Info-Scan: alles Wichtige zu einem Code."""
	from keks_trace import silo as silo_modul

	r = aufloesen(code)
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
		praefix = f"{artikel}-{now_datetime().strftime('%y%m%d')}-"
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
def herstellen(
	station: str, ziel: str, zeilen, ausbringung: float | None = None, ziel_behaelter: str | None = None
) -> dict:
	"""Fertigung buchen: Zutaten (gescannt) -> neue Charge des Ziels, optional in einen Behälter."""
	s = _station(station)
	r = rezept(ziel)
	if r["stufe"] not in STATION_ZIELE.get(s.typ, []):
		_fehler(_("{0} wird nicht an der Station {1} hergestellt.").format(r["name"], s.name))
	erlaubt = {z["artikel"] for z in r["zutaten"]}
	eingaenge = [_zeile(z["code"], z["menge"], ziel, erlaubt) for z in _liste(zeilen)]
	if not eingaenge:
		_fehler(_("Keine Zutaten gescannt."))

	summe = sum(z["menge"] for z in eingaenge)
	ausbringung = flt(ausbringung) or flt(summe * r["ausbeute"], 3)
	behaelter = _ziel_behaelter(ziel_behaelter)

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
			"items": [_se_zeile(z, s_warehouse=z["lager"]) for z in eingaenge] + [ausgabe],
		}
	)
	se.insert()
	se.submit()

	hinweise = list(se.flags.kt_fifo_warnungen or [])
	if se.flags.kt_fehlende_zutaten:
		hinweise.append(_("Laut Rezept nicht gescannt: {0}").format(", ".join(se.flags.kt_fehlende_zutaten)))
	b = frappe.db.get_value("Batch", charge, ["expiry_date", "kt_status"], as_dict=True)
	return {
		"charge": charge,
		"artikel": ziel,
		"name": r["name"],
		"menge": ausbringung,
		"behaelter": behaelter,
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
) -> dict:
	"""Wareneingang mit Lieferantencharge, ins Rohstofflager oder direkt ins Silo."""
	s = _station(station)
	menge = flt(menge)
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
	zeile = _se_zeile({"artikel": artikel, "charge": charge, "menge": menge}, t_warehouse=lager)
	rate = flt(frappe.get_cached_value("Item", artikel, "valuation_rate"))
	if rate:
		zeile["basic_rate"] = rate
	else:
		zeile["allow_zero_valuation_rate"] = 1
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
			"items": [zeile],
		}
	)
	se.insert()
	se.submit()
	b = frappe.db.get_value("Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"menge": menge,
		"lager": silo or lager,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund,
		"buchung": se.name,
		"hinweise": _meldungen(),
	}


@frappe.whitelist()
def pruefe_lieferzeile(station: str, code: str, menge: float) -> dict:
	_station(station)
	z = _zeile(code, menge)
	if artikel_stufe(z["artikel"]) != "Fertigware":
		_fehler(_("{0} ist keine Fertigware.").format(z["name"]))
	return z


@frappe.whitelist()
def lieferung(station: str, kunde: str, zeilen) -> dict:
	"""Lieferschein an einen Kunden mit den gescannten Losen."""
	s = _station(station)
	if not frappe.db.exists("Customer", kunde):
		_fehler(_("Kunde {0} unbekannt.").format(kunde))
	positionen = [pruefe_lieferzeile(station, z["code"], z["menge"]) for z in _liste(zeilen)]
	if not positionen:
		_fehler(_("Keine Lose gescannt."))
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
			"items": [
				{
					"item_code": p["artikel"],
					"qty": p["menge"],
					"rate": flt(frappe.get_cached_value("Item", p["artikel"], "standard_rate")),
					"warehouse": p["lager"],
					"use_serial_batch_fields": 1,
					"batch_no": p["charge"],
				}
				for p in positionen
			],
		}
	)
	dn.insert()
	dn.submit()
	return {
		"lieferschein": dn.name,
		"kunde": dn.customer_name,
		"positionen": len(positionen),
		"menge": flt(sum(p["menge"] for p in positionen), 3),
		"hinweise": _meldungen(),
	}


@frappe.whitelist()
def silo_leer(station: str, silo: str) -> dict:
	from keks_trace.silo import leermeldung

	s = _station(station)
	erg = leermeldung(silo, bemerkung=_("Leermeldung am Terminal {0}").format(s.name))
	if erg.get("ausbuchung"):
		frappe.db.set_value("Stock Entry", erg["ausbuchung"], "kt_station", s.name)
	erg["hinweise"] = _meldungen()
	return erg
