import asyncio
import logging
from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
from data_vault.storage import StorageManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ConnectivityHealth")

async def check_health():
    logger.info("Starting Aethelgard Connectivity Health Audit...")
    
    storage = StorageManager()
    orchestrator = ConnectivityOrchestrator(storage=storage)
    orchestrator.set_storage(storage)
    
    # Give some time for background threads if any
    await asyncio.sleep(1)
    
    report = orchestrator.get_status_report()
    
    print("\n" + "="*60)
    print(f"{'PROVIDER':<15} | {'STATUS':<15} | {'DATA':<5} | {'EXEC':<5} | {'LATENCY'}")
    print("-" * 60)
    
    for pid, info in report.items():
        data_tag = "YES" if info.get('supports_data') else "NO"
        exec_tag = "YES" if info.get('supports_exec') else "NO"
        status = info.get('status', 'OFFLINE')
        latency = f"{info.get('latency', 0):.2f}ms"
        
        print(f"{pid:<15} | {status:<15} | {data_tag:<5} | {exec_tag:<5} | {latency}")
        
        # Simulated Pulse Check if ONLINE
        if status == "ONLINE":
            connector = orchestrator.get_connector(pid)
            if connector:
                try:
                    is_avail = connector.is_available()
                    logger.info(f"[{pid}] Pulse check: {'SUCCESS' if is_avail else 'FAILED'}")
                except Exception as e:
                    logger.error(f"[{pid}] Error during pulse check: {e}")
                    
    print("="*60 + "\n")
    logger.info("Connectivity Health Audit Complete.")

if __name__ == "__main__":
    asyncio.run(check_health())
