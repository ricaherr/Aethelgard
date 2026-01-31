
import sqlite3
conn = sqlite3.connect('data_vault/aethelgard.db')
cursor = conn.cursor()
cursor.execute('SELECT name FROM sqlite_master WHERE type="table"')
tables = [row[0] for row in cursor.fetchall()]
print('Tablas existentes:', tables)
critical = ['brokers', 'signals', 'data_providers', 'system_state']
missing = [t for t in critical if t not in tables]
print('Tablas faltantes:', missing)
conn.close()

