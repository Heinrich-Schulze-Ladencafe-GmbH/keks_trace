"""Lieferung, Paketversand (DHL) und Umlagern."""

import frappe
from frappe import _
from frappe.utils import cint, flt, now_datetime

from keks_trace import palette as paletten
from keks_trace.anfrage import einmalig
from keks_trace.buchung.basis import EPS, _fehler
from keks_trace.buchung.beleg import _se_zeile
from keks_trace.buchung.bestand import _lager_chargen, _pruefe_charge, _verkaufslager, charge_lager
from keks_trace.buchung.scan import aufloesen
from keks_trace.terminal.basis import _darf, _liste, _meldungen, _station
from keks_trace.terminal.bestand import _verfuegbar
from keks_trace.utils import versandfaehig


def _lieferpositionen(z, aus_verkauf=False):
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
		pos = [(p, nve) for p in paletten.inhalt(nve)]
		# Versandkartons auf der Palette gehören dazu; gebucht wird je Karton (seine NVE an der Position)
		for k in paletten.kartons(nve):
			pos += [(p, k) for p in paletten.inhalt(k)]
		if not pos:
			_fehler(_("Palette {0} ist leer.").format(nve))
		return [_lieferposition(p["charge"], p["anzahl"], p["einheit"], von, aus_verkauf) for p, von in pos]
	if z.get("palette"):
		nve = paletten.finde(z["palette"])
		pos = paletten._position(nve, z.get("charge"), z.get("einheit")) if nve else None
		if not pos or flt(z.get("anzahl")) > pos["anzahl"] + EPS:
			_fehler(
				_("Auf Palette {0} sind von Los {1} nur {2} {3}.").format(
					z["palette"], z.get("charge"), flt(pos["anzahl"]) if pos else 0, z.get("einheit")
				)
			)
		return [_lieferposition(z["charge"], z["anzahl"], z["einheit"], nve, aus_verkauf)]
	r = aufloesen(z.get("code"))
	if r["typ"] == "palette":
		return _lieferpositionen({"palette": r["palette"], "ganz": 1}, aus_verkauf)
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
	return [_lieferposition(r["charge"], anzahl, einheit, None, aus_verkauf)]


@frappe.whitelist()
def umlager_ziele(station: str) -> list[dict]:
	"""Lagerorte, die an dieser Station beim Umlagern zur Auswahl stehen (fest eingestelltes Ziel zuerst)."""
	s = _station(station)
	ziele = frappe.get_all(
		"Warehouse",
		filters={"kt_umlagerziel": 1, "company": s.company, "disabled": 0},
		fields=["name", "warehouse_name", "kt_lagerverkauf"],
		order_by="kt_lagerverkauf desc, warehouse_name",
	)
	if s.umlager_ziel:
		fest = [
			{
				"name": s.umlager_ziel,
				"titel": frappe.get_cached_value("Warehouse", s.umlager_ziel, "warehouse_name"),
				"lagerverkauf": int(s.umlager_ziel in _verkaufslager()),
			}
		]
		if not fest[0]["lagerverkauf"]:
			return fest
		# Am Lagerverkauf: auch zurück ins Lager (Rücknahme, z. B. zu viel geholt)
		return fest + [
			{"name": z.name, "titel": z.warehouse_name, "lagerverkauf": 0, "zurueck": 1}
			for z in ziele
			if not z.kt_lagerverkauf
		]
	return [{"name": z.name, "titel": z.warehouse_name, "lagerverkauf": z.kt_lagerverkauf} for z in ziele]


