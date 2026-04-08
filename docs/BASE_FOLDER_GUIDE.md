# Base Folder Guide

Esta carpeta (`sales-bot-platform`) es la base reusable para futuros bots.

## Carpetas activas (core)

- `app/`: stack Final Production (API pública, CRM API/UI, worker, servicios).
- `Planning/`: SalesFlowManager y piezas comerciales determinísticas del stack productivo.
- `bot_sales/`: capa multirubro/tenancy + conectores tenant-aware + runtime legacy.
- `dashboard/`: dashboard tenant-aware de operación rápida.
- `data/tenants/<slug>/`: perfil/catálogo/policies/branding por rubro.
- `scripts/`: onboarding y utilidades operativas.
- `wsgi.py`: entrypoint unificado (Final Production + extensiones multitenant).

## Runtime esperado

`wsgi.py` debe iniciar en modo final (no fallback legacy), con blueprints:

- `crm_api`
- `crm_ui`
- `dashboard`
- `storefront_tenant_api`

## Comandos de salud (obligatorios antes de usar como plantilla)

```bash
python3 scripts/doctor_base.py
python3 scripts/validate_tenant.py
python3 scripts/smoke_runtime.py
pytest -q
```

## Onboarding de nuevo bot/rubro

```bash
python3 scripts/create_tenant.py --name "Mi Negocio" --slug mi-negocio --industry generic --non-interactive
```

Esto crea tenant files y sincroniza automáticamente el tenant al CRM base.

Si queres clonar toda esta base en otra carpeta y salir ya con tenant inicial:

```bash
python3 scripts/clone_full_bot.py --destination /Users/julian/Desktop/Cerrados/bot-nuevo --with-tenant --tenant-name "Mi Negocio" --tenant-slug mi-negocio --industry generic --run-checks
```

## Nota sobre `carniceria_bot/`

`carniceria_bot/` es histórico/legacy y no es parte del runtime principal de esta base.
Se puede conservar como referencia, pero no debe usarse como fuente de verdad.
