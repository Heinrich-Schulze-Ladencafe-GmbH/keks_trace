"""Bio (EU-Öko-Verordnung 2018/848) und V-Label (vegan / vegetarisch).

Die Kennzeichen hängen an der Charge (Feld „Kennzeichen“, z. B. „Bio, Vegan“ oder „keine“):

- Wareneingang: vom Artikel. Bio nur von einem Lieferanten mit gültigem Öko-Zertifikat,
  sonst wird die Annahme als Bio verweigert.
- Herstellen / Umpacken (Rework): die neue Charge bekommt ein Kennzeichen nur, wenn ALLE
  Eingänge es tragen. Packmittel zählen nicht. Für Bio zählen auch Zutaten, die in Bio-Produkten
  erlaubt sind (Haken „in Bio erlaubt“: Wasser, Salz, Backtriebmittel …), es muss aber mindestens
  eine echte Bio-Zutat dabei sein. Silo-Chargen, die durch Nachfüllen noch enthalten sein können,
  zählen mit.
- Ist der Zielartikel als Bio / vegan / vegetarisch gekennzeichnet (Haken am Artikel), wird jede
  Zutat ohne dieses Kennzeichen sofort beim Scannen abgewiesen und die Buchung verweigert.
- Umstellung: wird an einer Station Bio hergestellt und war die letzte Fertigung dort
  konventionell, fragt das Terminal die Prüfpläne „Bei Umstellung auf Bio“ ab (Reinigung,
  Spülcharge). Nicht in Ordnung → nicht gebucht.

Chargen, die vor dieser Funktion entstanden sind (Feld leer), erben die Haken ihres Artikels.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

BIO, VEGAN, VEGETARISCH = "Bio", "Vegan", "Vegetarisch"
ALLE = (BIO, VEGAN, VEGETARISCH)
KEINE = "keine"
OHNE_KENNZEICHEN = ("Packmittel",)  # zählen für kein Kennzeichen


class KennzeichenFehler(frappe.ValidationError):
	pass


def _fehler(text):
	frappe.throw(text, KennzeichenFehler, title=_("Bio / V-Label"))


# ---------------------------------------------------------------------------
# Kennzeichen lesen
# ---------------------------------------------------------------------------


def artikel_kennzeichen(artikel: str) -> set[str]:
	"""Was der Artikel verspricht (Haken am Artikel)."""
	i = (
		frappe.get_cached_value("Item", artikel, ["kt_bio", "kt_vegan", "kt_vegetarisch"], as_dict=True)
		or frappe._dict()
	)
	k = set()
	if i.kt_bio:
		k.add(BIO)
	if i.kt_vegan:
		k |= {VEGAN, VEGETARISCH}
	elif i.kt_vegetarisch:
		k.add(VEGETARISCH)
	return k


def _parse(text) -> set[str]:
	return {t.strip() for t in (text or "").split(",") if t.strip() in ALLE}


def text(kennzeichen) -> str:
	return ", ".join(k for k in ALLE if k in kennzeichen) or KEINE


def charge_kennzeichen(charge: str, artikel: str | None = None) -> set[str]:
	wert, item = frappe.db.get_value("Batch", charge, ["kt_kennzeichen", "item"]) or (None, artikel)
	if wert:
		return _parse(wert)
	return artikel_kennzeichen(artikel or item)


def _bio_erlaubt(artikel) -> bool:
	return bool(frappe.get_cached_value("Item", artikel, "kt_bio_erlaubt"))


def _zaehlt(artikel) -> bool:
	return frappe.get_cached_value("Item", artikel, "kt_chargen_stufe") not in OHNE_KENNZEICHEN


def wirksam(charge, artikel) -> set[str]:
	"""Kennzeichen, die eine Zutat für das Ergebnis mitbringt (Bio-erlaubte Zutaten zählen als Bio)."""
	k = charge_kennzeichen(charge, artikel)
	if _bio_erlaubt(artikel):
		k.add(BIO)
	return k


def fehlt(kennzeichen_ziel: set[str], charge, artikel) -> list[str]:
	if not _zaehlt(artikel):
		return []
	k = wirksam(charge, artikel)
	return [x for x in ALLE if x in kennzeichen_ziel and x not in k]


def pruefe_zutat(ziel: str, charge: str, artikel: str, silo: str | None = None):
	"""Sofortprüfung am Terminal: passt die Zutat zum Kennzeichen des Zielartikels?"""
	verlangt = artikel_kennzeichen(ziel)
	if not verlangt:
		return
	f = fehlt(verlangt, charge, artikel)
	if f:
		name = frappe.get_cached_value("Item", artikel, "item_name")
		zielname = frappe.get_cached_value("Item", ziel, "item_name")
		wo = _(" im {0}").format(silo) if silo else ""
		_fehler(
			_("{0} ist {1}, aber {2} (Charge {3}{4}) ist nicht {1}. Bitte passende Ware nehmen.").format(
				frappe.bold(zielname), " / ".join(f), name, charge, wo
			)
		)


# ---------------------------------------------------------------------------
# Hooks an der Lagerbuchung
# ---------------------------------------------------------------------------


def _eingaenge_mit_silo(doc):
	from keks_trace.silo import vermischung
	from keks_trace.utils import eingangs_zeilen, zeilen_chargen

	ein = [(c, r.item_code, m, None) for r in eingangs_zeilen(doc) for c, m in zeilen_chargen(r)]
	ein += [(c, i, 0, s) for c, i, s in vermischung(doc, [(c, i, m) for c, i, m, _s in ein])]
	return ein


def pruefe_stock_entry(doc):
	"""before_validate: Fertigung/Umpacken in einen gekennzeichneten Artikel nur mit passenden Zutaten."""
	from keks_trace.utils import ausgangs_zeilen

	if doc.purpose == "Material Receipt":
		for r in doc.items:
			if r.t_warehouse and BIO in artikel_kennzeichen(r.item_code):
				lieferant = r.get("batch_no") and frappe.db.get_value("Batch", r.batch_no, "supplier")
				pruefe_bio_lieferant(lieferant, r.item_code)
		return
	if doc.purpose not in ("Manufacture", "Repack"):
		return
	ziele = {r.item_code for r in ausgangs_zeilen(doc)}
	verlangt = set().union(*[artikel_kennzeichen(z) for z in ziele]) if ziele else set()
	if not verlangt:
		return
	for charge, artikel, _menge, silo in _eingaenge_mit_silo(doc):
		f = fehlt(verlangt, charge, artikel)
		if f:
			name = frappe.get_cached_value("Item", artikel, "item_name")
			zusatz = _(" Sie kann durch Nachfüllen noch im {0} sein.").format(silo) if silo else ""
			_fehler(
				_("Das Ergebnis soll {0} sein, aber {1} (Charge {2}) ist es nicht.{3}").format(
					" / ".join(f), name, charge, zusatz
				)
			)


def on_submit(doc, method=None):
	"""Kennzeichen der neuen Chargen setzen (und beim Wareneingang festhalten)."""
	from keks_trace.utils import ausgangs_zeilen, zeilen_chargen

	if doc.purpose == "Material Receipt":
		for r in doc.items:
			for c, _m in zeilen_chargen(r) if r.t_warehouse else []:
				if not frappe.db.get_value("Batch", c, "kt_kennzeichen"):
					frappe.db.set_value("Batch", c, "kt_kennzeichen", text(artikel_kennzeichen(r.item_code)))
		return
	if doc.purpose not in ("Manufacture", "Repack"):
		return
	ein = [(c, i) for c, i, _m, _s in _eingaenge_mit_silo(doc) if _zaehlt(i)]
	if not ein:
		return
	gemeinsam = set(ALLE)
	echt_bio = False
	for c, i in ein:
		gemeinsam &= wirksam(c, i)
		echt_bio = echt_bio or BIO in charge_kennzeichen(c, i)
	if not echt_bio:
		gemeinsam.discard(BIO)
	for r in ausgangs_zeilen(doc):
		for c, _m in zeilen_chargen(r):
			vorher = frappe.db.get_value("Batch", c, "kt_kennzeichen")
			# Tages-Los: mehrere Verpackungen in dieselbe Charge, es gilt die Schnittmenge
			k = gemeinsam & _parse(vorher) if vorher and _hat_fruehere_ausgaenge(c, doc.name) else gemeinsam
			frappe.db.set_value("Batch", c, "kt_kennzeichen", text(k))


def _hat_fruehere_ausgaenge(charge, beleg) -> bool:
	return bool(
		frappe.db.sql(
			"""select 1 from `tabSerial and Batch Entry` sbe
			join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
			where sbe.batch_no = %s and sbe.qty > 0 and sbb.voucher_no != %s
				and sbb.docstatus = 1 and sbb.is_cancelled = 0 limit 1""",
			(charge, beleg),
		)
	)


# ---------------------------------------------------------------------------
# Lieferant mit Öko-Zertifikat
# ---------------------------------------------------------------------------


def bio_lieferant_status(lieferant: str | None) -> dict:
	if not lieferant:
		return {"ok": False, "grund": _("kein Lieferant angegeben")}
	s = frappe.db.get_value(
		"Supplier", lieferant, ["kt_bio_kontrollstelle", "kt_bio_gueltig_bis"], as_dict=True
	)
	if not s or not s.kt_bio_kontrollstelle:
		return {"ok": False, "grund": _("{0} hat kein Öko-Zertifikat hinterlegt").format(lieferant)}
	if not s.kt_bio_gueltig_bis or getdate(s.kt_bio_gueltig_bis) < getdate(nowdate()):
		return {
			"ok": False,
			"grund": _("Öko-Zertifikat von {0} ist abgelaufen ({1})").format(
				lieferant, s.kt_bio_gueltig_bis or "-"
			),
		}
	return {"ok": True, "kontrollstelle": s.kt_bio_kontrollstelle, "gueltig_bis": s.kt_bio_gueltig_bis}


def pruefe_bio_lieferant(lieferant, artikel):
	st = bio_lieferant_status(lieferant)
	if not st["ok"]:
		_fehler(
			_("{0} ist Bio: Annahme nur von einem Lieferanten mit gültigem Öko-Zertifikat ({1}).").format(
				frappe.get_cached_value("Item", artikel, "item_name"), st["grund"]
			)
		)


def pruefe_einkauf(doc, method=None):
	"""Purchase Receipt (Büro): Bio-Artikel nur von zertifizierten Lieferanten."""
	for r in doc.get("items"):
		if BIO in artikel_kennzeichen(r.item_code):
			pruefe_bio_lieferant(doc.supplier, r.item_code)


def einkauf_on_submit(doc, method=None):
	from keks_trace.utils import zeilen_chargen

	for r in doc.items:
		for c, _m in zeilen_chargen(r):
			if not frappe.db.get_value("Batch", c, "kt_kennzeichen"):
				frappe.db.set_value("Batch", c, "kt_kennzeichen", text(artikel_kennzeichen(r.item_code)))


# ---------------------------------------------------------------------------
# Umstellung konventionell -> Bio an einer Station
# ---------------------------------------------------------------------------


def letzte_fertigung_bio(station: str) -> bool | None:
	"""Kennzeichen der letzten an der Station hergestellten Charge: True = Bio, None = noch nichts."""
	z = frappe.db.sql(
		"""
		select ifnull(nullif(sed.batch_no, ''), sbe.batch_no) as charge, sed.item_code
		from `tabStock Entry` se
		join `tabStock Entry Detail` sed on sed.parent = se.name
		left join `tabSerial and Batch Entry` sbe on sbe.parent = sed.serial_and_batch_bundle
		where se.docstatus = 1 and se.kt_station = %s and se.purpose = 'Manufacture'
			and ifnull(sed.t_warehouse, '') != '' and sed.is_finished_item = 1
		order by se.posting_date desc, se.posting_time desc, se.creation desc
		limit 1
		""",
		station,
		as_dict=True,
	)
	if not z or not z[0].charge:
		return None
	return BIO in charge_kennzeichen(z[0].charge, z[0].item_code)


def umstellung_noetig(station: str, ziel: str) -> bool:
	return BIO in artikel_kennzeichen(ziel) and letzte_fertigung_bio(station) is False


# ---------------------------------------------------------------------------
# Bio-Mengenabgleich (für die Öko-Kontrolle)
# ---------------------------------------------------------------------------

SPALTEN_ABGLEICH = (
	"anfang",
	"wareneingang",
	"hergestellt",
	"verbraucht",
	"ausgeliefert",
	"lagerverkauf",
	"entsorgt",
	"sonstiges",
	"ende",
)


def bio_chargen() -> list[dict]:
	"""Alle Chargen mit Kennzeichen Bio (gesetzt oder geerbt vom Artikel)."""
	return [
		b
		for b in frappe.db.sql(
			"""select b.name, b.item, b.kt_kennzeichen, i.item_name, i.stock_uom, i.kt_chargen_stufe
			from `tabBatch` b join `tabItem` i on i.name = b.item
			where b.kt_kennzeichen like '%%Bio%%' or (ifnull(b.kt_kennzeichen, '') = '' and i.kt_bio = 1)""",
			as_dict=True,
		)
	]


def bio_abgleich(von, bis) -> list[dict]:
	"""Je Bio-Artikel: Bestand am Anfang, Zu- und Abgänge im Zeitraum, Bestand am Ende."""
	from keks_trace.bilanz import _kategorie

	von, bis = getdate(von), getdate(bis)
	chargen = {b.name: b for b in bio_chargen()}
	if not chargen:
		return []
	zeilen = frappe.db.sql(
		"""
		select sbe.batch_no, sbe.qty, sbb.voucher_type, sbb.voucher_no, date(sbb.posting_datetime) as tag,
			se.purpose, se.stock_entry_type, dn.is_return as dn_return
		from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sbb on sbb.name = sbe.parent
		left join `tabStock Entry` se on sbb.voucher_type = 'Stock Entry' and se.name = sbb.voucher_no
		left join `tabDelivery Note` dn on sbb.voucher_type = 'Delivery Note' and dn.name = sbb.voucher_no
		where sbe.batch_no in %(c)s and sbb.is_cancelled = 0 and sbb.docstatus = 1
			and date(sbb.posting_datetime) <= %(bis)s
		""",
		{"c": tuple(chargen), "bis": bis},
		as_dict=True,
	)
	spalte = {
		"Wareneingang": "wareneingang",
		"Retoure": "wareneingang",
		"Hergestellt": "hergestellt",
		"Verbraucht in Produktion": "verbraucht",
		"Zu Rework umgefüllt": "verbraucht",
		"Ausgeliefert": "ausgeliefert",
		"Lagerverkauf (Endverbraucher)": "lagerverkauf",
		"Ausgebucht / entsorgt": "entsorgt",
		"Silo-Differenz (Leermeldung)": "entsorgt",
	}
	summe = defaultdict(lambda: defaultdict(float))
	for z in zeilen:
		b = chargen[z.batch_no]
		menge = flt(z.qty)
		kat = _kategorie(z, menge, set())
		if kat == "Umlagerung":
			continue  # bleibt im Betrieb
		s = summe[b.item]
		if getdate(z.tag) < von:
			s["anfang"] += menge
			continue
		s[spalte.get(kat, "sonstiges")] += menge
	ergebnis = []
	for artikel, s in summe.items():
		b = next(x for x in chargen.values() if x.item == artikel)
		ende = s["anfang"] + sum(s[k] for k in SPALTEN_ABGLEICH[1:-1])
		zeile = {
			"artikel": artikel,
			"artikelname": b.item_name,
			"stufe": b.kt_chargen_stufe,
			"einheit": b.stock_uom,
			**{k: flt(s[k], 3) for k in SPALTEN_ABGLEICH[:-1]},
			"ende": flt(ende, 3),
		}
		# Abgänge positiv zeigen
		for k in ("verbraucht", "ausgeliefert", "lagerverkauf", "entsorgt"):
			zeile[k] = flt(-zeile[k], 3)
		ergebnis.append(zeile)
	reihenfolge = {"Rohstoff": 0, "Halbfabrikat": 1, "Grundteig": 2, "Teig veredelt": 3, "Rework": 4}
	return sorted(ergebnis, key=lambda z: (reihenfolge.get(z["stufe"], 9), z["artikelname"]))
