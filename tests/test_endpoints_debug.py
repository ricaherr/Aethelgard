"""
Test endpoints que generan 500 errors para ver logs
"""
import requests
import json

BASE_URL = "http://localhost:8000/api"
USERNAME = "admin@aethelgard.com"
PASSWORD = "Aethelgard2026!"

# Login para obtener cookies
session = requests.Session()
resp = session.post(
    f"{BASE_URL}/auth/login",
    data=f"username={USERNAME}&password={PASSWORD}",
    headers={"Content-Type": "application/x-www-form-urlencoded"}
)
print(f"Login: {resp.status_code}")

# Test 1: predator-radar
print("\n[1] Testing /analysis/predator-radar")
resp = session.get(f"{BASE_URL}/analysis/predator-radar?symbol=EURUSD&timeframe=M5")
print(f"Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Error: {resp.text[:200]}")

# Test 2: usr_signals
print("\n[2] Testing /usr_signals")
resp = session.get(f"{BASE_URL}/usr_signals?limit=10")
print(f"Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Error: {resp.text[:200]}")

# Test 3: heatmap
print("\n[3] Testing /analysis/heatmap")
resp = session.get(f"{BASE_URL}/analysis/heatmap")
print(f"Status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Error: {resp.text[:200]}")
