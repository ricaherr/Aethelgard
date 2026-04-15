"""
schema.py — Public facade for database schema modules.

Re-exports all public functions from the split schema modules for
backward-compatible imports. Direct callers need not change.

Split modules:
  schema_ddl.py        — initialize_schema() DDL
  schema_migrations.py — run_migrations() ALTER TABLE
  schema_seeds.py      — seed helpers and symbol mapping bootstrap
  schema_provision.py  — provision_tenant_db(), bootstrap_tenant_template()
"""
from .schema_ddl import initialize_schema
from .schema_migrations import run_migrations
from .schema_seeds import seed_default_usr_preferences, bootstrap_symbol_mappings
from .schema_provision import provision_tenant_db, bootstrap_tenant_template

__all__ = [
    "initialize_schema",
    "run_migrations",
    "seed_default_usr_preferences",
    "bootstrap_symbol_mappings",
    "provision_tenant_db",
    "bootstrap_tenant_template",
]
