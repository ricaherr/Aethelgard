# Scripts de Migración (One-Time)

Scripts de migración de base de datos y configuración. Estos scripts se ejecutan **una sola vez** durante actualizaciones del sistema.

## Scripts Disponibles

### Migraciones de Base de Datos
- `migrate_broker_schema.py` - Actualiza schema de tabla brokers
- `migrate_credentials_to_db.py` - Migra credenciales de JSON a DB encriptada
- `migrate_add_traceability.py` - Añade campos de trazabilidad a señales

### Seed de Datos
- `seed_brokers_platforms.py` - Puebla DB con brokers y plataformas iniciales

## Uso

```bash
# Desde el root del proyecto
py scripts/migrations/nombre_del_script.py
```

## ⚠️ Advertencia

Estos scripts modifican la estructura de la base de datos. **Hacer backup antes de ejecutar**.
