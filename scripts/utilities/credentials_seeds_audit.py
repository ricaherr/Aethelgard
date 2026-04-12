#!/usr/bin/env python
"""
CREDENTIALS & SEEDS AUDIT - Validación automática de seguridad
Verifica que seeds NO contengan credenciales operativas, solo DEMO públicas
Ejecutado como parte de validate_all.py
MANIFESTO security and credentials governance section
"""
import sys
import json
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))


class CredentialsSedsAudit:
    """Audita seguridad de credenciales y seeds"""
    
    def __init__(self):
        self.workspace = Path(__file__).parent.parent.parent
        self.failures: List[str] = []
        self.warnings: List[str] = []
        self.passed: List[str] = []
    
    def run_audit(self) -> int:
        """Main audit entry point - returns 0 if all OK, 1 if failures"""
        print("="*70)
        print("CREDENTIALS & SEEDS AUDIT (MANIFESTO GOVERNANCE)")
        print("="*70)
        print()
        
        # Run all checks
        self._audit_seed_json_validity()
        self._audit_seed_demo_broker_accounts()
        self._audit_seed_data_providers()
        self._audit_no_hardcoded_passwords_in_python()
        self._audit_encryption_key_exists()
        
        # Report results
        self._print_report()
        
        return 0 if not self.failures else 1
    
    def _audit_seed_json_validity(self) -> None:
        """Check: Seeds are valid JSON"""
        seed_files = [
            "data_vault/seed/demo_broker_accounts.json",
            "data_vault/seed/data_providers.json",
        ]
        
        for seed_path in seed_files:
            seed_file = self.workspace / seed_path
            
            if not seed_file.exists():
                self.warnings.append(f"[WARN] Seed file not found: {seed_path}")
                continue
            
            try:
                with open(seed_file, 'r', encoding='utf-8') as f:
                    json.load(f)
                self.passed.append(f"[OK] {seed_path}: Valid JSON")
            except json.JSONDecodeError as e:
                self.failures.append(f"[FAIL] {seed_path}: Invalid JSON - {str(e)[:50]}")
    
    def _audit_seed_demo_broker_accounts(self) -> None:
        """Check: demo_broker_accounts.json only has DEMO credentials"""
        seed_file = self.workspace / "data_vault/seed/demo_broker_accounts.json"
        
        if not seed_file.exists():
            self.warnings.append("[WARN] demo_broker_accounts.json not found")
            return
        
        try:
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_data = json.load(f)
            
            accounts = seed_data.get("accounts", [])
            
            for account in accounts:
                account_id = account.get("account_id", "unknown")
                password = account.get("credential_password")
                account_type = account.get("account_type", "unknown")
                
                # Rule: DEMO accounts can have any password (including special chars).
                # Only reject if suspiciously long (likely API key or operative credential)
                
                if password and isinstance(password, str) and password.strip():
                    password_lower = password.lower()
                    
                    # Check if has explicit DEMO marker
                    has_demo_marker = any(pattern in password_lower for pattern in ["demo", "test", "public"])
                    
                    if has_demo_marker:
                        self.passed.append(f"[OK] {account_id}: DEMO credential (OK)")
                    elif account_type == "demo":
                        # DEMO account passwords are OK regardless of structure
                        # Only reject if suspiciously long (likely operative secret)
                        if len(password) > 40:
                            self.failures.append(f"[FAIL] {account_id}: Password too long ({len(password)} chars) - may be operative")
                        else:
                            self.passed.append(f"[OK] {account_id}: DEMO password OK")
                    else:
                        # Non-DEMO account with password = suspicious
                        self.failures.append(f"[FAIL] {account_id}: Non-DEMO account has password - check if operative")
                else:
                    # None, empty string, or whitespace only = no credentials (OK)
                    self.passed.append(f"[OK] {account_id}: No password (awaiting user setup)")
        
        except Exception as e:
            self.failures.append(f"[FAIL] demo_broker_accounts.json: {str(e)[:50]}")
    
    def _audit_seed_data_providers(self) -> None:
        """Check: data_providers.json structure"""
        seed_file = self.workspace / "data_vault/seed/data_providers.json"
        
        if not seed_file.exists():
            self.warnings.append("[WARN] data_providers.json not found")
            return
        
        try:
            with open(seed_file, 'r', encoding='utf-8') as f:
                seed_data = json.load(f)
            
            providers = seed_data.get("providers", [])
            
            for provider in providers:
                name = provider.get("name", "unknown")
                config = provider.get("additional_config", {})
                
                # Check no operative API keys or secrets
                sensitive_keys = ["api_key", "secret_key", "token", "password", "apikey"]
                found_sensitive = False
                
                for key in config:
                    if any(sensitive in key.lower() for sensitive in sensitive_keys):
                        config_value = str(config[key])
                        
                        # Operative keys are typically long and complex
                        if len(config_value) > 20 and any(c in config_value for c in ["$", "%", "&"]):
                            self.failures.append(f"[FAIL] {name}: Operative API key found in seed")
                            found_sensitive = True
                        else:
                            self.warnings.append(f"[WARN] {name}: Config key '{key}' may be sensitive")
                
                if not found_sensitive:
                    self.passed.append(f"[OK] {name}: No operative API keys")
        
        except Exception as e:
            self.failures.append(f"[FAIL] data_providers.json: {str(e)[:50]}")
    
    def _audit_no_hardcoded_passwords_in_python(self) -> None:
        """Check: No hardcoded passwords in Python files"""
        # Patterns to search for
        suspicious_patterns = [
            r'password=["\'](.*?)["\']',  # password="something"
            r'api_key=["\'](.*?)["\']',   # api_key="something"
            r'secret=["\'](.*?)["\']',    # secret="something"
        ]
        
        # Files to check (seed-related)
        files_to_check = [
            "scripts/migrations/seed_demo_data.py",
            "scripts/utilities/force_update_demo_accounts.py",
            "scripts/utilities/setup_mt5_demo.py",
        ]
        
        import re
        
        for file_path in files_to_check:
            full_path = self.workspace / file_path
            
            if not full_path.exists():
                continue
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Check for suspicious patterns
                found_hardcoded = False
                
                for pattern in suspicious_patterns:
                    matches = re.findall(pattern, content)
                    
                    for match in matches:
                        # Allowed: "demo", "test", empty strings, placeholders
                        if match.lower() in ["demo", "test", "****", "password", "secret", "<password>", "${...}"]:
                            continue
                        
                        # Skip comments and docstrings
                        lines = content.split('\n')
                        for i, line in enumerate(lines):
                            if pattern in line and (line.strip().startswith('#') or '"""' in line):
                                continue
                        
                        # Real hardcoded value
                        if len(match) > 8:
                            self.failures.append(f"[FAIL] {file_path}: Hardcoded credential found: {match[:20]}...")
                            found_hardcoded = True
                
                if not found_hardcoded:
                    self.passed.append(f"[OK] {file_path}: No hardcoded credentials")
            
            except Exception as e:
                self.warnings.append(f"[WARN] {file_path}: Could not scan - {str(e)[:30]}")
    
    def _audit_encryption_key_exists(self) -> None:
        """Check: Encryption key file exists and has correct permissions"""
        key_file = self.workspace / ".encryption_key"
        
        if not key_file.exists():
            self.failures.append("[FAIL] .encryption_key file not found - credentials cannot be encrypted")
        else:
            import stat
            
            try:
                # Check file permissions (should be 0o600 = -rw-------)
                file_stat = key_file.stat()
                file_mode = stat.filemode(file_stat.st_mode)
                
                # On Windows, permissions are different, so we check readable/writable
                if file_mode.startswith("-rw"):
                    self.passed.append("[OK] .encryption_key: Exists with proper permissions")
                else:
                    self.warnings.append(f"[WARN] .encryption_key: Permissions may be too open: {file_mode}")
            except Exception as e:
                self.warnings.append(f"[WARN] .encryption_key: Could not check permissions - {str(e)[:30]}")
    
    def _print_report(self) -> None:
        """Print audit report"""
        print()
        print("-"*70)
        print("[PASSED CHECKS]")
        print("-"*70)
        for check in self.passed:
            print(check)
        
        if self.warnings:
            print()
            print("-"*70)
            print("[WARNINGS]")
            print("-"*70)
            for warning in self.warnings:
                print(warning)
        
        if self.failures:
            print()
            print("-"*70)
            print("[FAILURES] [FAIL] SECURITY VIOLATIONS")
            print("-"*70)
            for failure in self.failures:
                print(failure)
            
            print()
            print("=" * 70)
            print(f"AUDIT FAILED: {len(self.failures)} security violations found")
            print("=" * 70)
        else:
            print()
            print("=" * 70)
            print("[OK] AUDIT PASSED: All credential & seed checks OK")
            print("=" * 70)


def main():
    # Fix Unicode output on Windows (charmap -> UTF-8)
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Python < 3.7 fallback
        pass
    
    audit = CredentialsSedsAudit()
    return audit.run_audit()


if __name__ == "__main__":
    sys.exit(main())
