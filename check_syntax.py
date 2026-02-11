import sys
import py_compile

files_to_check = [
    'C:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/core_brain/position_manager.py',
    'C:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/tests/test_position_manager_regime.py',
    'C:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/data_vault/trades_db.py'
]

print("SYNTAX VALIDATION:")
all_ok = True
for f in files_to_check:
    try:
        py_compile.compile(f, doraise=True)
        print(f"✅ {f.split('/')[-1]}")
    except Exception as e:
        print(f"❌ {f.split('/')[-1]}: {e}")
        all_ok = False

sys.exit(0 if all_ok else 1)
