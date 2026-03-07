#!/usr/bin/env python3
"""
Provider Selection Diagnostic Tool
Analyzes data provider configuration and selection logic
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager
import json
import logging

# Minimal logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def diagnose():
    """Run diagnostic on provider selection"""
    
    print("=" * 80)
    print("🔍 DATA PROVIDER SELECTION DIAGNOSTIC")
    print("=" * 80)
    print()
    
    storage = StorageManager()
    
    # Step 1: Check data_providers table
    print("📊 STEP 1: Data Providers in Database")
    print("-" * 80)
    
    try:
        providers = storage.get_data_providers()
        if not providers:
            print("❌ No providers found in database")
            return
            
        for provider in providers:
            name = provider.get('name', 'unknown')
            enabled = provider.get('enabled', False)
            priority = provider.get('priority', 50)
            requires_auth = provider.get('requires_auth', False)
            config = provider.get('config', {})
            
            # Parse config if it's a string
            if isinstance(config, str):
                try:
                    config = json.loads(config)
                except:
                    config = {}
            
            status = "✅ ENABLED" if enabled else "❌ DISABLED"
            auth_status = "🔑 Requires Auth" if requires_auth else "🔓 No Auth"
            
            print(f"\n{name.upper()}")
            print(f"  Status: {status} | Priority: {priority} | {auth_status}")
            
            # Check credentials
            if name == "mt5":
                login = config.get('login', '')
                server = config.get('server', '')
                has_password = bool(config.get('password', ''))
                
                print(f"  MT5 Config:")
                print(f"    - Login: {login if login else '❌ NOT SET'}")
                print(f"    - Server: {server if server else '❌ NOT SET'}")
                print(f"    - Password: {'✅ SET' if has_password else '❌ NOT SET'}")
                
                # Also check broker_accounts table
                print(f"  MT5 Broker Accounts:")
                all_accounts = storage.get_sys_broker_accounts()
                mt5_accounts = [a for a in all_accounts if a.get('platform_id') == 'mt5']
                if mt5_accounts:
                    for acc in mt5_accounts:
                        print(f"    - {acc.get('account_name')} (Login: {acc.get('login')})")
                        print(f"      Server: {acc.get('server')}, Enabled: {acc.get('enabled')}")
                else:
                    print(f"    - No MT5 accounts found")
                    
            elif name == "yahoo":
                print(f"  Yahoo Config: (No credentials needed)")
                
        print()
        
    except Exception as e:
        print(f"❌ Error reading providers: {e}")
        return
    
    # Step 2: Simulate get_best_provider() logic
    print("\n📌 STEP 2: Provider Selection Logic Simulation")
    print("-" * 80)
    print("Simulating DataProviderManager.get_best_provider() logic...\n")
    
    # Sort by priority (descending)
    sorted_providers = sorted(
        [p for p in providers if p.get('enabled')],
        key=lambda x: x.get('priority', 50),
        reverse=True
    )
    
    if not sorted_providers:
        print("❌ No enabled providers found!")
        return
    
    print(f"Enabled providers (sorted by priority):")
    for i, p in enumerate(sorted_providers, 1):
        name = p.get('name')
        priority = p.get('priority', 50)
        requires_auth = p.get('requires_auth', False)
        config = p.get('config', {})
        
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except:
                config = {}
        
        print(f"  {i}. {name.upper()} (priority: {priority})")
        
        # Check if would be skipped
        if requires_auth:
            if name == "mt5":
                login = config.get('login')
                server = config.get('server')
                has_creds = bool(login and server)
                if has_creds:
                    print(f"     ✅ Credentials present (login: {login}, server: {server})")
                else:
                    print(f"     ❌ WOULD BE SKIPPED (missing credentials)")
            else:
                has_api_key = bool(config.get('api_key'))
                if has_api_key:
                    print(f"     ✅ API Key present")
                else:
                    print(f"     ❌ WOULD BE SKIPPED (missing API key)")
    
    print(f"\n✅ SELECTED PROVIDER: {sorted_providers[0].get('name').upper()}")
    print(f"   (First enabled provider with valid credentials)")
    
    # Step 3: Summary
    print("\n📋 STEP 3: Summary")
    print("-" * 80)
    
    enabled_count = sum(1 for p in providers if p.get('enabled'))
    mt5_enabled = next((p for p in providers if p.get('name') == 'mt5' and p.get('enabled')), None)
    yahoo_enabled = next((p for p in providers if p.get('name') == 'yahoo' and p.get('enabled')), None)
    
    print(f"Total providers: {len(providers)}")
    print(f"Enabled providers: {enabled_count}")
    print(f"MT5: {'✅ ENABLED' if mt5_enabled else '❌ DISABLED'}")
    print(f"Yahoo: {'✅ ENABLED' if yahoo_enabled else '❌ DISABLED'}")
    
    if mt5_enabled:
        mt5_config = mt5_enabled.get('config', {})
        if isinstance(mt5_config, str):
            try:
                mt5_config = json.loads(mt5_config)
            except:
                mt5_config = {}
        
        has_creds = bool(mt5_config.get('login') and mt5_config.get('server'))
        print(f"MT5 Credentials: {'✅ CONFIGURED' if has_creds else '❌ NOT CONFIGURED'}")
        print(f"MT5 Priority: {mt5_enabled.get('priority', 50)}")
    
    if yahoo_enabled:
        print(f"Yahoo Priority: {yahoo_enabled.get('priority', 50)}")
    
    print()
    print("=" * 80)

if __name__ == '__main__':
    diagnose()
