"""Demo E-Rechnung: Stammdaten für eu_einvoice und eine Rechnung aus einem Lieferschein.

Nur Testdaten (fiktive Adressen, Beispiel-IBAN, Steuernummern aus den Tests von eu_einvoice).

    bench --site keks.localhost execute keks_trace.demo_erechnung.einrichten
    bench --site keks.localhost execute keks_trace.demo_erechnung.rechnung --kwargs "{'lieferschein': 'MAT-DN-…'}"
"""

import os

import frappe
from frappe.utils import add_days, nowdate

from keks_trace.utils import demo_commit

FIRMA = "Keks Test GmbH"
KUERZEL = "KTG"
KUNDE = "KT Demo Handel"
ZAHLUNGSART = "Überweisung"
ZAHLUNGSBEDINGUNG = "Überweisung 30 Tage"
BANK = "Demo Hausbank"
IBAN = "DE02120300000000202051"  # Beispiel-IBAN mit gültiger Prüfziffer
BIC = "BYLADEM1001"
STEUER_7 = "7 % - KTG"
STEUER_VORLAGE = "Lieferung oder sonstige Leistung im Inland - KTG"

# ERPNext-Einheit → UN/ECE Rec 20/21 (BT-130)
EINHEITEN = {"Kg": "KGM", "Nos": "H87", "Stk": "H87", "Karton": "XCT", "Beutel": "XBG", "Palette": "XPX"}
CODELISTE_EINHEIT = "urn:cef.eu:names:identifier:Unit"
CODELISTE_ZAHLUNG = "urn:cef.eu:names:identifier:Payment"


def _code(codeliste, code, doctype, name):
	"""Ordnet einen Datensatz (z. B. UOM „Kg“) einem Code der Codeliste zu (applies_to)."""
	from erpnext.edi.doctype.code_list.code_list import resolve_code_list

	liste = resolve_code_list(codeliste)
	cc = frappe.get_doc(
		"Common Code", frappe.db.get_value("Common Code", {"code_list": liste, "common_code": code})
	)
	if not any(z.link_doctype == doctype and z.link_name == name for z in cc.applies_to):
		cc.append("applies_to", {"link_doctype": doctype, "link_name": name})
		cc.save(ignore_permissions=True)


def _adresse(titel, link_doctype, link_name, **felder):
	name = frappe.db.get_value("Address", {"address_title": titel})
	if name:
		return name
	doc = frappe.get_doc(
		{"doctype": "Address", "address_title": titel, "address_type": "Billing", "country": "Germany", **felder,
		 "links": [{"link_doctype": link_doctype, "link_name": link_name}]}
	).insert(ignore_permissions=True)  # fmt: skip
	return doc.name


def _kontakt(vorname, nachname, email, telefon, link_doctype, link_name):
	name = frappe.db.get_value("Contact", {"email_id": email})
	if name:
		return name
	c = frappe.get_doc({"doctype": "Contact", "first_name": vorname, "last_name": nachname})
	c.append("email_ids", {"email_id": email, "is_primary": 1})
	c.append("phone_nos", {"phone": telefon, "is_primary_phone": 1})
	c.append("links", {"link_doctype": link_doctype, "link_name": link_name})
	return c.insert(ignore_permissions=True).name


