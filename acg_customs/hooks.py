app_name = "acg_customs"
app_title = "Acg Customs"
app_publisher = "Consultoria en Negocios y Aplicaciones"
app_description = "Personalizaciones para ERPNext/Frappe clientes CNAP"
app_email = "it@buzola.mx"
app_license = "mit"

# Apps
# ------------------

required_apps = ["erpnext"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "acg_customs",
# 		"logo": "/assets/acg_customs/logo.png",
# 		"title": "Acg Customs",
# 		"route": "/acg_customs",
# 		"has_permission": "acg_customs.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/acg_customs/css/acg_customs.css"
# app_include_js = "/assets/acg_customs/js/acg_customs.js"

# include js, css files in header of web template
# web_include_css = "/assets/acg_customs/css/acg_customs.css"
# web_include_js = "/assets/acg_customs/js/acg_customs.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "acg_customs/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "acg_customs/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "acg_customs.utils.jinja_methods",
# 	"filters": "acg_customs.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "acg_customs.install.before_install"
# after_install = "acg_customs.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "acg_customs.uninstall.before_uninstall"
# after_uninstall = "acg_customs.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "acg_customs.utils.before_app_install"
# after_app_install = "acg_customs.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "acg_customs.utils.before_app_uninstall"
# after_app_uninstall = "acg_customs.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "acg_customs.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "acg_customs.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["acg_customs.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"acg_customs.tasks.all"
# 	],
# 	"daily": [
# 		"acg_customs.tasks.daily"
# 	],
# 	"hourly": [
# 		"acg_customs.tasks.hourly"
# 	],
# 	"weekly": [
# 		"acg_customs.tasks.weekly"
# 	],
# 	"monthly": [
# 		"acg_customs.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "acg_customs.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "acg_customs.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "acg_customs.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "acg_customs.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["acg_customs.utils.before_request"]
# after_request = ["acg_customs.utils.after_request"]

# Job Events
# ----------
# before_job = ["acg_customs.utils.before_job"]
# after_job = ["acg_customs.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"acg_customs.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# ======================================================================
# ACG Order Import — segregacion por proveedor (server-side, fail-closed)
# ======================================================================

# Configuracion idempotente (rol de importador + proveedores base).
after_migrate = "acg_customs.setup.install.after_migrate"

# Capas 1 y 3: filtrado de lista. ANDea con las condiciones nativas (incl. File).
permission_query_conditions = {
	"ACG Order Import": "acg_customs.permissions.order_import_query_conditions",
	"File": "acg_customs.permissions.file_query_conditions",
}

# Capas 2 y 4: gate por registro. Semantica deny-only (solo puede endurecer).
has_permission = {
	"ACG Order Import": "acg_customs.permissions.order_import_has_permission",
	"File": "acg_customs.permissions.file_has_permission",
}

