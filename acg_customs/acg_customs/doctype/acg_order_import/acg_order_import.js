// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.ui.form.on("ACG Order Import", {
	refresh(frm) {
		acg_render_preflight(frm);
		acg_render_reconciliation(frm);
		if (frm.is_new()) return;

		const status = frm.doc.status;

		if (["Uploaded", "Preflight Failed", "Preflight Passed"].includes(status)) {
			frm.add_custom_button(__("Ejecutar Preflight"), () => {
				frappe.call({
					method: "acg_customs.acg_customs.order_import.preflight.run_preflight",
					args: { order_import: frm.doc.name },
					freeze: true,
					freeze_message: __("Ejecutando preflight..."),
					callback: (r) => {
						const res = r.message || {};
						frappe.show_alert({
							message: __("Preflight: {0}", [res.result || "?"]),
							indicator: res.result === "PASS" ? "green" : "red",
						});
						frm.reload_doc();
					},
				});
			});
		}

		if (status === "Preflight Passed") {
			frm.add_custom_button(__("Crear Órdenes de Venta"), () => {
				frappe.confirm(
					__("¿Crear las Órdenes de Venta de esta importación? (una por sucursal)"),
					() => {
						frappe.call({
							method: "acg_customs.acg_customs.order_import.apply.create_sales_orders",
							args: { order_import: frm.doc.name },
							freeze: true,
							freeze_message: __("Creando Órdenes de Venta..."),
							callback: (r) => {
								const res = r.message || {};
								const rec = res.reconciliation || {};
								frappe.msgprint({
									title: __("Órdenes de Venta creadas"),
									indicator: "green",
									message: __(
										"Se crearon {0} Órdenes de Venta (en borrador).<br>Conciliación de totales: {1} OK, {2} con diferencia, {3} sin validar.",
										[
											(res.created || []).length,
											rec.pass || 0,
											rec.warning || 0,
											rec.sin_validar || 0,
										]
									),
								});
								frm.reload_doc();
							},
						});
					}
				);
			}).addClass("btn-primary");
		}
	},
});

function acg_render_preflight(frm) {
	const field = frm.get_field("preflight_report_html");
	if (!field || !field.$wrapper) return;
	const $w = field.$wrapper;

	if (!frm.doc.preflight_summary) {
		$w.html(`<div class="text-muted">${__("Sin preflight ejecutado todavía.")}</div>`);
		return;
	}

	let s;
	try {
		s = JSON.parse(frm.doc.preflight_summary);
	} catch (e) {
		$w.html(`<div class="text-muted">${__("Resumen no legible.")}</div>`);
		return;
	}

	const pass = s.result === "PASS";
	const badge = `<span class="indicator-pill ${
		pass ? "green" : "red"
	}">${frappe.utils.escape_html(s.result || "?")}</span>`;

	const join_codes = (arr, key) =>
		(arr || []).map((x) => frappe.utils.escape_html(String(key ? x[key] : x))).join(", ") ||
		"—";

	const rows = [
		[__("Sucursales con pedido"), s.branches_with_orders],
		[__("Sucursales resueltas"), s.branches_resolved],
		[__("Sucursales faltantes"), join_codes(s.branches_missing, "code")],
		[
			__("Columnas de sucursal en el archivo (catálogo, no el pedido)"),
			s.branch_columns_in_file,
		],
		[__("Productos resueltos"), s.products_resolved],
		[__("Productos faltantes"), join_codes(s.products_missing, "plu")],
		[__("Productos ambiguos"), join_codes(s.products_ambiguous, "plu")],
		[__("Productos sin precio vigente"), join_codes(s.products_without_price, "plu")],
		[__("Líneas"), s.product_lines],
		[__("Unidades"), s.total_units],
	];

	const tr = rows
		.map(
			([k, v]) =>
				`<tr><td style="padding:2px 14px 2px 0;color:#6c7680">${k}</td>` +
				`<td>${
					v === undefined || v === null ? "—" : frappe.utils.escape_html(String(v))
				}</td></tr>`
		)
		.join("");

	const warn = (s.warnings || []).map((w) => `<li>${frappe.utils.escape_html(w)}</li>`).join("");
	const errs = (s.structural_errors || [])
		.map((e) => `<li>${frappe.utils.escape_html(e)}</li>`)
		.join("");

	$w.html(`
		<div style="margin-bottom:8px">${__("Resultado")}: ${badge}</div>
		<table style="font-size:12px">${tr}</table>
		${warn ? `<div style="margin-top:8px"><b>${__("Advertencias")}</b><ul>${warn}</ul></div>` : ""}
		${
			errs
				? `<div style="margin-top:8px;color:#b00"><b>${__(
						"Errores"
				  )}</b><ul>${errs}</ul></div>`
				: ""
		}
	`);
}

function acg_render_reconciliation(frm) {
	const field = frm.get_field("reconciliation_html");
	if (!field || !field.$wrapper) return;
	const $w = field.$wrapper;

	const rows = frm.doc.sales_orders || [];
	if (!rows.length) {
		$w.html(`<div class="text-muted">${__("Sin Órdenes de Venta creadas todavía.")}</div>`);
		return;
	}

	const fmt = (v) =>
		v === undefined || v === null
			? "—"
			: format_currency(v, frappe.defaults.get_default("currency"));
	const pill = (st) => {
		const ind = st === "PASS" ? "green" : st === "WARNING" ? "orange" : "gray";
		return `<span class="indicator-pill ${ind}">${frappe.utils.escape_html(st || "—")}</span>`;
	};

	let nPass = 0;
	let nWarn = 0;
	let nSin = 0;
	const body = rows
		.map((r) => {
			if (r.reconciliation_status === "PASS") nPass++;
			else if (r.reconciliation_status === "WARNING") nWarn++;
			else nSin++;
			return (
				`<tr>` +
				`<td>${frappe.utils.escape_html(r.external_branch_code || "—")}</td>` +
				`<td>${frappe.utils.escape_html(r.sales_order || "—")}</td>` +
				`<td style="text-align:right">${fmt(r.excel_total)}</td>` +
				`<td style="text-align:right">${fmt(r.erp_total)}</td>` +
				`<td style="text-align:right">${fmt(r.reconciliation_diff)}</td>` +
				`<td>${pill(r.reconciliation_status)}</td>` +
				`</tr>`
			);
		})
		.join("");

	$w.html(`
		<div style="margin-bottom:6px">
			<b>${__("Conciliación de totales por sucursal")}</b>
			&nbsp; ${__("OK")}: ${nPass} · ${__("Con diferencia")}: ${nWarn} · ${__("Sin validar")}: ${nSin}
		</div>
		<table class="table table-bordered" style="font-size:12px">
			<thead><tr>
				<th>${__("Sucursal")}</th><th>${__("Orden de Venta")}</th>
				<th style="text-align:right">${__("Total Excel")}</th>
				<th style="text-align:right">${__("Total OV")}</th>
				<th style="text-align:right">${__("Diferencia")}</th>
				<th>${__("Conciliación")}</th>
			</tr></thead>
			<tbody>${body}</tbody>
		</table>
		<div class="text-muted" style="font-size:11px">${__(
			"Las OV con diferencia o sin validar permanecen en borrador; revise antes de facturar."
		)}</div>
	`);
}