def _lieferposition(charge, anzahl, einheit, palette, aus_verkauf=False):
	artikel = frappe.db.get_value("Batch", charge, "item")
	if not versandfaehig(artikel):
		_fehler(
			_("{0} ist weder Fertigware noch lose Ware im Karton.").format(
				frappe.get_cached_value("Item", artikel, "item_name")
			)
		)
	if flt(anzahl) <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	_pruefe_charge(charge, artikel)
	f = paletten.faktor(artikel, einheit)
	verkauf = _verkaufslager()
	auf_linie = set(frappe.get_all("Linie", pluck="lagerort"))  # gehört dem laufenden Produktionsauftrag
	# Rücknahme aus dem Lagerverkauf: nur Bestand dort; sonst nie aus dem Lagerverkauf
	lager = {
		w: m
		for w, m in charge_lager(charge).items()
		if (w in verkauf) == bool(aus_verkauf) and w not in auf_linie
	}
	if not lager:
		_fehler(
			_("Los {0} hat keinen Bestand im {1}.").format(
				charge, _("Lagerverkauf") if aus_verkauf else _("Lager")
			)
		)
	if flt(anzahl) * f > max(lager.values()) + 1e-4:
		_fehler(
			_("Von Los {0} sind im Lager nur {1} {2}.").format(
				charge, paletten._anzahl_text(artikel, max(lager.values()), einheit), einheit
			)
		)
	return {
		"artikel": artikel,
		"name": frappe.get_cached_value("Item", artikel, "item_name"),
		"charge": charge,
		"anzahl": flt(anzahl, 3),
		"einheit": einheit,
		"faktor": f,
		"menge": flt(flt(anzahl) * f, 3),
		"palette": palette,
		"versandkarton": bool(palette)
		and frappe.db.get_value("Palette", palette, "typ") == paletten.VERSANDKARTON,
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
@einmalig
def lieferung(station: str, kunde: str, zeilen, kundenauftrag: str | None = None) -> dict:
	"""Lieferschein an einen Kunden mit gescannten Paletten und Losen, optional zu einem Kundenauftrag."""
	s = _station(station)
	_darf(s, "lieferung")
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


KARTON_TARA_KG = 0.3  # Versandkarton je Paket, für den Plausibilitäts-Vorschlag


@frappe.whitelist()
def paket_vorschlag(station: str, artikel: str, stueck: float, pakete: int = 1) -> dict:
	"""Erwartetes Gewicht (Stückgewicht am Artikel mal Stück + Karton) und was vom verpackten Bestand da ist."""
	_station(station)
	je, einheit = frappe.get_cached_value("Item", artikel, ["weight_per_unit", "weight_uom"])
	faktor = 0.001 if (einheit or "").lower() in ("g", "gram", "gramm") else 1
	netto = flt(je) * faktor * flt(stueck)
	return {
		"erwartet_kg": flt(netto + KARTON_TARA_KG * max(cint(pakete), 1), 2) if je else None,
		"verfuegbar": _verfuegbar(artikel),
		"adresse": None,
	}


def _kundenadresse(artikel=None, kunde=None) -> str | None:
	if not kunde:
		return None
	from frappe.contacts.doctype.address.address import get_address_display, get_default_address

	name = get_default_address("Customer", kunde)
	return frappe.utils.strip_html(get_address_display(name)).strip() if name else None


@frappe.whitelist()
@einmalig
def paket_lieferung(
	station: str,
	kundenauftrag: str,
	artikel: str | None = None,
	stueck: float | None = None,
	gewichte=None,
	sendungsnummer: str | None = None,
	kartons=None,
) -> dict:
	"""Herzen direkt per DHL: Lieferschein über die Stückzahl (älteste Lose zuerst), dazu Pakete und das
	auf der Paketwaage abgelesene Gewicht je Paket. Die Sendungsnummer kann auch später nachgetragen werden."""
	s = _station(station)
	_darf(s, "lieferung")
	if kartons:
		return _paket_lieferung_kartons(s, kundenauftrag, _liste(kartons), sendungsnummer)
	gewichte = [flt(g, 3) for g in _liste(gewichte) if flt(g) > 0]
	if not gewichte:
		_fehler(_("Bitte das Gewicht jedes Pakets von der Paketwaage eintragen."))
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	offen, zeilen = flt(stueck), []
	for c in _lager_chargen(artikel):
		if offen <= EPS:
			break
		frei = min(c["menge"], paletten.lose(c["charge"]))
		n = min(offen, frei)
		if n > EPS:
			zeilen.append({"code": c["charge"], "anzahl": n, "einheit": einheit})
			offen -= n
	if offen > EPS:
		_fehler(
			_("Verpackt im Lager sind nur {0}. Erst verpacken.").format(
				paletten._n(flt(stueck) - offen, einheit)
			)
		)
	erg = lieferung(s.name, kunde, zeilen, kundenauftrag)
	gesamt = flt(sum(gewichte), 3)
	frappe.db.set_value(
		"Delivery Note",
		erg["lieferschein"],
		{
			"kt_pakete": len(gewichte),
			"kt_gewicht_kg": gesamt,
			"kt_paket_gewichte": " / ".join(f"{g:g}".replace(".", ",") for g in gewichte),
			"kt_sendungsnummer": (sendungsnummer or "").strip() or None,
		},
	)
	vorschlag = paket_vorschlag(s.name, artikel, stueck, len(gewichte))
	hinweise = erg["hinweise"]
	erwartet = vorschlag["erwartet_kg"]
	if erwartet and abs(gesamt - erwartet) > erwartet * 0.15:
		hinweise.append(
			_("Gewogen {0} kg, erwartet etwa {1} kg. Bitte Stückzahl im Paket prüfen.").format(
				f"{gesamt:g}".replace(".", ","), f"{erwartet:g}".replace(".", ",")
			)
		)
	return {
		**erg,
		"pakete": len(gewichte),
		"gewicht_kg": gesamt,
		"erwartet_kg": erwartet,
		"adresse": _kundenadresse(kunde=kunde),
		"lose": [z["code"] for z in zeilen],
		"hinweise": hinweise,
	}


def _paket_lieferung_kartons(s, kundenauftrag: str, kartons: list, nummer: str | None) -> dict:
	"""Pakete als Versandkartons: jeder Karton ganz in den Lieferschein, Gewichte aus den Kartons."""
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	nves = []
	for code in kartons:
		nve = paletten.finde(code)
		if not nve or frappe.db.get_value("Palette", nve, "typ") != paletten.VERSANDKARTON:
			_fehler(_("{0} ist kein Versandkarton.").format(code))
		nves.append(nve)
	if len(set(nves)) != len(nves):
		_fehler(_("Ein Versandkarton ist doppelt gescannt."))
	erg = lieferung(s.name, kunde, [{"palette": n, "ganz": 1} for n in nves], kundenauftrag)
	gewichte = [flt(frappe.db.get_value("Palette", n, "gewicht_kg"), 3) for n in nves]
	frappe.db.set_value(
		"Delivery Note",
		erg["lieferschein"],
		{
			"kt_pakete": len(nves),
			"kt_gewicht_kg": flt(sum(gewichte), 3) or None,
			"kt_paket_gewichte": " / ".join(f"{g:g}".replace(".", ",") for g in gewichte if g) or None,
			"kt_sendungsnummer": None,
		},
	)
	if (nummer or "").strip():
		sendungsnummer(s.name, erg["lieferschein"], nummer)
	return {
		**erg,
		"pakete": len(nves),
		"gewicht_kg": flt(sum(gewichte), 3),
		"versandkartons": nves,
		"adresse": _kundenadresse(kunde=kunde),
		"lose": sorted({b for n in nves for b in _lose_im_karton(n, erg["lieferschein"])}),
	}


@frappe.whitelist()
@einmalig
def paket_karton(
	station: str, kundenauftrag: str, artikel: str, stueck: float, gewicht: float | None = None
) -> dict:
	"""Ein Paket als Versandkarton mit eigener NVE packen: Stück dieses Artikels (älteste Lose zuerst, lose im
	Lager) in einen neuen Versandkarton, dazu das Gewicht von der Paketwaage. Geliefert wird später mit
	paket_lieferung(kartons=…)."""
	s = _station(station)
	_darf(s, "lieferung")
	kunde = frappe.db.get_value("Sales Order", kundenauftrag, "customer")
	if not kunde:
		_fehler(_("Kundenauftrag {0} gibt es nicht.").format(kundenauftrag))
	stueck = flt(stueck)
	if stueck <= EPS:
		_fehler(_("Bitte die Stückzahl im Paket eingeben."))
	einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	offen, teile = stueck, []
	for c in _lager_chargen(artikel):
		if offen <= EPS:
			break
		n = min(offen, min(c["menge"], paletten.lose(c["charge"])))
		if n > EPS:
			teile.append((c["charge"], n))
			offen -= n
	if offen > EPS:
		_fehler(
			_("Verpackt im Lager sind nur {0}. Erst verpacken.").format(paletten._n(stueck - offen, einheit))
		)
	nve = paletten.anlegen(paletten.VERSANDKARTON, s.name, kunde)
	frappe.db.set_value(
		"Palette", nve, {"kundenauftrag": kundenauftrag, "gewicht_kg": flt(gewicht, 3) or None}
	)
	for charge, n in teile:
		paletten.beladen(nve, charge, n, einheit, s.name)
	paletten.schliessen(nve)
	return paletten.info(nve)


@frappe.whitelist()
def sendungsnummer(station: str, lieferschein: str, nummer: str) -> dict:
	"""DHL-Sendungsnummer nachtragen (vom Label scannen); mehrere Pakete: jede Nummer einzeln hinzufügen."""
	_station(station)
	nummer = (nummer or "").strip()
	if not nummer:
		_fehler(_("Bitte die Sendungsnummer scannen oder eintippen."))
	alt = frappe.db.get_value("Delivery Note", lieferschein, "kt_sendungsnummer") or ""
	neu = "\n".join([x for x in alt.splitlines() if x.strip()] + [nummer])
	frappe.db.set_value("Delivery Note", lieferschein, "kt_sendungsnummer", neu)
	# Pakete als Versandkarton: die Nummer gehört zum nächsten Karton dieses Lieferscheins ohne Nummer
	karton = None
	for k in _versandkartons_im_lieferschein(lieferschein):
		if not frappe.db.get_value("Palette", k, "sendungsnummer"):
			frappe.db.set_value("Palette", k, "sendungsnummer", nummer)
			karton = k
			break
	return {"lieferschein": lieferschein, "sendungsnummern": neu.splitlines(), "versandkarton": karton}


def _lose_im_karton(karton: str, lieferschein: str) -> list[str]:
	return frappe.get_all(
		"Paletten Bewegung",
		filters={"palette": karton, "beleg": lieferschein, "art": "Lieferung"},
		pluck="charge",
		distinct=True,
	)


def _versandkartons_im_lieferschein(lieferschein: str) -> list[str]:
	return [
		k
		for k in dict.fromkeys(
			frappe.get_all(
				"Paletten Bewegung",
				filters={"beleg_typ": "Delivery Note", "beleg": lieferschein, "art": "Lieferung"},
				pluck="palette",
				order_by="creation",
			)
		)
		if frappe.db.get_value("Palette", k, "typ") == paletten.VERSANDKARTON
	]


@frappe.whitelist()
@einmalig
def umlagern(
	station: str,
	code: str | None = None,
	anzahl: float | None = None,
	einheit: str | None = None,
	palette: str | None = None,
	charge: str | None = None,
	ganz: int = 0,
	nach: str | None = None,
) -> dict:
	"""Lose, Kartons oder eine ganze Palette in einen anderen Lagerort umlagern (z. B. Lagerverkauf).

	Ist an der Station ein Ziel fest eingestellt, gilt es; sonst wird eins der Umlager-Ziele gewählt.
	"""
	s = _station(station)
	_darf(s, "umlagern")
	erlaubt = {z["name"] for z in umlager_ziele(s.name)}
	ziel = nach or s.umlager_ziel
	if not ziel:
		_fehler(_("Bitte wählen, wohin umgelagert wird."))
	if ziel not in erlaubt:
		_fehler(_("Nach {0} kann an der Station {1} nicht umgelagert werden.").format(ziel, s.name))
	verkauf = _verkaufslager()
	aus_verkauf = ziel not in verkauf and s.umlager_ziel in verkauf
	positionen = _lieferpositionen(
		{
			"code": code,
			"anzahl": anzahl,
			"einheit": einheit,
			"palette": palette,
			"charge": charge,
			"ganz": cint(ganz),
		},
		aus_verkauf,
	)
	for p in positionen:
		if p["lager"] == ziel:
			_fehler(_("Los {0} liegt schon in {1}.").format(p["charge"], ziel))
	jetzt = now_datetime()
	se = frappe.get_doc(
		{
			"doctype": "Stock Entry",
			"stock_entry_type": "Material Transfer",
			"purpose": "Material Transfer",
			"company": s.company,
			"set_posting_time": 1,
			"posting_date": jetzt.date(),
			"posting_time": jetzt.time().strftime("%H:%M:%S"),
			"kt_station": s.name,
			"items": [
				_se_zeile(
					{"artikel": p["artikel"], "charge": p["charge"], "menge": p["menge"]}, p["lager"], ziel
				)
				for p in positionen
			],
		}
	)
	se.insert()
	se.submit()
	for p in positionen:
		if p["palette"]:
			paletten._bewegung(
				p["palette"], "Abgang", "Umlagerung", p["charge"], p["anzahl"], p["einheit"],
				s.name, "Stock Entry", se.name,
			)  # fmt: skip
	for nve in {p["palette"] for p in positionen if p["palette"]}:
		paletten._status_pruefen(nve)
	return {
		"buchung": se.name,
		"nach": ziel,
		"positionen": [
			{"name": p["name"], "charge": p["charge"], "anzahl": p["anzahl"], "einheit": p["einheit"]}
			for p in positionen
		],
		"hinweise": _meldungen(),
	}
