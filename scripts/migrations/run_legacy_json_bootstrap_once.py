"""
Run legacy JSON -> DB migration once, manually.

Use only for controlled transition scenarios.
"""
from data_vault.storage import StorageManager


def main() -> None:
    storage = StorageManager()
    storage.run_legacy_json_bootstrap_once()
    print("Legacy JSON bootstrap executed (manual one-shot).")


if __name__ == "__main__":
    main()
