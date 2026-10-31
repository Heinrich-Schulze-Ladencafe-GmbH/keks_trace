"""Paletten mit NVE (SSCC): Kartons und Beutel aus Fertigware-Losen.

Die Palette ist ein logischer Träger im Fertiglager. Ihr Inhalt ergibt sich ausschließlich aus
den unveränderbaren Paletten-Bewegungen (Zugang/Abgang je Los und Einheit). Lagerbestand bleibt
in ERPNext je Charge geführt; diese Datei sorgt dafür, dass beides zusammenpasst:

- Auf Paletten kann nie mehr stehen, als vom Los am Lager ist.
- Ein Lieferschein nimmt Ware entweder von einer Palette (Feld „Palette“ an der Position)
  oder aus losen Kartons, die auf keiner Palette stehen.
- Eine Fertigung, deren Los schon auf einer Palette steht, kann nicht storniert werden.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.model.naming import getseries
from frappe.utils import cint, flt, formatdate, getdate, now_datetime

from keks_trace.utils import artikel_stufe

EPS = 1e-6
# Nummernkreis für eingeschränkte Verwendung (GS1 „02“): taugt zum Testen, nie für Kunden.
TEST_BASISNUMMER = "0200000"
AKTIV = ("Offen", "Geschlossen")


class PalettenFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, PalettenFehler, title=_("Palette"))


# ---------------------------------------------------------------------------
# Einheiten (Karton, Beutel, kg)
# ---------------------------------------------------------------------------


# Einheiten, die nur zum Rechnen und Anzeigen dienen (nicht zum Zählen am Packtisch)
NUR_ANZEIGE = ("Palette", "Lage")


def einheiten(artikel: str, alle: bool = False) -> list[dict]:
	"""Zähleinheiten eines Artikels mit Umrechnung in die Lagereinheit, größte zuerst.

	Palette und Lage nur mit alle=True (Aufträge in Paletten, Anzeige); gezählt wird in Karton/Beutel.
	"""
	lager_einheit = frappe.get_cached_value("Item", artikel, "stock_uom")
	liste = [
		{"einheit": u.uom, "faktor": flt(u.conversion_factor)}
		for u in frappe.get_cached_doc("Item", artikel).uoms
		if u.uom != lager_einheit and flt(u.conversion_factor) > EPS and (alle or u.uom not in NUR_ANZEIGE)
	]
	liste.sort(key=lambda e: -e["faktor"])
	liste.append({"einheit": lager_einheit, "faktor": 1.0})
	return liste


def faktor(artikel: str, einheit: str | None) -> float:
	if not einheit:
		return 1.0
	for e in einheiten(artikel, alle=True):
		if e["einheit"] == einheit:
			return e["faktor"]
	_fehler(_("Einheit {0} ist für {1} nicht eingerichtet.").format(einheit, artikel))


def zerlegen(artikel: str, menge: float) -> str:
	"""Menge (Lagereinheit) als „3 Paletten + 5 Karton“; Reste in der kleinsten Zähleinheit."""
	menge = flt(menge, 6)
	stufen = [e for e in einheiten(artikel, alle=True) if e["einheit"] != "Lage"]
	if menge <= EPS:
		zaehl = [e["einheit"] for e in stufen if e["einheit"] not in NUR_ANZEIGE]
		return "0 " + ANZEIGE.get(zaehl[0], zaehl[0])
	teile = []
	for i, e in enumerate(stufen):
		letzte = i == len(stufen) - 1 or (stufen[i + 1]["faktor"] == 1 and e["faktor"] != 1)
		if letzte:
			n = round(menge / e["faktor"], 2)
			if n >= 0.05:  # Rundungsreste (z. B. 0,0002 kg) nicht anzeigen
				teile.append(_n(n, e["einheit"]))
			break
		n = int(menge / e["faktor"] + 1e-6)
		if n:
			teile.append(_n(n, e["einheit"]))
			menge = flt(menge - n * e["faktor"], 6)
		if menge <= 1e-6:
			break
	if not teile:
		erste = next(e["einheit"] for e in stufen if e["einheit"] not in NUR_ANZEIGE)
		return "0 " + ANZEIGE.get(erste, erste)
	return " + ".join(teile)


ANZEIGE = {"Nos": "Stk", "Kg": "kg"}


def _n(n, einheit):
	mehrzahl = {"Palette": "Paletten", "Lage": "Lagen"}
	einheit = ANZEIGE.get(einheit, einheit)
	text = f"{flt(n, 3):,.3f}".rstrip("0").rstrip(".").replace(",", "_").replace(".", ",").replace("_", ".")
	return f"{text} {mehrzahl.get(einheit, einheit) if flt(n) != 1 else einheit}"


def fuellung(palette: str, pos=None) -> dict | None:
	"""Wie voll ist die Palette? Anteil je Artikel nach „Palette“-Umrechnung am Artikel."""
	pos = inhalt(palette) if pos is None else pos
	anteil, ohne = 0.0, False
	for x in pos:
		f = next((e["faktor"] for e in einheiten(x["artikel"], alle=True) if e["einheit"] == "Palette"), None)
		if not f:
			ohne = True
			continue
		anteil += x["menge"] / f
	if ohne or not pos:
		return None
	artikel = {x["artikel"] for x in pos}
	text = None
	if len(artikel) == 1:
		a = next(iter(artikel))
		karton = faktor(a, "Karton") if any(e["einheit"] == "Karton" for e in einheiten(a)) else None
		voll = faktor(a, "Palette")
		if karton:
			text = f"{flt(sum(x['menge'] for x in pos) / karton, 2):g} von {flt(voll / karton, 2):g} Karton"
	return {"anteil": flt(anteil, 4), "voll": anteil >= 1 - 1e-6, "ueber": anteil > 1 + 1e-6, "text": text}


# ---------------------------------------------------------------------------
# NVE / SSCC
# ---------------------------------------------------------------------------


def pruefziffer(ziffern: str) -> int:
	"""GS1-Prüfziffer (Modulo 10, Gewichte 3/1 von rechts)."""
	summe = sum(int(z) * (3 if i % 2 == 0 else 1) for i, z in enumerate(reversed(ziffern)))
	return (10 - summe % 10) % 10


def nve_neu() -> tuple[str, bool]:
	"""Nächste NVE (18 Ziffern). Gibt (NVE, ist_test) zurück."""
	e = frappe.get_cached_doc("Keks Trace Einstellungen")
	basis = "".join(c for c in (e.get("gs1_basisnummer") or "") if c.isdigit())
	test = not basis
	if test:
		basis = TEST_BASISNUMMER
	if not 7 <= len(basis) <= 10:
		_fehler(_("Die GS1-Basisnummer muss 7 bis 10 Ziffern haben."))
	reserve = str(cint(e.get("nve_reserveziffer") if e.get("nve_reserveziffer") is not None else 3) % 10)
	stellen = 16 - len(basis)
	laufend = getseries(f"KT-NVE-{reserve}{basis}-", stellen)
	koerper = f"{reserve}{basis}{laufend}"
	if len(koerper) != 17:
		_fehler(_("Nummernkreis für NVE ist erschöpft."))
	return koerper + str(pruefziffer(koerper)), test


def nve_aus_scan(code: str) -> str:
	"""Gescannte NVE normalisieren: GS1-Präfix ]C1, (00) bzw. 00 entfernen."""
	c = (code or "").strip().replace("\x1d", "")
	for p in ("]C1", "]c1"):
		if c.startswith(p):
			c = c[len(p) :]
	c = c.replace("(", "").replace(")", "")
	if len(c) == 20 and c.startswith("00") and c.isdigit():
		c = c[2:]
	return c


def finde(code: str) -> str | None:
	nve = nve_aus_scan(code)
	return nve if nve and frappe.db.exists("Palette", nve) else None


# ---------------------------------------------------------------------------
# Inhalt
# ---------------------------------------------------------------------------


def inhalt(palette: str) -> list[dict]:
	"""Aktueller Inhalt je Los und Einheit."""
	zeilen = frappe.db.sql(
		"""
		select charge, artikel, einheit,
			sum(if(richtung = 'Zugang', anzahl, -anzahl)) as anzahl,
			sum(if(richtung = 'Zugang', menge, -menge)) as menge
		from `tabPaletten Bewegung`
		where palette = %s
		group by charge, artikel, einheit
		order by min(zeitpunkt), charge
		""",
		palette,
		as_dict=True,
	)
	ergebnis = []
	for z in zeilen:
		if flt(z.anzahl) <= EPS:
			continue
		b = frappe.db.get_value("Batch", z.charge, ["expiry_date", "kt_status"], as_dict=True) or {}
		ergebnis.append(
			{
				"charge": z.charge,
				"artikel": z.artikel,
				"name": frappe.get_cached_value("Item", z.artikel, "item_name"),
				"einheit": z.einheit,
				"anzahl": flt(z.anzahl, 3),
				"anzahl_text": f"{flt(z.anzahl, 3):g}".replace(".", ","),
				"menge": flt(z.menge, 3),
				"mhd": formatdate(b.get("expiry_date")) if b.get("expiry_date") else None,
				"mhd_datum": b.get("expiry_date"),
				"gesperrt": b.get("kt_status") == "Gesperrt",
			}
		)
	return ergebnis


def auf_paletten(charge: str, ohne_beleg: str | None = None) -> float:
	"""Menge (Lagereinheit) eines Loses, die aktuell auf Paletten steht."""
	bedingung = "and ifnull(beleg, '') != %(ohne)s" if ohne_beleg else ""
	return flt(
		frappe.db.sql(
			f"""
			select sum(if(richtung = 'Zugang', menge, -menge)) from `tabPaletten Bewegung`
			where charge = %(charge)s {bedingung}
			""",
			{"charge": charge, "ohne": ohne_beleg},
		)[0][0]
	)


def lagerbestand(charge: str) -> float:
	return flt(
		frappe.db.sql(
			"""
			select sum(sbe.qty) from `tabSerial and Batch Entry` sbe
			join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
			where sbe.batch_no = %s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			""",
			charge,
		)[0][0]
	)


def lose(charge: str) -> float:
	"""Menge eines Loses am Lager, die auf keiner Palette steht."""
	return flt(lagerbestand(charge) - auf_paletten(charge), 6)


def info(palette: str) -> dict:
	p = frappe.get_doc("Palette", palette)
	pos = inhalt(palette)
	return {
		"nve": p.name,
		"art": p.typ,
		"status": p.status,
		"kunde": p.kunde,
		"lieferschein": p.lieferschein,
		"test": bool(p.test_nve),
		"positionen": pos,
		"kartons": _summe_text(pos),
		"menge": flt(sum(x["menge"] for x in pos), 3),
		"fuellung": fuellung(palette, pos),
	}


def _summe_text(pos):
	je = defaultdict(float)
	for x in pos:
		je[x["einheit"]] += x["anzahl"]
	return ", ".join(f"{flt(n, 3):g} {e}".replace(".", ",") for e, n in je.items())


# ---------------------------------------------------------------------------
# Bewegungen
# ---------------------------------------------------------------------------


def _bewegung(
	palette, richtung, art, charge, anzahl, einheit, station=None, beleg_typ=None, beleg=None, gegen=None
):
	artikel = frappe.db.get_value("Batch", charge, "item")
	frappe.get_doc(
		{
			"doctype": "Paletten Bewegung",
			"palette": palette,
			"richtung": richtung,
			"art": art,
			"charge": charge,
			"artikel": artikel,
			"anzahl": flt(anzahl, 6),
			"einheit": einheit,
			"menge": flt(flt(anzahl) * faktor(artikel, einheit), 6),
			"gegen_palette": gegen,
			"station": station,
			"beleg_typ": beleg_typ,
			"beleg": beleg,
			"zeitpunkt": now_datetime(),
			"nutzer": frappe.session.user,
		}
	).insert(ignore_permissions=True)


def _status_pruefen(palette):
	p = frappe.get_doc("Palette", palette)
	if not inhalt(palette) and p.status in AKTIV:
		frappe.db.set_value("Palette", palette, "status", "Leer")


def anlegen(typ: str = "Lagerpalette", station: str | None = None, kunde: str | None = None) -> str:
	nve, test = nve_neu()
	frappe.get_doc(
		{
			"doctype": "Palette",
			"nve": nve,
			"typ": typ,
			"status": "Offen",
			"station": station,
			"kunde": kunde,
			"test_nve": 1 if test else 0,
		}
	).insert(ignore_permissions=True)
	return nve


def _offen(palette):
	status = frappe.db.get_value("Palette", palette, "status")
	if status is None:
		_fehler(_("Palette {0} gibt es nicht.").format(palette))
	if status == "Leer":
		frappe.db.set_value("Palette", palette, "status", "Offen")
	elif status != "Offen":
		_fehler(_("Palette {0} ist {1}. Erst wieder öffnen.").format(palette, status.lower()))


def beladen(
	palette, charge, anzahl, einheit, station=None, art="Beladen", beleg_typ=None, beleg=None
) -> dict:
	"""Lose Kartons eines Loses auf eine Palette."""
	artikel = frappe.db.get_value("Batch", charge, "item")
	if not artikel:
		_fehler(_("Charge {0} gibt es nicht.").format(charge))
	if artikel_stufe(artikel) != "Fertigware":
		_fehler(_("Auf Paletten kommt nur Fertigware, nicht {0}.").format(artikel))
	anzahl = flt(anzahl)
	if anzahl <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	_offen(palette)
	menge = anzahl * faktor(artikel, einheit)
	frei = lose(charge)
	if menge > frei + 1e-4:
		_fehler(
			_("Von Los {0} sind nur noch {1} {2} lose (nicht auf einer Palette).").format(
				charge, _anzahl_text(artikel, frei, einheit), einheit
			)
		)
	_bewegung(palette, "Zugang", art, charge, anzahl, einheit, station, beleg_typ, beleg)
	i = info(palette)
	_hinweis_fuellung(i)
	return i


def _hinweis_fuellung(i):
	f = i.get("fuellung")
	if not f:
		return
	if f["ueber"]:
		frappe.msgprint(
			_("Palette {0} ist überladen ({1} %). Bitte Kartons auf eine neue Palette.").format(
				i["nve"], round(f["anteil"] * 100)
			),
			indicator="orange",
			alert=True,
		)
	elif f["voll"]:
		frappe.msgprint(
			_("Palette {0} ist voll. Schließen, Etikett anbringen, neue Palette beginnen.").format(i["nve"]),
			indicator="green",
			alert=True,
		)


def _anzahl_text(artikel, menge, einheit):
	return f"{flt(menge / faktor(artikel, einheit), 3):g}"


def _position(palette, charge, einheit):
	for x in inhalt(palette):
		if x["charge"] == charge and x["einheit"] == einheit:
			return x
	return None


def umpacken(von, nach, charge, anzahl, einheit, station=None) -> dict:
	"""Kartons von einer Palette auf eine andere (Anbrechen, Kommissionieren)."""
	if von == nach:
		_fehler(_("Quelle und Ziel sind dieselbe Palette."))
	anzahl = flt(anzahl)
	pos = _position(von, charge, einheit)
	if not pos or anzahl > pos["anzahl"] + EPS:
		_fehler(
			_("Auf Palette {0} sind von Los {1} nur {2} {3}.").format(
				von, charge, flt(pos["anzahl"], 3) if pos else 0, einheit
			)
		)
	if anzahl <= EPS:
		_fehler(_("Bitte eine Anzahl größer 0 eingeben."))
	if frappe.db.get_value("Palette", von, "status") not in AKTIV:
		_fehler(_("Palette {0} ist nicht mehr im Lager.").format(von))
	_offen(nach)
	_bewegung(von, "Abgang", "Umpacken", charge, anzahl, einheit, station, gegen=nach)
	_bewegung(nach, "Zugang", "Umpacken", charge, anzahl, einheit, station, gegen=von)
	_status_pruefen(von)
	i = info(nach)
	_hinweis_fuellung(i)
	return i


def schliessen(palette) -> dict:
	if frappe.db.get_value("Palette", palette, "status") == "Offen":
		frappe.db.set_value("Palette", palette, "status", "Geschlossen" if inhalt(palette) else "Leer")
	return info(palette)


def oeffnen(palette) -> dict:
	if frappe.db.get_value("Palette", palette, "status") in ("Geschlossen", "Leer"):
		frappe.db.set_value("Palette", palette, "status", "Offen")
	return info(palette)


@frappe.whitelist()
def korrektur(palette: str, charge: str, anzahl: float, einheit: str, richtung: str, grund: str) -> dict:
	"""Inhalt einer Palette nach Zählung korrigieren (nur Lagerleitung/QS)."""
	if not set(frappe.get_roles()) & {"Stock Manager", "Quality Manager", "System Manager"}:
		frappe.throw(_("Nur Lagerleitung oder QS darf Paletten korrigieren."), frappe.PermissionError)
	if not grund:
		_fehler(_("Bitte einen Grund angeben."))
	if richtung == "Zugang":
		beladen(palette, charge, anzahl, einheit, art="Korrektur")
	else:
		pos = _position(palette, charge, einheit)
		if not pos or flt(anzahl) > pos["anzahl"] + EPS:
			_fehler(_("So viel ist nicht auf der Palette."))
		_bewegung(palette, "Abgang", "Korrektur", charge, anzahl, einheit)
		_status_pruefen(palette)
	frappe.get_doc("Palette", palette).add_comment("Comment", _("Korrektur: {0}").format(grund))
	return info(palette)


# ---------------------------------------------------------------------------
# Hooks: Lieferschein und Storno
# ---------------------------------------------------------------------------


def pruefe_lieferung(doc, method=None):
	"""Positionen mit Palette: so viel muss drauf sein. Ohne Palette: so viel muss lose da sein."""
	if doc.get("is_return"):
		return
	von_palette, lose_bedarf = defaultdict(float), defaultdict(float)
	for r in doc.items:
		if not r.batch_no:
			continue
		menge = flt(r.qty) * (flt(r.conversion_factor) or 1)
		if r.get("kt_palette"):
			status = frappe.db.get_value("Palette", r.kt_palette, "status")
			if status not in AKTIV:
				_fehler(_("Palette {0} ist {1}.").format(r.kt_palette, (status or "unbekannt").lower()))
			anzahl, einheit = _gezaehlt(r)
			von_palette[(r.kt_palette, r.batch_no, einheit)] += anzahl
		elif artikel_stufe(r.item_code) == "Fertigware":
			lose_bedarf[r.batch_no] += menge

	for (palette, charge, einheit), anzahl in von_palette.items():
		pos = _position(palette, charge, einheit)
		if not pos or anzahl > pos["anzahl"] + EPS:
			_fehler(
				_("Auf Palette {0} sind von Los {1} nur {2} {3}, geliefert werden sollen {4}.").format(
					palette, charge, flt(pos["anzahl"], 3) if pos else 0, einheit, flt(anzahl, 3)
				)
			)
	for charge, menge in lose_bedarf.items():
		frei = flt(lagerbestand(charge) - auf_paletten(charge, ohne_beleg=doc.name))
		if menge > frei + 1e-4:
			paletten = frappe.db.sql_list(
				"""select distinct palette from `tabPaletten Bewegung` where charge = %s""", charge
			)
			paletten = [p for p in paletten if _position_charge(p, charge)]
			if not paletten:
				_fehler(_("Von Los {0} sind nur {1} am Lager.").format(charge, flt(frei, 3)))
			_fehler(
				_(
					"Von Los {0} sind nur {1} lose am Lager, der Rest steht auf Palette {2}. Bitte die Palette angeben."
				).format(charge, flt(frei, 3), ", ".join(paletten) or "-")
			)


def _gezaehlt(r):
	"""Am Terminal gezählte Anzahl und Einheit einer Lieferscheinposition (sonst Menge/Einheit der Zeile)."""
	if r.get("kt_einheit") and flt(r.get("kt_anzahl")):
		return flt(r.kt_anzahl), r.kt_einheit
	return flt(r.qty), r.uom


def _position_charge(palette, charge):
	return any(x["charge"] == charge for x in inhalt(palette))


def lieferung_on_submit(doc, method=None):
	if doc.get("is_return"):
		return
	betroffen = set()
	for r in doc.items:
		if r.get("kt_palette") and r.batch_no:
			anzahl, einheit = _gezaehlt(r)
			_bewegung(
				r.kt_palette, "Abgang", "Lieferung", r.batch_no, anzahl, einheit,
				doc.get("kt_station"), "Delivery Note", doc.name,
			)  # fmt: skip
			betroffen.add(r.kt_palette)
	for palette in betroffen:
		if not inhalt(palette):
			frappe.db.set_value(
				"Palette",
				palette,
				{"status": "Versendet", "lieferschein": doc.name, "kunde": doc.customer},
			)


def lieferung_on_cancel(doc, method=None):
	bewegungen = frappe.get_all(
		"Paletten Bewegung",
		filters={"beleg_typ": "Delivery Note", "beleg": doc.name, "art": "Lieferung"},
		fields=["palette", "charge", "anzahl", "einheit"],
	)
	for b in bewegungen:
		_bewegung(
			b.palette, "Zugang", "Storno Lieferung", b.charge, b.anzahl, b.einheit,
			beleg_typ="Delivery Note", beleg=doc.name,
		)  # fmt: skip
	for palette in {b.palette for b in bewegungen}:
		if frappe.db.get_value("Palette", palette, "status") in ("Versendet", "Leer"):
			frappe.db.set_value("Palette", palette, {"status": "Geschlossen", "lieferschein": None})


def se_before_cancel(doc, method=None):
	"""Eine Fertigung kann nicht storniert werden, solange ihr Los auf einer Palette steht."""
	for r in doc.items:
		charge = r.batch_no or _charge_aus_bundle(r)
		if not (r.t_warehouse and charge):
			continue
		auf = auf_paletten(charge)
		if auf > EPS and lagerbestand(charge) - flt(r.transfer_qty or r.qty) < auf - 1e-4:
			paletten = sorted(
				{
					b.palette
					for b in frappe.get_all(
						"Paletten Bewegung", filters={"charge": charge}, fields=["palette"]
					)
					if _position_charge(b.palette, charge)
				}
			)
			_fehler(
				_("Los {0} steht auf Palette {1}. Erst von der Palette nehmen, dann stornieren.").format(
					charge, ", ".join(paletten)
				)
			)


def _charge_aus_bundle(r):
	if not r.get("serial_and_batch_bundle"):
		return None
	return frappe.db.get_value("Serial and Batch Entry", {"parent": r.serial_and_batch_bundle}, "batch_no")


# ---------------------------------------------------------------------------
# Rückverfolgung und Etikett
# ---------------------------------------------------------------------------


def paletten_fuer(chargen) -> list[dict]:
	"""Alle Paletten, auf denen eines der Lose stand oder steht."""
	chargen = list(chargen)
	if not chargen:
		return []
	zeilen = frappe.db.sql(
		"""
		select b.charge, b.palette, p.status, p.kunde, p.lieferschein,
			sum(if(b.richtung = 'Zugang', b.anzahl, -b.anzahl)) as anzahl_jetzt, b.einheit
		from `tabPaletten Bewegung` b join `tabPalette` p on p.name = b.palette
		where b.charge in %(c)s
		group by b.charge, b.palette, b.einheit
		order by b.charge, b.palette
		""",
		{"c": tuple(chargen)},
		as_dict=True,
	)
	for z in zeilen:
		z["anzahl_jetzt"] = max(flt(z.anzahl_jetzt, 3), 0)
	return zeilen


def _yymmdd(datum):
	return getdate(datum).strftime("%y%m%d") if datum else None


def etikett(nve: str) -> dict:
	"""Daten für das GS1-Paletten-Etikett."""
	i = info(nve)
	e = frappe.get_cached_doc("Keks Trace Einstellungen")
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	daten = {
		**i,
		"absender": e.get("absender") or company or "",
		"datum": formatdate(now_datetime()),
		"barcode_sscc": "00" + nve,
		"text_sscc": f"(00) {nve}",
		"inhalt_barcode": None,
		"inhalt_text": None,
	}
	pos = i["positionen"]
	# Bio nur, wenn alles auf der Palette Bio ist (Artikel verspricht es und das Los trägt es)
	from keks_trace import kennzeichnung as kz

	if pos and all(
		kz.BIO in kz.artikel_kennzeichen(p["artikel"])
		and kz.BIO in kz.charge_kennzeichen(p["charge"], p["artikel"])
		for p in pos
	):
		daten["bio"] = True
		daten["oeko_nr"] = e.get("oeko_kontrollnummer")
	# Sortenreine Palette (ein Los, eine Einheit): GTIN, Anzahl, MHD, Charge als zweiter Strichcode
	if len(pos) == 1:
		p = pos[0]
		gtin = frappe.db.get_value(
			"Item Barcode", {"parent": p["artikel"], "uom": p["einheit"]}, "barcode"
		) or frappe.db.get_value("Item Barcode", {"parent": p["artikel"]}, "barcode")
		if gtin and gtin.isdigit() and len(gtin) in (8, 12, 13, 14) and float(p["anzahl"]).is_integer():
			gtin14 = gtin.zfill(14)
			mhd = _yymmdd(p["mhd_datum"])
			anzahl = str(int(p["anzahl"]))
			fnc1 = "Ï"  # FNC1 in JsBarcode
			los = p["charge"] if len(p["charge"]) <= 20 else None  # GS1 (10) max. 20 Zeichen
			roh = (
				f"02{gtin14}"
				+ (f"15{mhd}" if mhd else "")
				+ f"37{anzahl}"
				+ (f"{fnc1}10{los}" if los else "")
			)
			daten["inhalt_barcode"] = roh
			daten["inhalt_text"] = (
				f"(02) {gtin14}"
				+ (f" (15) {mhd}" if mhd else "")
				+ f" (37) {anzahl}"
				+ (f" (10) {los}" if los else "")
			)
			daten["gtin"] = gtin14
	return daten
