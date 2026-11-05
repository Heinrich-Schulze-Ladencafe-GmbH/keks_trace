"""Wareneingang: Scan des Lieferanten-Etiketts (GS1), Bestellungen, Gebinde."""

import frappe
from frappe import _
from frappe.utils import cint, flt, formatdate, getdate, now_datetime, nowdate

from keks_trace import gs1, haccp, kennzeichnung
from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.buchung.basis import EPS, _fehler, _silo_je_artikel, _vorraete
from keks_trace.buchung.beleg import _neue_charge, _se_zeile
from keks_trace.buchung.scan import _artikel_zur_gtin, _charge_name
from keks_trace.terminal.basis import _darf, _meldungen, _station
from keks_trace.utils import artikel_stufe

GEBINDEARTEN = ("Sack", "Fass", "IBC", "Eimer", "Karton", "Kanister", "BigBag", "Sonstiges")


def _pruefe_lieferantencharge(artikel: str, text: str) -> None:
	"""Plausibilität: eine Charge enthält eine Ziffer und ist nicht der Artikelname (z. B. „Präsentkarton“)."""
	if not 2 <= len(text) <= 60:
		_fehler(
			_("Charge {0}: bitte die Charge des Lieferanten (2 bis 60 Zeichen).").format(frappe.bold(text))
		)
	name = (frappe.get_cached_value("Item", artikel, "item_name") or "").casefold()
	if not any(z.isdigit() for z in text) or text.casefold() in (name, artikel.casefold()):
		_fehler(
			_(
				"{0} ist keine Charge. Bitte die Charge vom Etikett des Lieferanten scannen oder abtippen."
			).format(frappe.bold(text))
		)


