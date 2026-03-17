# Invoice Management System

Flask-based internal application for procurement, invoice, organization, supplier, and master-data administration.

This repository is structured around a small application factory, thin HTTP route handlers, focused service modules, schema-centric SQLAlchemy models, and explicit cross-cutting packages for bootstrap, security, audit, presentation, reports, and seed data.

---

## What this project is

This system manages operational workflows around:

- procurement creation, editing, implementation, and listing
- organization setup and personnel administration
- settings and master data administration
- suppliers and service units
- user administration and authentication
- document/report generation for procurement flows
- audit logging for important mutations

The codebase follows a deliberate refactor direction:

- **`app/__init__.py` stays small** as the Flask application factory entrypoint
- **blueprints keep only HTTP boundary concerns**
- **services own orchestration and use-case logic**
- **models stay schema-centric**
- **security rules are explicit and reusable**
- **presentation helpers are separated from domain logic**

---

## Current architectural principles

### 1. Thin routes

Route modules under `app/blueprints/.../routes.py` should contain only:

- Flask decorators
- reading `request.args`, `request.form`, and uploaded files
- basic object loading at the HTTP boundary when appropriate
- calling services / use-case functions
- `render_template(...)`
- `redirect(...)`
- `flash(...)`
- `send_file(...)`

Routes should **not** own:

- business branching
- validation orchestration
- page-context assembly at scale
- reusable authorization logic
- persistence workflows
- report/domain calculations unrelated to pure HTTP response shaping

### 2. Function-first design

The codebase prefers:

- functions for focused orchestration and helpers
- classes only when state or complexity actually justifies them

This is intentional. The project does **not** adopt abstract class-heavy architecture by default.

### 3. Clear module boundaries

The target shape is:

- **Blueprints** = HTTP transport layer
- **Services** = use-case orchestration / page-context assembly / validation coordination
- **Security** = decorators, permissions, guards
- **Audit** = serialization + audit entry construction
- **Presentation** = UI/helper formatting logic
- **Models** = database schema and relationship definitions
- **Reports** = file/document generation

### 4. Conservative refactoring

The project intentionally avoids arbitrary decomposition.

A module should be refactored only when the current source of truth shows clear value in doing so. Some modules are better marked as:

- **stabilize, not decompose**

instead of being split further.

---

## Repository structure

> The following structure reflects the application code visible in the current project snapshot.

```text
app/
├── __init__.py                     # Flask application factory
├── audit/                         # Audit public surface + internal helpers
│   ├── __init__.py
│   ├── audit.py                   # legacy compatibility facade
│   ├── logging.py
│   └── serialization.py
├── blueprints/                    # HTTP entrypoints grouped by domain
│   ├── admin/
│   ├── auth/
│   ├── procurements/
│   ├── settings/
│   └── users/
├── bootstrap/                     # app wiring, hooks, blueprint registration, nav
│   ├── __init__.py
│   ├── bootstrap.py               # legacy compatibility facade
│   └── navigation.py
├── extensions/                    # Flask extension instances
│   ├── __init__.py
│   └── extensions.py              # legacy compatibility facade
├── models/                        # schema-centric SQLAlchemy model modules
│   ├── audit.py
│   ├── feedback.py
│   ├── helpers.py
│   ├── master_data.py
│   ├── organization.py
│   ├── procurement.py
│   ├── supplier.py
│   └── user.py
├── presentation/                  # UI-specific helpers
│   ├── __init__.py
│   ├── presentation.py            # legacy compatibility facade
│   └── procurement_ui.py
├── reports/                       # generated document/report logic
│   ├── award_decision_docx.py
│   └── proforma_invoice.py
├── security/                      # decorators, permissions, guards
│   ├── __init__.py
│   ├── admin_guards.py
│   ├── decorators.py
│   ├── permissions.py
│   ├── procurement_guards.py
│   └── security.py                # legacy compatibility facade
├── seed/                          # bootstrap/reference data seed helpers
│   ├── __init__.py
│   ├── defaults.py
│   ├── reference_data.py
│   └── seed.py
├── services/                      # application orchestration modules
│   ├── admin_organization_setup_service.py
│   ├── admin_personnel_service.py
│   ├── excel_imports.py
│   ├── master_data_service.py
│   ├── operation_results.py
│   ├── organization_queries.py
│   ├── organization_scope.py
│   ├── organization_service.py
│   ├── organization_validation.py
│   ├── parsing.py
│   ├── procurement_create_service.py
│   ├── procurement_edit_service.py
│   ├── procurement_implementation_service.py
│   ├── procurement_list_page_service.py
│   ├── procurement_queries.py
│   ├── procurement_reference_data.py
│   ├── procurement_related_entities_service.py
│   ├── procurement_service.py
│   ├── procurement_workflow.py
│   ├── settings_service_units_service.py
│   └── settings_suppliers_service.py
├── static/
│   └── app.css
├── templates/
│   ├── admin/
│   ├── auth/
│   ├── errors/
│   ├── procurements/
│   ├── settings/
│   └── users/
└── utils.py
```

