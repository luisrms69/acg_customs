// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.ui.form.on("ACG Order Import", {
	refresh(frm) {
		acg_render_preflight(frm);
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
			frm.add_custom_button(__("Crear Sales Orders"), () => {
				frappe.confirm(
					__("¿Crear las Sales Orders de esta importación? (una por sucursal)"),
					() => {
						frappe.call({
							method: "acg_customs.acg_customs.order_import.apply.create_sales_orders",
							args: { order_import: frm.doc.name },
							freeze: true,
							freeze_message: __("Creando Sales Orders..."),
							callback: (r) => {
								const res = r.message || {};
								frappe.show_alert({
									message: __("Sales Orders creadas: {0}", [
										(res.created || []).length,
									]),
									indicator: "green",
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
		[__("Productos resueltos"), s.products_resolved],
		[__("Productos faltantes"), join_codes(s.products_missing, "plu")],
		[__("Productos ambiguos"), join_codes(s.products_ambiguous, "plu")],
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
		${warn ? `<div style="margin-top:8px"><b>${__("Warnings")}</b><ul>${warn}</ul></div>` : ""}
		${
			errs
				? `<div style="margin-top:8px;color:#b00"><b>${__(
						"Errores"
				  )}</b><ul>${errs}</ul></div>`
				: ""
		}
	`);
}