@frappe.whitelist()
def wareneingang_scan(code: str) -> dict:
	"""Etikett des Lieferanten im Wareneingang lesen. Schlägt vor, bucht nichts.

	GS1-128/DataMatrix: Artikel (über GTIN), Charge, MHD, Gewicht. Einfache EAN: nur Artikel und Einheit.
	Alles andere: Text, wird als Charge vorgeschlagen.
	"""
	g = gs1.lesen(code)
	gtin = g.get("gtin") if g else gs1.ean(code)
	erg = {"code": (code or "").strip(), "gs1": bool(g), "gtin": gtin}
	if not g and not gtin:
		erg["charge"] = erg["code"]
		return erg
	if g:
		erg["charge"] = g.get("charge")
		erg["mhd"] = str(g["mhd"]) if g.get("mhd") else None
		erg["netto_kg"] = g.get("netto_kg")
		erg["unvollstaendig"] = bool(g.get("rest"))
	treffer = _artikel_zur_gtin(gtin) if gtin else None
	if not treffer:
		erg["unbekannt"] = True
		return erg
	artikel = treffer["artikel"]
	stufe = artikel_stufe(artikel)
	if stufe not in ("Rohstoff", "Packmittel") or not frappe.get_cached_value(
		"Item", artikel, "has_batch_no"
	):
		_fehler(
			_("Code {0} gehört zu {1} ({2}) - das ist kein Rohstoff oder Packmittel mit Charge.").format(
				gtin, artikel, frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	erg["artikel"] = artikel
	erg["einheit"] = treffer["einheit"]
	# Menge je Gebinde: Gewicht aus dem Etikett, sonst Umrechnung der Einheit des Barcodes (Karton = 25 Stk)
	lager_einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	je = None
	if erg.get("netto_kg") and lager_einheit in ("Kg", "kg"):
		je = erg["netto_kg"]
	elif treffer["einheit"] and treffer["einheit"] != lager_einheit:
		je = next(
			(
				e["faktor"]
				for e in paletten.einheiten(artikel, alle=True)
				if e["einheit"] == treffer["einheit"]
			),
			None,
		)
	erg["menge_je_gebinde"] = je
	erg["gebindeart"] = treffer["einheit"] if treffer["einheit"] in GEBINDEARTEN else None
	if erg.get("charge"):
		vorhanden = _charge_name(artikel, erg["charge"])
		erg["charge_bekannt"] = bool(frappe.db.exists("Batch", vorhanden))
	return erg


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
	lieferanten = _lieferanten()
	for a in artikel:
		a["silo"] = silos.get(a["artikel"]) if a["artikel"] not in _vorraete() else None
		a["bio"] = kennzeichnung.BIO in kennzeichnung.artikel_kennzeichen(a["artikel"])
		eigene = frappe.get_all("Item Supplier", {"parent": a["artikel"]}, pluck="supplier")
		a["lieferanten"] = [
			x
			for x in lieferanten
			if (not eigene or x["lieferant"] in eigene) and (x["bio_ok"] or not a["bio"])
		]
		a["pruefungen"] = [
			haccp.beschreibung(p) for p in haccp.fuer_artikel(haccp.WARENEINGANG, a["artikel"])
		]
		a["bestellungen"] = _bestellungen(a["artikel"])
	return artikel


BESTELLUNG_OFFEN = ("To Receive and Bill", "To Receive")


def _bestellungen(artikel: str) -> list[dict]:
	"""Offene Bestellungen (Einkauf) mit diesem Artikel, älteste Liefertermine zuerst.

	Offen = bestellt minus Eingangsbelege (ERPNext zählt die selbst) minus Wareneingänge am Terminal mit Verweis
	auf die Bestellung (die zählt ERPNext nicht). Menge in der Lagereinheit.
	"""
	zeilen = frappe.db.sql(
		"""
		select po.name as bestellung, po.supplier as lieferant, po.supplier_name as lieferantname,
			po.transaction_date as datum, min(poi.schedule_date) as termin,
			sum(poi.stock_qty) as bestellt, sum(poi.received_qty * poi.conversion_factor) as erhalten
		from `tabPurchase Order Item` poi
		join `tabPurchase Order` po on po.name = poi.parent
		where poi.item_code = %(a)s and po.docstatus = 1 and po.status in %(offen)s
		group by po.name, po.supplier, po.supplier_name, po.transaction_date
		order by termin, po.name
		limit 30
		""",
		{"a": artikel, "offen": BESTELLUNG_OFFEN},
		as_dict=True,
	)
	if not zeilen:
		return []
	am_terminal = dict(
		frappe.db.sql(
			"""
			select se.kt_bestellung, sum(sed.transfer_qty) from `tabStock Entry Detail` sed
			join `tabStock Entry` se on se.name = sed.parent
			where se.docstatus = 1 and sed.item_code = %(a)s and se.kt_bestellung in %(b)s
			group by se.kt_bestellung
			""",
			{"a": artikel, "b": tuple(z.bestellung for z in zeilen)},
		)
	)
	ergebnis = []
	for z in zeilen:
		offen = flt(z.bestellt) - flt(z.erhalten) - flt(am_terminal.get(z.bestellung))
		if offen <= EPS:
			continue
		ergebnis.append(
			{
				"bestellung": z.bestellung,
				"lieferant": z.lieferant,
				"lieferantname": z.lieferantname,
				"datum": formatdate(z.datum) if z.datum else None,
				"termin": formatdate(z.termin) if z.termin else None,
				"bestellt": flt(z.bestellt, 3),
				"offen": flt(offen, 3),
			}
		)
	return ergebnis


def _lieferanten() -> list[dict]:
	ergebnis = []
	for x in frappe.get_all("Supplier", {"disabled": 0}, ["name", "supplier_name"], order_by="supplier_name"):
		st = kennzeichnung.bio_lieferant_status(x.name)
		ergebnis.append({"lieferant": x.name, "name": x.supplier_name, "bio_ok": st["ok"]})
	return ergebnis


def _neues_gebinde(gebindeart=None) -> str:
	from frappe.model.naming import getseries

	code = "G" + getseries("KT-GEBINDE-", 6)
	frappe.get_doc(
		{"doctype": "Produkttraeger", "code": code, "typ": "Gebinde", "gebindeart": gebindeart}
	).insert(ignore_permissions=True)
	return code


@frappe.whitelist()
@einmalig
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
	pruefwerte=None,
	etiketten=1,
	bestellung: str | None = None,
) -> dict:
	"""Wareneingang mit Lieferantencharge, ins Rohstofflager oder direkt ins Silo.

	bestellung = Bestellung (Einkauf), zu der die Lieferung gehört. Optional; ohne Lieferant gilt der der Bestellung.

	gebinde = Anzahl Gebinde (Sack, Fass, IBC, ...); menge ist dann die Menge JE Gebinde.
	etiketten = 1: jedes Gebinde bekommt einen eigenen Code (Etikett) und wird in der Backstube gescannt.
	etiketten = 0: kein eigenes Etikett - das Etikett des Lieferanten trägt die Charge (GS1-128) und wird
	in der Backstube gescannt; gebucht wird die Gesamtmenge auf die Charge.
	"""
	s = _station(station)
	_darf(s, "wareneingang")
	menge = flt(menge)
	gebinde = cint(gebinde) if not silo else 0
	lieferantencharge = (lieferantencharge or "").strip()
	if menge <= EPS:
		_fehler(_("Bitte eine Menge größer 0 eingeben."))
	if not lieferantencharge:
		_fehler(_("Bitte die Charge des Lieferanten scannen oder eingeben."))
	g = gs1.lesen(lieferantencharge)
	if g:
		# Ganzes Lieferanten-Etikett ins Chargenfeld gescannt: Charge herauslesen, Artikel muss passen
		treffer = _artikel_zur_gtin(g["gtin"]) if g.get("gtin") else None
		if treffer and treffer["artikel"] != artikel:
			_fehler(
				_("Das Etikett gehört zu {0} ({1}), nicht zu {2}.").format(
					treffer["artikel"],
					frappe.get_cached_value("Item", treffer["artikel"], "item_name"),
					artikel,
				)
			)
		if not g.get("charge"):
			_fehler(_("Auf diesem Etikett steht keine Charge im Strichcode. Bitte die Charge abtippen."))
		lieferantencharge = g["charge"]
	_pruefe_lieferantencharge(artikel, lieferantencharge)
	lieferant = _pruefe_bestellung(bestellung, artikel, lieferant)
	if frappe.get_cached_value("Item", artikel, "has_expiry_date") and not mhd:
		_fehler(_("Bitte das MHD eingeben."))
	if mhd:
		try:
			mhd = getdate(mhd)
		except Exception:
			_fehler(_("MHD {0} ist kein gültiges Datum.").format(mhd))
		if mhd < getdate(nowdate()):
			_fehler(
				_("MHD {0} liegt in der Vergangenheit: Ware abgelaufen, nicht annehmen.").format(
					formatdate(mhd)
				)
			)
	if kennzeichnung.BIO in kennzeichnung.artikel_kennzeichen(artikel):
		kennzeichnung.pruefe_bio_lieferant(lieferant, artikel)

	pruef_ergebnisse = haccp.bei_buchung(haccp.WARENEINGANG, artikel, pruefwerte, s.name)
	abgelehnt = haccp.verweigert(pruef_ergebnisse)
	if abgelehnt:
		# Annahme verweigern: nichts buchen, aber die Prüfung protokollieren
		for p, ok, felder in pruef_ergebnisse:
			haccp.protokoll(
				p, ok, felder, station=s.name,
				folge=_("Annahme verweigert") if not ok else None,
				bemerkung=_("Lieferantencharge {0}, {1} {2}").format(lieferantencharge, menge, artikel),
			)  # fmt: skip
		return {
			"abgelehnt": True,
			"name": frappe.get_cached_value("Item", artikel, "item_name"),
			"gruende": [
				_("{0}: gemessen {1} {2}, erlaubt {3}").format(
					p.titel,
					haccp._zahl(f["wert"]) if "wert" in f else "-",
					f.get("einheit") or "",
					f.get("grenzwert"),
				)
				for p, _ok, f in abgelehnt
			],
			"korrektur": [p.korrekturmassnahme for p, _ok, _f in abgelehnt if p.korrekturmassnahme],
		}

	if silo:
		silo_doc = frappe.get_cached_doc("Silo", silo)
		if silo_doc.artikel != artikel:
			_fehler(_("{0} ist für {1}, nicht für {2}.").format(silo, silo_doc.artikel, artikel))
		lager = silo_doc.warehouse
	else:
		lager = s.rohstofflager
		if not lager:
			_fehler(_("An der Station {0} ist kein Rohstofflager eingerichtet.").format(s.name))

	charge_id = _charge_name(artikel, lieferantencharge)
	charge = (
		charge_id
		if frappe.db.exists("Batch", charge_id)
		else _neue_charge(artikel, None, charge_id, lieferant, getdate(mhd) if mhd else None)
	)

	jetzt = now_datetime()
	if gebinde and not cint(etiketten):
		menge, gebinde = menge * gebinde, 0
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
			"kt_bestellung": bestellung or None,
			"items": zeilen,
		}
	)
	se.insert()
	se.submit()
	pruef_hinweise = haccp.nach_buchung(pruef_ergebnisse, s.name, charge, se.name)
	b = frappe.db.get_value("Batch", charge, ["kt_status", "kt_sperrgrund", "expiry_date"], as_dict=True)
	return {
		"charge": charge,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"menge": flt(menge * (len(codes) or 1), 3),
		"gebinde": codes,
		"pruef_hinweise": pruef_hinweise,
		"lager": silo or lager,
		"mhd": formatdate(b.expiry_date) if b.expiry_date else None,
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund,
		"buchung": se.name,
		"bestellung": bestellung or None,
		"hinweise": pruef_hinweise + _meldungen(),
	}