---

## Main runtime flow

### Application startup

`app/__init__.py` is the entrypoint.

High-level flow:

1. create Flask app
2. load configuration from `config.Config`
3. delegate all wiring to `app.bootstrap.configure_app(app)`

This keeps the application factory intentionally small and predictable.

### Request flow

Normal request flow should look like this:

1. request enters a blueprint route
2. route reads HTTP input
3. route calls a focused service function
4. service coordinates validation / orchestration / persistence
5. service may call:
   - models
   - audit helpers
   - security guards
   - presentation helpers
   - reports
6. route renders or redirects

That separation is the core maintenance rule of the project.

---

## Blueprint overview

### `app/blueprints/auth`

Authentication entrypoints.

Typical responsibilities:

- login form
- logout
- initial admin bootstrap / seeding flow

Routes here should remain transport-oriented, while credential/bootstrap orchestration belongs in services.

### `app/blueprints/users`

User administration.

Typical responsibilities:

- list users
- create user
- edit user

The route layer should not own validation or persistence branching.

### `app/blueprints/settings`

Settings and master-data administration.

This blueprint includes mixed responsibilities such as:

- service units
- suppliers
- theme/settings-like pages
- feedback administration
- ALE/KAE and CPV imports/admin
- option values
- income tax rules
- withholding profiles
- committees

Because this blueprint can grow large quickly, it benefits strongly from focused service extraction.

### `app/blueprints/admin`

Administrative setup flows such as:

- organization setup
- personnel management

This area often works best with page-context/use-case services and conservative route cleanup.

### `app/blueprints/procurements`

Procurement workflow entrypoints.

This is one of the most important domains in the system and already contains focused service decomposition around:

- list pages
- create/edit flows
- implementation flow
- related child mutations
- queries / workflow helpers / reference data

Report routes should be treated conservatively unless the real source shows a strong reason to split them.

---

## Service layer overview

The current codebase already contains several useful service clusters.

### Procurement-oriented services

- `procurement_create_service.py`
- `procurement_edit_service.py`
- `procurement_implementation_service.py`
- `procurement_list_page_service.py`
- `procurement_related_entities_service.py`
- `procurement_queries.py`
- `procurement_reference_data.py`
- `procurement_workflow.py`
- `procurement_service.py` (legacy / compatibility / broader helper surface)

These modules support the rule that procurement routes should stay thin.

### Organization-oriented services

- `organization_service.py`
- `organization_queries.py`
- `organization_scope.py`
- `organization_validation.py`

These support organization setup, service-unit scoping, and related admin/settings concerns.

### Settings-oriented services

- `settings_service_units_service.py`
- `settings_suppliers_service.py`

These already show the right direction: extract settings-related orchestration away from the route layer.

### Shared/common services

- `parsing.py`
- `operation_results.py`
- `excel_imports.py`
- `master_data_service.py`

These modules should remain focused, reusable, and free from HTTP concerns.

---

## Security layer overview

The security package exists so route files do not accumulate authorization logic ad hoc.

### Main pieces

- `decorators.py` for route-facing decorators such as access enforcement
- `permissions.py` for permission rules
- `admin_guards.py` for reusable admin-specific checks
- `procurement_guards.py` for reusable procurement access/transition rules

The design goal is:

- reusable security logic lives in `app/security/...`
- routes apply guards, but do not re-implement them repeatedly

---

## Audit layer overview

The audit package is split into two focused concerns:

- `serialization.py`
  - prepares safe, serializable snapshots of model values
- `logging.py`
  - creates and adds `AuditLog` entries to the current SQLAlchemy session

Important behavior:

- audit helpers do **not** commit transactions on their own
- the caller remains responsible for transaction boundaries

This is important because audit logging must stay compatible with larger request-scoped transactions.

---

## Presentation layer overview

`app/presentation` holds helper logic that is UI-oriented but not domain logic.

Example:

- `procurement_ui.py`

This is the right place for things like:

- display formatting
- filename shaping for downloads
- small template-support helpers

It should **not** become a second service layer.

---

## Reports layer overview

`app/reports` contains document/file generation code.

Visible report modules include:

- `award_decision_docx.py`
- `proforma_invoice.py`

These should stay focused on file/report generation and avoid absorbing request orchestration.

---

## Models layer overview

Models are intentionally **schema-centric**.

Current model modules include:

- `audit.py`
- `feedback.py`
- `master_data.py`
- `organization.py`
- `procurement.py`
- `supplier.py`
- `user.py`

The guiding rule is:

- keep models focused on database structure, relationships, defaults, and modest model-local helpers
- do not push orchestration-heavy application workflows into model classes

---

## Templates

Templates are grouped by blueprint/domain:

- `templates/admin/...`
- `templates/auth/...`
- `templates/procurements/...`
- `templates/settings/...`
- `templates/users/...`
- shared base and error templates

This is the correct structure for a Flask application with domain-grouped blueprints.

