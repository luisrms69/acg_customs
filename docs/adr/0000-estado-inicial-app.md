# ADR-0000: Estado inicial — acg_customs

**Fecha:** 2026-09-30
**Status:** Activo

## Contexto

App nueva creada como parte del ecosistema Buzola sobre frappe-bench-v16.
Personalizaciones para ERPNext/Frappe clientes CNAP.

## Decisiones iniciales

- Bench: frappe-bench-v16 (Frappe 16.x, ERPNext 16.x)
- Branch protegida: version-16 (estándar Frappe upstream)
- Site de desarrollo: `<dev-site>` → localhost:`<port>` (pendiente de creación)
- Site de tests: test-acg_customs.localhost (pendiente de creación)
- Apps requeridas: erpnext (`required_apps = ["erpnext"]` en hooks.py)
- GitHub: pendiente (repo remoto aún no creado)

## Notas

Documentar decisiones arquitectónicas relevantes en ADRs subsiguientes.