def einrichten():
	"""Alles, was eu_einvoice für eine gültige XRechnung braucht (EN 16931, BR-DE-*)."""
	frappe.db.set_value(
		"Company",
		FIRMA,
		{"tax_id": "DE123456789", "email": "rechnung@keks-test.example", "phone_no": "+49 30 1234567"},
	)
	_adresse(
		"Keks Test GmbH", "Company", FIRMA, address_line1="Backstraße 1", city="Musterstadt", pincode="12345",
		is_your_company_address=1, email_id="rechnung@keks-test.example",
	)  # fmt: skip
	_kontakt("Erika", "Muster", "buchhaltung@keks-test.example", "+49 30 1234568", "Company", FIRMA)

	kunde = frappe.get_doc("Customer", KUNDE)
	kunde.tax_id = "DE987654321"
	kunde.buyer_reference = kunde.buyer_reference or "Bestellung per E-Mail"
	kunde.save(ignore_permissions=True)
	_adresse(
		"KT Demo Handel", "Customer", KUNDE, address_line1="Handelsweg 7", city="Beispielhausen", pincode="54321",
		email_id="einkauf@demo-handel.example",
	)  # fmt: skip
	_kontakt("Max", "Einkauf", "einkauf@demo-handel.example", "+49 40 7654321", "Customer", KUNDE)

	# Bank: GL-Konto, Bankkonto mit IBAN, Zahlungsart Überweisung (Code 58 = SEPA-Überweisung)
	konto = f"Hausbank - {KUERZEL}"
	if not frappe.db.exists("Account", konto):
		frappe.get_doc(
			{"doctype": "Account", "account_name": "Hausbank",
			 "parent_account": frappe.db.get_value("Account", {"company": FIRMA, "account_type": "Bank", "is_group": 1}),
			 "company": FIRMA, "account_type": "Bank", "account_currency": "EUR"}
		).insert(ignore_permissions=True)  # fmt: skip
	if not frappe.db.exists("Bank", BANK):
		frappe.get_doc({"doctype": "Bank", "bank_name": BANK, "swift_number": BIC}).insert(
			ignore_permissions=True
		)
	if not frappe.db.exists("Bank Account", {"account": konto}):
		frappe.get_doc(
			{"doctype": "Bank Account", "account_name": "Geschäftskonto", "bank": BANK, "account": konto,
			 "company": FIRMA, "is_company_account": 1, "iban": IBAN}
		).insert(ignore_permissions=True)  # fmt: skip
	if not frappe.db.exists("Mode of Payment", ZAHLUNGSART):
		frappe.get_doc(
			{"doctype": "Mode of Payment", "mode_of_payment": ZAHLUNGSART, "type": "Bank",
			 "accounts": [{"company": FIRMA, "default_account": konto}]}
		).insert(ignore_permissions=True)  # fmt: skip
	_code(CODELISTE_ZAHLUNG, "58", "Mode of Payment", ZAHLUNGSART)
	if not frappe.db.exists("Payment Terms Template", ZAHLUNGSBEDINGUNG):
		frappe.get_doc(
			{"doctype": "Payment Terms Template", "template_name": ZAHLUNGSBEDINGUNG,
			 "terms": [{"invoice_portion": 100, "credit_days": 30, "due_date_based_on": "Day(s) after invoice date",
						"mode_of_payment": ZAHLUNGSART, "description": "Zahlbar innerhalb 30 Tagen ohne Abzug"}]}
		).insert(ignore_permissions=True)  # fmt: skip
	frappe.db.set_value("Customer", KUNDE, "payment_terms", ZAHLUNGSBEDINGUNG)

	for uom, code in EINHEITEN.items():
		if frappe.db.exists("UOM", uom):
			_code(CODELISTE_EINHEIT, code, "UOM", uom)
	demo_commit()
	return "eingerichtet"


def rechnung(lieferschein=None, profil="XRECHNUNG"):
	"""Rechnung aus einem gebuchten Lieferschein von KT Demo Handel, Lebensmittel mit 7 %, buchen, XML prüfen."""
	from erpnext.controllers.accounts_controller import get_taxes_and_charges
	from erpnext.stock.doctype.delivery_note.delivery_note import make_sales_invoice
	from eu_einvoice.european_e_invoice.custom.sales_invoice import get_einvoice
	from eu_einvoice.schematron import get_validation_errors
	from eu_einvoice.utils import EInvoiceProfile

	lieferschein = (
		lieferschein
		or frappe.get_all(
			"Delivery Note",
			{"docstatus": 1, "customer": KUNDE, "per_billed": 0},
			pluck="name",
			order_by="creation desc",
		)[0]
	)
	si = make_sales_invoice(lieferschein)
	si.einvoice_profile = profil
	si.payment_terms_template = ZAHLUNGSBEDINGUNG
	si.due_date = add_days(nowdate(), 30)
	si.set("payment_schedule", [])
	si.company_contact_person = frappe.db.get_value("Contact", {"email_id": "buchhaltung@keks-test.example"})
	# Ohne Vorlage nimmt ERPNext alle Konten der Artikel-Steuervorlage (auch Vorsteuer) - daher Vorlage setzen
	si.taxes_and_charges = STEUER_VORLAGE
	si.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", STEUER_VORLAGE))
	for z in si.items:
		z.item_tax_template = STEUER_7
	si.set_missing_values()
	si.calculate_taxes_and_totals()
	si.insert(ignore_permissions=True)
	si.submit()
	xml = get_einvoice(si.name)
	pfad = frappe.get_site_path("private", "files", f"{si.name}.xml")
	with open(pfad, "wb") as f:
		f.write(xml)
	fehler, warnungen = get_validation_errors(xml.decode(), EInvoiceProfile(profil))
	if profil == "XRECHNUNG":
		f2, w2 = get_validation_errors(xml.decode(), EInvoiceProfile.EN16931)
		fehler, warnungen = fehler + f2, warnungen + w2
	demo_commit()
	return {"rechnung": si.name, "lieferschein": lieferschein, "brutto": si.grand_total, "steuer": si.total_taxes_and_charges,
			"xml": pfad, "fehler": fehler, "warnungen": warnungen}  # fmt: skip


