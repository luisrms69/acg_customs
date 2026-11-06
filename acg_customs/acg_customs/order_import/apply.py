# Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
# For license information, please see license.txt

"""Creacion de Sales Orders desde un ACG Order Import con preflight en PASS.

Reglas:
- Una Sales Order por sucursal con cantidades > 0.
- Customer desde ACG Order Provider.customer; Company desde ACG Order Provider.company
  (server-side; nunca desde parametros del cliente).
- Shipping Address desde ACG Order Branch Mapping (via resolver).
- Items/qty desde las resoluciones validadas por el preflight (qty = cantidad original).
- Idempotente por (import, external_branch_code): no recrea OVs ya registradas.
- Transaccional/fail-closed: todo en una sola transaccion; si algo falla -> rollback
  (no se hace commit intermedio y status solo pasa a Applied si todo se creo).
- Segregacion intacta: check_permission('write') sobre el import.
"""

import io

import frappe
from frappe import _

from . import parser, preflight, profiles, resolver


def _build_plan(parsed, customer):
	"""Agrupa las lineas por sucursal y resuelve address (sucursal) e item (producto).

	Devuelve {branch_code: {"address": addr, "items": {item_code: qty}}}.
	Lanza si alguna resolucion no es 'ok' (no deberia ocurrir tras un preflight PASS).
	"""
	branch_addr = {}
	for code in sorted({line["branch_code"] for line in parsed["lines"]}):
		res = resolver.resolve_branch(customer, code)
		if res["status"] != "ok":
			frappe.throw(_("Sucursal {0} no resoluble al aplicar.").format(code), frappe.ValidationError)
		branch_addr[code] = res["address"]

	item_by_plu = {}
	for plu in sorted({line["plu"] for line in parsed["lines"] if line["plu"]}):
		res = resolver.resolve_product(customer, plu)
		if res["status"] != "ok":
			frappe.throw(_("Producto PLU {0} no resoluble al aplicar.").format(plu), frappe.ValidationError)
		item_by_plu[plu] = res["item"]

	plan = {}
	for line in parsed["lines"]:
		code = line["branch_code"]
		item = item_by_plu[line["plu"]]
		entry = plan.setdefault(code, {"address": branch_addr[code], "items": {}})
		entry["items"][item] = entry["items"].get(item, 0) + line["qty"]
	return plan


PROVIDER_DIMENSION_FIELD = "acg_order_provider"  # Accounting Dimension nativa (proveedor)


def _create_sales_order(customer, company, address, items, provider, price_list):
	today = frappe.utils.nowdate()
	so = frappe.get_doc(
		{
			"doctype": "Sales Order",
			"customer": customer,
			"company": company,
			"order_type": "Sales",
			"transaction_date": today,
			"delivery_date": today,
			"shipping_address_name": address,
			# Lista de precios tomada del Customer (fuente nativa, sin hardcodear nombre).
			# ERPNext resuelve el rate desde Item Price de esta lista.
			"selling_price_list": price_list,
			PROVIDER_DIMENSION_FIELD: provider,  # identifica al proveedor (Accounting Dimension)
			"items": [
				# Sin 'rate': ERPNext lo resuelve por pricing nativo
				# (Customer.default_price_list -> Item Price). El precio NO se duplica aqui.
				{"item_code": item_code, "qty": qty, "delivery_date": today}
				for item_code, qty in sorted(items.items())
			],
		}
	)
	so.insert(ignore_permissions=True)
	return so


@frappe.whitelist()
def create_sales_orders(order_import: str) -> dict:
	"""Crea las Sales Orders de la importacion. Idempotente y transaccional."""
	doc = frappe.get_doc("ACG Order Import", order_import)
	doc.check_permission("write")  # segregacion por proveedor

	# Idempotencia: ya aplicada -> no-op
	if doc.status == "Applied":
		return {
			"status": "Applied",
			"idempotent": True,
			"created": [],
			"existing": [r.sales_order for r in doc.sales_orders],
		}
	if doc.status != "Preflight Passed":
		frappe.throw(
			_("La importacion debe estar en 'Preflight Passed' para crear Sales Orders."),
			frappe.ValidationError,
		)

	# Fail-closed: re-ejecutar preflight fresco (no confiar en el summary almacenado)
	summary = preflight.execute_preflight(doc)
	if summary["result"] != "PASS":
		frappe.throw(
			_("El preflight no esta en PASS; no se pueden crear Sales Orders."), frappe.ValidationError
		)

	customer = frappe.db.get_value("ACG Order Provider", doc.provider, "customer")
	company = frappe.db.get_value("ACG Order Provider", doc.provider, "company")
	if not customer:
		frappe.throw(_("El perfil no tiene Customer configurado."), frappe.ValidationError)
	if not company:
		frappe.throw(_("El perfil no tiene Company configurada."), frappe.ValidationError)

	# Fail-closed: la Accounting Dimension de proveedor debe estar configurada (campo en SO).
	if not frappe.get_meta("Sales Order").has_field(PROVIDER_DIMENSION_FIELD):
		frappe.throw(
			_(
				"La Accounting Dimension de proveedor (campo '{0}' en Sales Order) no esta "
				"configurada. Ejecute migrate para crearla."
			).format(PROVIDER_DIMENSION_FIELD),
			frappe.ValidationError,
		)

	# Fail-closed: el Customer debe tener lista de precios nativa (default_price_list).
	price_list = frappe.db.get_value("Customer", customer, "default_price_list")
	if not price_list:
		frappe.throw(
			_("El Customer {0} no tiene lista de precios (default_price_list) configurada.").format(customer),
			frappe.ValidationError,
		)

	# Re-parsear para construir el plan (misma fuente inmutable)
	content, _sha = preflight._load_content(doc)
	wb = io.BytesIO(content)
	import openpyxl

	spec = profiles.detect_profile(openpyxl.load_workbook(wb, data_only=True))
	parsed = parser.parse_workbook(openpyxl.load_workbook(io.BytesIO(content), data_only=True), spec)
	plan = _build_plan(parsed, customer)

	# Ledger de idempotencia por sucursal
	existing_codes = {r.external_branch_code for r in doc.sales_orders if r.external_branch_code}

	# Transaccionalidad explicita: todo o nada. Un savepoint garantiza rollback del
	# conjunto de creacion de ESTA importacion aunque el llamador no sea un request.
	savepoint = "acg_order_apply"
	frappe.db.savepoint(savepoint)
	try:
		created = []
		missing_price = []
		for code in sorted(plan):
			if code in existing_codes:
				continue
			so = _create_sales_order(
				customer, company, plan[code]["address"], plan[code]["items"], doc.provider, price_list
			)
			# Gate fail-closed de precio: tras el pricing nativo, ninguna linea puede quedar en rate 0.
			for it in so.items:
				if not it.rate:
					missing_price.append(f"{code}:{it.item_code}")
			doc.append(
				"sales_orders",
				{"sales_order": so.name, "external_branch_code": code, "address": plan[code]["address"]},
			)
			created.append(so.name)
		if missing_price:
			frappe.throw(
				_(
					"Sin precio valido en la Price List del Customer para {0} linea(s): {1}. "
					"No se crean Sales Orders con rate 0."
				).format(len(missing_price), ", ".join(missing_price[:20])),
				frappe.ValidationError,
			)
		doc.status = "Applied"
		doc.save(ignore_permissions=True)
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		raise

	return {
		"status": "Applied",
		"idempotent": False,
		"created": created,
		"existing": sorted(existing_codes),
	}