---

## Legacy compatibility facades

Several packages currently expose both:

- canonical package surfaces such as `app.audit`, `app.bootstrap`, `app.extensions`, `app.presentation`, `app.security`
- legacy module files such as `audit.py`, `bootstrap.py`, `extensions.py`, `presentation.py`, `security.py`

These legacy files should be treated as **compatibility facades**, not as places for new logic.

### Rule

For new code, prefer canonical imports such as:

```python
from app.audit import log_action, serialize_model
from app.bootstrap import configure_app
from app.security import admin_required
```

Avoid introducing new imports from legacy flat compatibility modules when a canonical package import already exists.

---

## Recommended import policy

To keep the project predictable, follow these rules.

### Prefer package-level canonical imports

Use:

```python
from app.audit import log_action
from app.extensions import db, login_manager
from app.security import admin_required
```

Prefer this over legacy module paths when both exist.

### Keep route imports explicit

Blueprint routes should import only what they need:

- service functions
- decorators / guards
- specific models when object loading is unavoidable at the HTTP boundary

### Avoid circular dependencies by boundary discipline

A safe dependency direction is:

- blueprints → services / security / presentation / reports / models
- services → models / security / audit / presentation / shared services
- models → extensions / SQLAlchemy only

Try to avoid reverse dependencies such as:

- models importing blueprint code
- presentation importing route handlers
- security importing blueprint modules

---

## Refactor status summary

### Already aligned with the target direction

- `app/__init__.py` as a small application factory
- package-based cross-cutting structure (`audit`, `bootstrap`, `extensions`, `presentation`, `security`, `seed`)
- schema-centric model split
- procurement service decomposition in focused modules
- organization logic separated into multiple helper/service modules

### Areas that typically need ongoing review

- large settings/admin route modules
- import drift between canonical package surfaces and legacy compatibility facades
- oversized flat `app/services` directory as more focused modules are added

---

## Suggested next structural improvement

The current codebase already has natural clusters inside `app/services`.

A sensible future grouping would be:

```text
app/services/
├── admin/
├── organization/
├── procurement/
├── settings/
└── shared/
```

This should be done only when you are ready to update imports consistently across the project and maintain compatibility facades where needed.

The goal is **clarity**, not over-engineering.

---

## Local development

The current source snapshot clearly shows the Flask application package, but it does **not** fully show outer repository/runtime files such as all of the following:

- `requirements.txt` or `pyproject.toml`
- top-level `run.py` / `wsgi.py`
- the full `config.py`
- migration tooling/config
- test suite layout

Because those files are not fully visible in the source snapshot used for this README, the exact local setup commands may differ in your repository.

A typical Flask setup would look like:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export FLASK_APP=app:create_app
flask run
```

If your repository uses a different entrypoint, dependency manager, or environment loading mechanism, prefer the repository-specific runtime instructions.

---

## How to add new functionality correctly

### Adding a new page or flow

1. add or update the blueprint route
2. keep the route focused on HTTP concerns
3. move orchestration into a service function
4. put reusable authorization in `app/security`
5. put UI-only helpers in `app/presentation`
6. log important mutations through `app.audit`
7. keep models schema-centric

### Adding a new mutation route

Prefer this shape:

```python
@blueprint.route("/...", methods=["POST"])
@login_required
def some_action():
    result = execute_some_action(...)
    if result.ok:
        flash("Success", "success")
        return redirect(...)
    flash(result.message, "danger")
    return render_template(...)
```

### Adding a new list/detail page

Prefer this shape:

```python
@blueprint.route("/...")
@login_required
def some_page():
    context = build_some_page_context(...)
    return render_template("template.html", **context)
```

---

## Known caveats from the current source snapshot

This README is aligned to the visible `combined_project.md` snapshot.

That matters because some outer-repository files and some potential schema/runtime details are not fully visible in the provided source snapshot. As a result:

- this document is accurate for the visible application structure
- any repository-wide setup instructions not present in the snapshot may need to be adjusted in the real repo
- if a field/import/runtime contract exists in the real codebase but not in the snapshot, the real repository remains the final executable truth

---

## Maintenance rules for contributors

Before changing code, keep these rules in mind:

1. **Do not make assumptions when the current source is unclear.**
2. **Prefer extraction only when the current route/module is actually fat.**
3. **Do not split modules just to make the tree look more abstract.**
4. **Keep public import surfaces stable when possible.**
5. **Document non-obvious boundaries inside the file itself.**
6. **When in doubt, optimize for explicitness over cleverness.**

---

## Summary

This project is moving toward a clean, production-style Flask architecture with:

- a small application factory
- thin blueprint routes
- focused service orchestration
- explicit security and audit layers
- schema-centric models
- controlled compatibility surfaces during refactoring

That direction is correct.

The next quality gains come mostly from:

- keeping canonical import surfaces consistent
- continuing targeted extraction from fat route modules
- grouping service modules by domain when the team is ready to migrate imports cleanly