def zugferd(rechnung, pdf=None):
	"""ZUGFeRD: PDF der Rechnung mit eingebettetem XML (PDF/A-3, braucht Ghostscript).

	Ohne `pdf` druckt ERPNext selbst (braucht ein gepatchtes wkhtmltopdf). Mit `pdf` wird ein fertiges PDF genommen
	(im Testcontainer per Chromium aus `frappe.get_print` erzeugt).
	"""
	from eu_einvoice.european_e_invoice.custom.sales_invoice import attach_xml_to_pdf
	from frappe.utils.print_format import download_pdf

	if pdf:
		with open(pdf, "rb") as f:
			inhalt = f.read()
	else:
		download_pdf("Sales Invoice", rechnung)
		inhalt = frappe.local.response.filecontent
	pfad = frappe.get_site_path("private", "files", f"{rechnung}-zugferd.pdf")
	with open(pfad, "wb") as f:
		f.write(attach_xml_to_pdf(rechnung, inhalt))
	return os.path.abspath(pfad)


def druck_html(rechnung):
	"""HTML der Rechnung (Standard-Druckformat) für ein PDF außerhalb von ERPNext."""
	pfad = frappe.get_site_path("private", "files", f"{rechnung}.html")
	with open(pfad, "w") as f:
		f.write(frappe.get_print("Sales Invoice", rechnung))
	return os.path.abspath(pfad)


LIEFERANT = "KT Demo Mühle"
BEISPIEL_EINGANG = os.path.join(os.path.dirname(__file__), "demo_daten", "eingangsrechnung_muehle.xml")


def eingang(xml=BEISPIEL_EINGANG):
	"""Eingangsrechnung (XRechnung/ZUGFeRD) einlesen: E Invoice Import → Prüfung → Eingangsrechnung (Entwurf).

	Lieferant wird über die USt-IdNr. erkannt, der Artikel über die Lieferanten-Artikelnummer (Item Supplier),
	die Einheit über den UN/ECE-Code.
	"""
	from eu_einvoice.european_e_invoice.doctype.e_invoice_import.e_invoice_import import (
		create_purchase_invoice,
	)

	frappe.db.set_value("Supplier", LIEFERANT, "tax_id", "DE111222333")
	mehl = frappe.get_doc("Item", "KT-MEHL")
	if not any(z.supplier == LIEFERANT for z in mehl.supplier_items):
		mehl.append("supplier_items", {"supplier": LIEFERANT, "supplier_part_no": "WM550"})
		mehl.save(ignore_permissions=True)

	with open(xml, "rb") as f:
		datei = frappe.get_doc(
			{"doctype": "File", "file_name": os.path.basename(xml), "is_private": 1, "content": f.read()}
		).insert(ignore_permissions=True)  # fmt: skip
	imp = frappe.get_doc({"doctype": "E Invoice Import", "einvoice": datei.file_url})
	imp.insert(ignore_permissions=True)
	for t in imp.taxes:
		t.tax_account = (
			t.tax_account or f"Abziehbare Vorsteuer {int(t.rate_applicable_percent)} % - {KUERZEL}"
		)
	imp.save(ignore_permissions=True)
	ergebnis = {
		"import": imp.name, "lieferant": imp.supplier, "firma": imp.company, "rechnungsnr": imp.id,
		"brutto": imp.grand_total, "iban": imp.payee_iban, "korrekt": imp.e_invoice_is_correct,
		"fehler": imp.validation_errors, "zeilen": [(z.item, z.uom, z.billed_quantity, z.net_rate) for z in imp.items],
	}  # fmt: skip
	imp.submit()
	pi = create_purchase_invoice(imp.name)
	for t in pi.taxes:
		t.description = t.description or f"Vorsteuer {t.rate:g} %"  # Pflichtfeld, eu_einvoice füllt es nicht
	pi.insert(ignore_permissions=True)
	demo_commit()
	ergebnis.update(eingangsrechnung=pi.name, pi_brutto=pi.grand_total, faellig=str(pi.due_date))
	return ergebnis