def _pruefe_bestellung(bestellung: str | None, artikel: str, lieferant: str | None) -> str | None:
	"""Bestellung muss offen sein, den Artikel enthalten und zum Lieferanten passen. Gibt den Lieferanten zurück."""
	if not bestellung:
		return lieferant
	po = frappe.db.get_value("Purchase Order", bestellung, ["docstatus", "status", "supplier"], as_dict=True)
	if not po or po.docstatus != 1:
		_fehler(_("Bestellung {0} gibt es nicht oder sie ist nicht gebucht.").format(bestellung))
	if po.status not in BESTELLUNG_OFFEN:
		_fehler(_("Bestellung {0} ist nicht mehr offen ({1}).").format(bestellung, _(po.status)))
	if not frappe.db.exists("Purchase Order Item", {"parent": bestellung, "item_code": artikel}):
		_fehler(
			_("In Bestellung {0} ist {1} nicht bestellt.").format(
				bestellung, frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	if lieferant and lieferant != po.supplier:
		_fehler(
			_("Bestellung {0} ist bei {1}, nicht bei {2}.").format(
				bestellung,
				frappe.get_cached_value("Supplier", po.supplier, "supplier_name"),
				frappe.get_cached_value("Supplier", lieferant, "supplier_name"),
			)
		)
	return po.supplier
