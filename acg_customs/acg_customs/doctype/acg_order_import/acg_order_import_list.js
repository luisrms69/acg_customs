// Copyright (c) 2026, Consultoria en Negocios y Aplicaciones and contributors
// For license information, please see license.txt

frappe.listview_settings["ACG Order Import"] = {
	get_indicator(doc) {
		const map = {
			Uploaded: "gray",
			"Preflight Passed": "green",
			"Preflight Failed": "red",
			Applied: "blue",
			Error: "orange",
		};
		return [__(doc.status), map[doc.status] || "gray", "status,=," + doc.status];
	},
};