DATEV_FIRMA = "Keks DATEV Demo GmbH"


def _datev_firma():
	"""Eigene Demo-Firma mit SKR04 (Kontonummern). Die Testfirma hat einen Kontenplan ohne Nummern - DATEV braucht sie."""
	if not frappe.db.exists("Company", DATEV_FIRMA):
		frappe.get_doc(
			{"doctype": "Company", "company_name": DATEV_FIRMA, "abbr": "KDD", "country": "Germany",
			 "default_currency": "EUR", "create_chart_of_accounts_based_on": "Standard Template",
			 "chart_of_accounts": "SKR04 mit Kontonummern", "tax_id": "DE123456789"}
		).insert(ignore_permissions=True)  # fmt: skip
	# Die ERPNext-Vorlage SKR04 setzt als Standard 3250 (erhaltene Anzahlungen) und 3500 (sonstige Verb.) - falsch
	frappe.db.set_value(
		"Company", DATEV_FIRMA,
		{"default_receivable_account": _konto(DATEV_FIRMA, "1200"), "default_payable_account": _konto(DATEV_FIRMA, "3300")},
	)  # fmt: skip
	if not frappe.db.exists("DATEV Settings", DATEV_FIRMA):
		frappe.get_doc(
			{"doctype": "DATEV Settings", "client": DATEV_FIRMA, "client_number": "10001", "consultant_number": "1234567",
			 "account_number_length": 4, "temporary_against_account_number": "9090"}
		).insert(ignore_permissions=True)  # fmt: skip


def _konto(firma, nummer):
	return frappe.db.get_value("Account", {"company": firma, "account_number": nummer, "is_group": 0})


def datev(von=None, bis=None):
	"""Ausgangs- und Eingangsrechnung in der SKR04-Demofirma buchen und den DATEV-Export (EXTF, ZIP) erzeugen."""
	from erpnext_datev.erpnext_datev.report.datev.datev import download_datev_csv

	_datev_firma()
	heute = nowdate()
	ust7, vst7 = _konto(DATEV_FIRMA, "3801"), _konto(DATEV_FIRMA, "1401")  # USt 7 %, Vorsteuer 7 %
	erloes7, wareneingang7 = _konto(DATEV_FIRMA, "4300"), _konto(DATEV_FIRMA, "5300")
	if not frappe.db.exists("Sales Invoice", {"company": DATEV_FIRMA, "docstatus": 1}):
		si = frappe.get_doc(
			{"doctype": "Sales Invoice", "company": DATEV_FIRMA, "customer": KUNDE, "posting_date": heute,
			 "due_date": add_days(heute, 30), "currency": "EUR", "einvoice_profile": "",
			 "items": [{"item_code": "HZ-9-ICH-LIEBE-DICH", "qty": 10, "rate": 1.5, "income_account": erloes7}],
			 "taxes": [{"charge_type": "On Net Total", "account_head": ust7, "rate": 7, "description": "USt 7 %"}]}
		).insert(ignore_permissions=True)  # fmt: skip
		si.submit()
		pi = frappe.get_doc(
			{"doctype": "Purchase Invoice", "company": DATEV_FIRMA, "supplier": LIEFERANT, "posting_date": heute,
			 "bill_no": "RE-M-2026-0815", "bill_date": heute, "due_date": add_days(heute, 30), "currency": "EUR",
			 "items": [{"item_code": "KT-MEHL", "qty": 10, "rate": 1.5, "expense_account": wareneingang7}],
			 "taxes": [{"charge_type": "On Net Total", "account_head": vst7, "rate": 7, "description": "VSt 7 %",
						"category": "Total", "add_deduct_tax": "Add"}]}
		).insert(ignore_permissions=True)  # fmt: skip
		pi.submit()
	demo_commit()
	download_datev_csv({"company": DATEV_FIRMA, "from_date": von or heute, "to_date": bis or heute})
	pfad = os.path.abspath(frappe.get_site_path("private", "files", "datev-demo.zip"))
	with open(pfad, "wb") as f:
		f.write(frappe.local.response.filecontent)
	return pfad
