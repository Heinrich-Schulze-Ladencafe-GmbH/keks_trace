"""Akte: der Lebenslauf einer Palette oder eines Behälters, lesbar für das Terminal.

Quelle sind nur vorhandene Protokolle, nichts wird neu berechnet oder gespeichert:
- Palette: Paletten Bewegung (wer, wann, wo, welches Los) und Etikettendruck
- Behälter/Gebinde: Traeger Belegung (welche Charge von wann bis wann) und Etikettendruck

Dazu „Wo ist dieses Los?“ (fundstellen): alle Paletten und Behälter, auf bzw. in denen ein Los gerade liegt, je mit
kurzem Lebenslauf. Damit findet man eine Palette ohne Etikett wieder: Inhalt, Ort, Zeit und Person grenzen ein.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, format_datetime, get_fullname

from keks_trace import druckprotokoll
from keks_trace import palette as paletten

EPS = 1e-6
MAX_EREIGNISSE = 80
MAX_FUNDSTELLEN = 40
# Aufeinanderfolgende gleiche Bewegungen (z. B. 40 Karton einzeln gebucht) werden zu einer Zeile zusammengefasst,
# solange zwischen zwei Buchungen höchstens so viele Minuten liegen.
ZUSAMMEN_MINUTEN = 30


def _zeit(dt) -> str | None:
	return format_datetime(dt, "dd.MM.yy HH:mm") if dt else None


def _uhr(dt) -> str | None:
	return format_datetime(dt, "HH:mm") if dt else None


def _bis(von, bis) -> str:
	"""„-10:48“ für eine Zeitspanne; gleiche Minute: nichts; anderer Tag: mit Datum."""
	if not von or not bis or _zeit(bis) == _zeit(von):
		return ""
	return f"-{_uhr(bis)}" if _datum(bis) == _datum(von) else f" bis {_zeit(bis)}"


def _person(nutzer: str | None) -> str | None:
	return get_fullname(nutzer) if nutzer else None


def _los(charge: str) -> str:
	los = frappe.get_cached_value("Batch", charge, "kt_los") if charge else None
	return los or charge


def _bewegungen(palette: str) -> list[dict]:
	return frappe.get_all(
		"Paletten Bewegung",
		filters={"palette": palette},
		fields=[
			"richtung",
			"art",
			"charge",
			"artikel",
			"anzahl",
			"einheit",
			"gegen_palette",
			"beleg",
			"station",
			"zeitpunkt",
			"nutzer",
		],
		order_by="zeitpunkt asc, creation asc",
	)


def _zusammenfassen(zeilen: list[dict]) -> list[dict]:
	"""Gleiche Bewegungen hintereinander (Art, Richtung, Los, Einheit, Station, Person, Gegenpalette) zu einer."""
	gruppen = []
	for z in zeilen:
		g = gruppen[-1] if gruppen else None
		gleich = g and all(
			g[k] == z[k]
			for k in ("art", "richtung", "charge", "einheit", "station", "nutzer", "gegen_palette", "beleg")
		)
		if gleich and (z.zeitpunkt - g["bis"]).total_seconds() <= ZUSAMMEN_MINUTEN * 60:
			g["anzahl"] += flt(z.anzahl)
			g["bis"] = z.zeitpunkt
		else:
			gruppen.append({**z, "anzahl": flt(z.anzahl), "von": z.zeitpunkt, "bis": z.zeitpunkt})
	return gruppen


def _bewegung_text(g: dict) -> str:
	vorzeichen = "+" if g["richtung"] == "Zugang" else "-"
	text = f"{g['art']}: {vorzeichen}{paletten._n(g['anzahl'], g['einheit'])} Los {_los(g['charge'])}"
	if g.get("gegen_palette"):
		text += (" von" if g["richtung"] == "Zugang" else " auf") + f" Palette …{g['gegen_palette'][-6:]}"
	if g.get("beleg") and g["art"] in ("Lieferung", "Storno Lieferung"):
		text += f" ({g['beleg']})"
	return text


def _druck_ereignisse(**filt) -> list[dict]:
	return [
		{
			"zeit": d.zeitpunkt,
			"art": "Etikett",
			"text": _("Etikett gedruckt: {0}").format(d.grund)
			+ (f" · {d.drucker}" if d.drucker else "")
			+ (f" · {d.bemerkung}" if d.bemerkung else ""),
			"station": d.station,
			"person": _person(d.nutzer),
		}
		for d in druckprotokoll.drucke(**filt)
	]


def _sortiert(ereignisse: list[dict]) -> list[dict]:
	ereignisse.sort(key=lambda e: e["zeit"])
	ereignisse = ereignisse[-MAX_EREIGNISSE:]
	for e in ereignisse:
		e["zeit_text"] = _zeit(e["zeit"]) + _bis(e["zeit"], e.get("bis"))
		e["zeit"] = str(e["zeit"])
		e.pop("bis", None)
	return ereignisse


def palette(nve: str) -> dict:
	nr = paletten.finde(nve)
	if not nr:
		frappe.throw(_("Palette nicht gefunden."), frappe.DoesNotExistError)
	frappe.has_permission("Palette", "read", nr, throw=True)
	p = frappe.get_doc("Palette", nr)
	ereignisse = [
		{
			"zeit": p.creation,
			"art": "Angelegt",
			"text": _("Palette angelegt ({0})").format(p.typ),
			"station": p.station,
			"person": _person(p.owner),
		}
	]
	for g in _zusammenfassen(_bewegungen(nr)):
		ereignisse.append(
			{
				"zeit": g["von"],
				"bis": g["bis"],
				"art": g["art"],
				"text": _bewegung_text(g),
				"station": g["station"],
				"person": _person(g["nutzer"]),
			}
		)
	ereignisse += _druck_ereignisse(palette=nr)
	ereignisse += _zuordnungen(nr)
	i = paletten.info(nr)
	return {
		"typ": "palette",
		"nve": nr,
		"titel": _("Palette {0}").format(nr),
		"zeilen": [
			[_("Art / Status"), f"{p.typ} · {p.status}"],
			[_("Inhalt"), i["kartons"] or _("leer")],
			*([[_("Kunde"), p.kunde]] if p.kunde else []),
			*([[_("Lieferschein"), p.lieferschein]] if p.lieferschein else []),
			*_karton_zeilen(i),
			[_("Etikett"), _etikett_text(i["etikett_aktuell"], p.etikett_gedruckt)],
		],
		"ereignisse": _sortiert(ereignisse),
		# Lose auf der Palette: „Woraus besteht das?“ je Los
		"lose": [
			{"charge": x["charge"], "los": x.get("los") or x["charge"], "name": x.get("name")}
			for x in i["positionen_gesamt"]
		],
	}


def _zuordnungen(nr: str) -> list[dict]:
	"""Versandkarton auf/von einer Palette, aus Sicht des Kartons und der Palette."""
	out = []
	for z in frappe.get_all(
		"Versandkarton Zuordnung",
		or_filters={"karton": nr, "palette": nr},
		fields=["karton", "palette", "richtung", "zeitpunkt", "station", "nutzer", "beleg"],
	):
		auf = z.richtung == "Auf"
		if z.karton == nr:
			text = (_("Auf Palette …{0} gestellt") if auf else _("Von Palette …{0} genommen")).format(
				z.palette[-6:]
			)
		else:
			text = (
				_("Versandkarton …{0} aufgestellt") if auf else _("Versandkarton …{0} heruntergenommen")
			).format(z.karton[-6:])
		if z.beleg:
			text += f" ({z.beleg})"
		out.append(
			{
				"zeit": z.zeitpunkt,
				"art": "Versandkarton",
				"text": text,
				"station": z.station,
				"person": _person(z.nutzer),
			}
		)
	return out


def _karton_zeilen(i: dict) -> list[list]:
	zeilen = []
	if i.get("auf_palette"):
		zeilen.append([_("Steht auf Palette"), i["auf_palette"]])
	if i.get("versandkartons"):
		zeilen.append(
			[
				_("Versandkartons darauf"),
				", ".join(f"…{k['nve'][-6:]} ({k['inhalt']})" for k in i["versandkartons"]),
			]
		)
	paket = [
		f"{i['gewicht_kg']:g} kg".replace(".", ",") if i.get("gewicht_kg") else "",
		i.get("sendungsnummer") or "",
	]
	if any(paket):
		zeilen.append([_("Paket"), " · ".join(x for x in paket if x)])
	return zeilen


def _etikett_text(aktuell, gedruckt) -> str:
	if aktuell is None:
		return _("noch nie gedruckt")
	return _("zuletzt {0}").format(_zeit(gedruckt)) + ("" if aktuell else _(" - Inhalt seither geändert"))


def behaelter(code: str) -> dict:
	if not frappe.db.exists("Produkttraeger", code):
		frappe.throw(_("Behälter {0} nicht gefunden.").format(code), frappe.DoesNotExistError)
	frappe.has_permission("Produkttraeger", "read", code, throw=True)
	t = frappe.get_doc("Produkttraeger", code)
	ereignisse = [
		{
			"zeit": t.creation,
			"art": "Angelegt",
			"text": _("{0} angelegt").format(t.typ),
			"station": None,
			"person": _person(t.owner),
		}
	]
	for b in frappe.get_all(
		"Traeger Belegung",
		filters={"traeger": code},
		fields=["charge", "artikel", "menge_eingang", "menge_aktuell", "von", "bis", "offen"],
		order_by="von asc, creation asc",
	):
		name = frappe.get_cached_value("Item", b.artikel, "item_name") if b.artikel else ""
		text = _("Befüllt: {0} kg {1}, Charge {2}").format(
			f"{flt(b.menge_eingang, 3):g}".replace(".", ","), name, _los(b.charge)
		)
		ereignisse.append({"zeit": b.von, "art": "Befüllt", "text": text, "station": None, "person": None})
		if b.bis:
			ereignisse.append(
				{
					"zeit": b.bis,
					"art": "Geleert",
					"text": _("Geleert: Charge {0}").format(_los(b.charge)),
					"station": None,
					"person": None,
				}
			)
	if t.gereinigt_am:
		ereignisse.append(
			{
				"zeit": t.gereinigt_am,
				"art": "Gereinigt",
				"text": _("Zuletzt als gereinigt gemeldet"),
				"station": None,
				"person": None,
			}
		)
	ereignisse += _druck_ereignisse(traeger=code)
	inhalt = (
		(f"{flt(t.menge, 3):g} kg".replace(".", ",") + f" · Charge {_los(t.charge)}")
		if t.charge
		else _("leer")
	)
	return {
		"typ": "behaelter",
		"code": code,
		"titel": _("{0} {1}").format(t.typ, code),
		"zeilen": [[_("Status"), t.status], [_("Inhalt"), inhalt]],
		"lose": [
			{
				"charge": t.charge,
				"los": _los(t.charge),
				"name": frappe.get_cached_value("Item", t.artikel, "item_name") if t.artikel else None,
			}
		]
		if t.charge
		else [],
		"ereignisse": _sortiert([e for e in ereignisse if e["zeit"]]),
	}


def akte(code: str) -> dict:
	"""Akte zu einem gescannten oder abgetippten Code: Palette oder Behälter/Gebinde."""
	code = (code or "").strip()
	if paletten.finde(code):
		return palette(code)
	if frappe.db.exists("Produkttraeger", code):
		return behaelter(code)
	frappe.throw(_("Zu {0} gibt es keine Akte (nur Paletten und Behälter).").format(frappe.bold(code)))


# ---------------------------------------------------------------------------
# Wo ist dieses Los?
# ---------------------------------------------------------------------------


def _kurz(nve: str) -> dict:
	"""Lebenslauf in einer Zeile: wann und von wem gepackt, letzte Bewegung, letzter Etikettendruck."""
	zeilen = _bewegungen(nve)
	zu = [z for z in zeilen if z.richtung == "Zugang"]
	letzte = zeilen[-1] if zeilen else None
	personen = sorted({_person(z.nutzer) for z in zu if z.nutzer})
	stationen = sorted({z.station for z in zu if z.station})
	druck = druckprotokoll.drucke(palette=nve, anzahl=1)
	return {
		"gepackt": (_zeit(zu[0].zeitpunkt) + _bis(zu[0].zeitpunkt, zu[-1].zeitpunkt) if zu else None),
		"stationen": ", ".join(stationen),
		"personen": ", ".join(personen),
		"letzte": (
			f"{letzte.art} {_zeit(letzte.zeitpunkt)}" + (f" · {letzte.station}" if letzte.station else "")
		)
		if letzte
		else None,
		"letzter_druck": (f"{_zeit(druck[0].zeitpunkt)} ({druck[0].grund})" if druck else None),
	}


def fundstellen(charge: str) -> dict:
	"""Alle Stellen, an denen das Los gerade liegt: aktive Paletten, Behälter, lose Ware."""
	if not charge:
		return {"paletten": [], "behaelter": [], "lose": None}
	je_palette = defaultdict(list)
	for z in paletten.paletten_fuer([charge]):
		if z.anzahl_jetzt > EPS and z.status in paletten.AKTIV:
			je_palette[z.palette].append(z)
	liste = []
	for nve, zeilen in list(je_palette.items())[:MAX_FUNDSTELLEN]:
		i = paletten.info(nve)
		liste.append(
			{
				"nve": nve,
				"status": i["status"],
				"art": i["art"],
				"kunde": i["kunde"],
				"dieses_los": ", ".join(paletten._n(z.anzahl_jetzt, z.einheit) for z in zeilen),
				"auf_palette": i.get("auf_palette"),
				# Gesamtinhalt nur, wenn noch andere Lose auf der Palette stehen
				"inhalt": i["kartons"] if len(i["positionen"]) > 1 else None,
				"etikett_aktuell": i["etikett_aktuell"],
				**_kurz(nve),
			}
		)
	behaelter = frappe.get_all(
		"Produkttraeger",
		filters={"charge": charge},
		fields=["name as code", "typ", "status", "menge"],
		limit=MAX_FUNDSTELLEN,
	)
	artikel = frappe.db.get_value("Batch", charge, "item")
	lose = paletten.lose(charge)
	return {
		"los": _los(charge),
		"paletten": liste,
		"mehr_paletten": max(0, len(je_palette) - MAX_FUNDSTELLEN),
		"behaelter": behaelter,
		"lose": paletten.zerlegen(artikel, lose) if lose > EPS and artikel else None,
	}


# ---------------------------------------------------------------------------
# Woraus besteht das? (Rückverfolgung rückwärts als Baum)
# ---------------------------------------------------------------------------

# Obergrenzen, damit ein Los mit viel Rework (viele Generationen) die Seite nicht sprengt
MAX_KNOTEN = 300
MAX_HERKUNFT_TIEFE = 25
MAX_PRUEFUNGEN = 8
ROHSTOFF_STUFEN = ("Rohstoff", "Packmittel")


def _datum(d) -> str | None:
	return format_datetime(d, "dd.MM.yy") if d else None


def _wareneingang(charge: str) -> dict | None:
	"""Erster Zugang der Charge von außen: Wareneingang am Terminal (Stock Entry „Material Receipt“) oder
	Eingangsbeleg im Büro (Purchase Receipt). Beleg, Zeit, Lager bzw. Silo, Station, Lieferant."""
	from keks_trace import silo as silo_modul

	z = frappe.db.sql(
		"""
		select sbb.voucher_type as typ, sbb.voucher_no as beleg, sbb.posting_datetime as zeit,
			sbe.warehouse as lager, sbe.qty as menge
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		left join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		where sbe.batch_no = %s and sbb.docstatus = 1 and sbb.is_cancelled = 0 and sbe.qty > 0
			and (sbb.voucher_type = 'Purchase Receipt' or se.purpose = 'Material Receipt')
		order by sbb.posting_datetime, sbb.creation
		limit 1
		""",
		charge,
		as_dict=True,
	)
	if not z:
		return None
	z = z[0]
	lieferant = frappe.db.get_value("Batch", charge, "supplier")
	lieferschein = station = bestellung = None
	if z.typ == "Purchase Receipt":
		pr = (
			frappe.db.get_value(
				"Purchase Receipt", z.beleg, ["supplier", "supplier_delivery_note"], as_dict=True
			)
			or frappe._dict()
		)
		lieferant, lieferschein = pr.supplier or lieferant, pr.supplier_delivery_note
		bestellung = frappe.db.get_value(
			"Purchase Receipt Item", {"parent": z.beleg, "purchase_order": ["is", "set"]}, "purchase_order"
		)
	else:
		station, bestellung = frappe.db.get_value("Stock Entry", z.beleg, ["kt_station", "kt_bestellung"])
	return {
		"beleg": z.beleg,
		"zeit": _zeit(z.zeit),
		"menge": flt(z.menge, 3),
		"lager": z.lager,
		"silo": silo_modul.silo_fuer_lager(z.lager),
		"station": station,
		"lieferant": (frappe.get_cached_value("Supplier", lieferant, "supplier_name") or lieferant)
		if lieferant
		else None,
		"lieferschein": lieferschein,
		"bestellung": bestellung,
	}


def _freigabe(charge: str) -> dict | None:
	f = frappe.get_all(
		"Chargen Sperre",
		filters={"charge": charge},
		fields=["aktion", "zeitpunkt", "nutzer", "grund"],
		order_by="zeitpunkt desc, creation desc",
		limit=1,
	)
	if not f:
		return None
	f = f[0]
	return {"aktion": f.aktion, "zeit": _zeit(f.zeitpunkt), "person": _person(f.nutzer), "grund": f.grund}


def _buchung(stock_entry: str | None) -> dict | None:
	if not stock_entry:
		return None
	se = frappe.db.get_value(
		"Stock Entry",
		stock_entry,
		["name", "posting_date", "posting_time", "kt_station", "owner"],
		as_dict=True,
	)
	if not se:
		return None
	zeit = f"{_datum(se.posting_date)} {str(se.posting_time or '')[:5]}".strip()
	return {"beleg": se.name, "zeit": zeit, "station": se.kt_station, "person": _person(se.owner)}


def _pruefungen(charge: str, beleg: str | None) -> list[dict]:
	zeilen = frappe.get_all(
		"Pruefung",
		or_filters={"charge": charge, **({"beleg": beleg} if beleg else {})},
		fields=["pruefplan", "ergebnis", "wert", "einheit", "zeitpunkt", "station"],
		order_by="zeitpunkt desc",
		limit=MAX_PRUEFUNGEN,
	)
	return [
		{
			"was": z.pruefplan,
			"ergebnis": z.ergebnis,
			"wert": (
				f"{flt(z.wert, 3):g} {z.einheit or ''}".strip().replace(".", ",")
				if z.wert is not None
				else None
			),
			"zeit": _zeit(z.zeitpunkt),
			"station": z.station,
		}
		for z in zeilen
	]


def _zutaten(charge: str) -> list[dict]:
	"""Direkte Bestandteile einer Charge, je Eingangscharge zusammengefasst (mehrere Buchungen, Silo-Kante)."""
	je = {}
	for k in frappe.get_all(
		"Chargen Genealogie",
		filters={"output_batch": charge, "storniert": 0},
		fields=["input_batch", "menge", "anteil", "stock_entry", "quelle", "silo"],
		order_by="posting_date asc, creation asc",
	):
		if not k.input_batch or k.input_batch == charge:
			continue
		e = je.setdefault(
			k.input_batch,
			{
				"charge": k.input_batch,
				"menge": 0.0,
				"anteil": 0.0,
				"silo": None,
				"nur_silo": True,
				"buchung": k.stock_entry,
			},
		)
		e["menge"] += flt(k.menge)
		e["anteil"] += flt(k.anteil)
		e["silo"] = e["silo"] or k.silo
		if k.quelle != "Silo" or flt(k.menge) > EPS:
			e["nur_silo"] = False
	return list(je.values())


def _knoten(charge: str) -> dict:
	b = (
		frappe.db.get_value(
			"Batch",
			charge,
			[
				"item",
				"item_name",
				"kt_chargen_stufe",
				"kt_los",
				"manufacturing_date",
				"kt_backtag",
				"expiry_date",
				"kt_status",
				"kt_sperrgrund",
				"kt_kennzeichen",
			],
			as_dict=True,
		)
		or frappe._dict()
	)
	n = {
		"charge": charge,
		"los": b.kt_los or None,
		"artikel": b.item,
		"name": b.item_name or b.item or charge,
		"stufe": b.kt_chargen_stufe,
		"hergestellt": _datum(b.manufacturing_date),
		"backtag": _datum(b.kt_backtag),
		"mhd": _datum(b.expiry_date),
		"gesperrt": b.kt_status == "Gesperrt",
		"sperrgrund": b.kt_sperrgrund if b.kt_status == "Gesperrt" else None,
		"kennzeichen": b.kt_kennzeichen,
	}
	if b.kt_chargen_stufe in ROHSTOFF_STUFEN:
		n["wareneingang"] = _wareneingang(charge)
		n["freigabe"] = _freigabe(charge)
	return n


def herkunft(charge: str) -> dict:
	"""Woraus besteht eine Charge bzw. ein Los: Baum über Chargen Genealogie, dazu alle Rohstoffe flach.

	Jede Charge wird nur einmal aufgeklappt (Rework kann dieselbe Charge über viele Wege enthalten);
	weitere Vorkommen tragen `wiederholt`. „Möglicherweise enthalten“ heißt: nur über die Silo-Vermischung
	(Menge 0, Quelle Silo, siehe silo.py) - lieber eine Charge zu viel als eine zu wenig.
	"""
	if not frappe.db.exists("Batch", charge):
		frappe.throw(_("Charge {0} existiert nicht.").format(charge), frappe.DoesNotExistError)
	frappe.has_permission("Batch", "read", charge, throw=True)
	gesehen: set[str] = set()
	zaehler = {"n": 0, "abgeschnitten": False}
	rohstoffe: dict[str, dict] = {}

	def bauen(c: str, tiefe: int, kante: dict | None) -> dict:
		zaehler["n"] += 1
		n = _knoten(c)
		if kante:
			n["menge"] = flt(kante["menge"], 3)
			n["moeglich"] = kante["nur_silo"]
			n["ueber_silo"] = kante["silo"]
		if n["stufe"] in ROHSTOFF_STUFEN:
			# Rohstoff: in der Liste einmal; „möglicherweise“ nur, wenn er auf keinem Weg sicher enthalten ist
			if r := rohstoffe.get(c):
				r["moeglich"] = r["moeglich"] and n.get("moeglich", False)
				n["wiederholt"] = True
			else:
				rohstoffe[c] = {**n, "moeglich": n.get("moeglich", False)}
			return n
		if c in gesehen:
			n["wiederholt"] = True
			return n
		gesehen.add(c)
		teile = _zutaten(c)
		if teile:
			n["herstellung"] = _buchung(teile[0]["buchung"])
		n["pruefungen"] = _pruefungen(c, teile[0]["buchung"] if teile else None)
		if tiefe >= MAX_HERKUNFT_TIEFE or zaehler["n"] >= MAX_KNOTEN:
			if teile:
				zaehler["abgeschnitten"] = True
				n["abgeschnitten"] = True
			return n
		n["teile"] = [bauen(t["charge"], tiefe + 1, t) for t in teile]
		return n

	baum = bauen(charge, 0, None)
	liste = sorted(
		rohstoffe.values(), key=lambda r: (r["stufe"] != "Rohstoff", r["moeglich"], r["name"], r["charge"])
	)
	return {"baum": baum, "rohstoffe": liste, "abgeschnitten": zaehler["abgeschnitten"]}
