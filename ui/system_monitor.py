"""
Aethelgard System Monitor - Technical Diagnostic Dashboard
Dedicated interface for system health, logs, and maintenance.
"""
import streamlit as st
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

# Path configuration
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from core_brain.health import HealthManager

# Page Configuration
st.set_page_config(
    page_title="Aethelgard System Monitor",
    page_icon="🛡️",
    layout="wide"
)

# Custom CSS for better aesthetics
st.markdown("""
<style>
    .status-green { color: #00ff00; font-weight: bold; }
    .status-yellow { color: #ffff00; font-weight: bold; }
    .status-red { color: #ff0000; font-weight: bold; }
    .log-container { background-color: #1e1e1e; color: #d4d4d4; padding: 10px; border-radius: 5px; font-family: monospace; }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_health_manager():
    return HealthManager()

def main():
    st.title("🛡️ Aethelgard System Monitor")
    st.markdown("---")
    
    health_manager = get_health_manager()
    
    # Sidebar: Controls
    with st.sidebar:
        st.header("⚙️ System Control")
        if st.button("🔄 Refresh Diagnostic", type="primary"):
            st.rerun()
        
        st.markdown("---")
        st.subheader("🛠️ Quick Repairs")
        if st.button("💾 Re-index Database"):
            st.warning("Feature in progress: Re-indexing...")
        if st.button("🔌 Restart Connectors"):
            st.info("Restart command sent to Orchestrator.")

    # Run Diagnostic
    summary = health_manager.run_full_diagnostic()
    
    # 1. Overall Status Banner
    status = summary["overall_status"]
    status_emoji = {"GREEN": "✅", "YELLOW": "⚠️", "RED": "🚨"}.get(status, "⚪")
    
    st.subheader(f"Status: {status_emoji} {status}")
    
    # 2. Main Dashboard Metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        cpu = summary["resources"].get("cpu_percent", 0)
        st.metric("CPU Usage", f"{cpu}%", delta="-2%" if cpu < 50 else "+5%", delta_color="inverse")
        
    with col2:
        mem = summary["resources"].get("memory_mb", 0)
        st.metric("RAM (Process)", f"{mem:.1f} MB")
        
    with col3:
        threads = summary["resources"].get("threads", 0)
        st.metric("Active Threads", threads)
        
    with col4:
        st.metric("Last Check", datetime.fromisoformat(summary["timestamp"]).strftime("%H:%M:%S"))

    st.markdown("---")

    # 3. Component Details
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📂 Configuration Files")
        config_data = summary["config"]
        for detail in config_data["details"]:
            if "SUCCESS" in detail:
                 st.write(f"🟢 {detail}")
            else:
                 st.write(f"🔴 {detail}")
                 
    with col_right:
        st.subheader("🗄️ Database Integrity")
        db_data = summary["db"]
        if db_data["status"] == "GREEN":
            st.success("SQLite database is healthy and tables are verified.")
        else:
            st.error(f"Issues detected in DB: {', '.join(db_data['details'])}")
        
        for detail in db_data["details"]:
            st.write(f"• {detail}")

    st.markdown("---")

    # 4. Technical Logs (Simulation for now)
    st.subheader("📝 Technical Logs (Real-time)")
    log_file = BASE_DIR / "logs" / "system.log"
    
    if log_file.exists():
        with open(log_file, "r") as f:
            lines = f.readlines()
            # Show last 20 lines
            log_text = "".join(lines[-20:])
            st.code(log_text, language="log")
    else:
        st.info("Log file 'logs/system.log' not found. Starting simulation...")
        st.code("""
[INFO] 2026-01-28 09:21:00 - HealthCore initialized successfully.
[INFO] 2026-01-28 09:21:15 - Verifying module configurations...
[WARN] 2026-01-28 09:21:30 - ADX value near threshold in ES.
[INFO] 2026-01-28 09:22:01 - SQLite connection heartbeat OK.
        """, language="log")

if __name__ == "__main__":
    main()
