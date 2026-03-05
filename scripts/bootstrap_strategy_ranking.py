#!/usr/bin/env python
"""
Bootstrap Script: Inicializar strategy_ranking Table
Trace_ID: BOOTSTRAP-RANKING-S007-20260305

Propósito:
- Crear 5 filas en strategy_ranking (una por estrategia READY_FOR_ENGINE)
- Excluir SESS_EXT_0001 (LOGIC_PENDING per regla § 7.2)
- Todas con execution_mode='SHADOW' (default inicial)
- Idempotente (no duplica si se ejecuta múltiples veces)

Uso:
    python scripts/bootstrap_strategy_ranking.py
    python scripts/bootstrap_strategy_ranking.py --env production
    python scripts/bootstrap_strategy_ranking.py --dry-run

Gobernanza:
- .ai_rules.md § 2: Migraciones aditivas (INSERT only)
- DEVELOPMENT_GUIDELINES § 1: DI + SSOT
- No modificar datos existentes
"""
import logging
import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Agregar paths
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager
from data_vault.tenant_factory import TenantDBFactory


# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_logging(verbose: bool = False) -> logging.Logger:
    """Configurar logging con niveles apropiados"""
    log_level = logging.DEBUG if verbose else logging.INFO
    
    logging.basicConfig(
        level=log_level,
        format='[%(asctime)s] [%(levelname)-8s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    return logging.getLogger(__name__)


# ============================================================================
# BOOTSTRAP LOGIC
# ============================================================================

class StrategyRankingBootstrap:
    """Orquestador de bootstrap para strategy_ranking tabla"""
    
    def __init__(self, storage: StorageManager, logger: logging.Logger, dry_run: bool = False):
        self.storage = storage
        self.logger = logger
        self.dry_run = dry_run
        self.stats = {
            'total_strategies': 0,
            'ready_strategies': 0,
            'logic_pending_strategies': 0,
            'created_rankings': 0,
            'skipped_existing': 0,
            'skipped_logic_pending': 0,
            'errors': 0
        }
    
    def run(self) -> bool:
        """Ejecutar bootstrap completo"""
        self.logger.info("="*80)
        self.logger.info("BOOTSTRAP: strategy_ranking Table Initialization")
        self.logger.info(f"Timestamp: {datetime.utcnow().isoformat()}Z")
        self.logger.info(f"Dry-Run: {self.dry_run}")
        self.logger.info("="*80)
        
        try:
            # 1. Cargar todas las estrategias
            self.logger.info("\n[1/3] Loading strategies from database...")
            strategies = self._load_strategies()
            
            if not strategies:
                self.logger.error("❌ No strategies found in database")
                return False
            
            self.logger.info(f"✓ Loaded {len(strategies)} strategies")
            
            # 2. Filtrar y validar
            self.logger.info("\n[2/3] Filtering READY_FOR_ENGINE strategies...")
            ready_strategies = self._filter_ready_strategies(strategies)
            
            if not ready_strategies:
                self.logger.error("❌ No READY_FOR_ENGINE strategies found")
                return False
            
            self.logger.info(f"✓ Found {len(ready_strategies)} READY_FOR_ENGINE strategies")
            self.logger.info(f"  Excluding {self.stats['logic_pending_strategies']} LOGIC_PENDING strategies")
            
            # 3. Bootstrap strategy_ranking
            self.logger.info("\n[3/3] Creating strategy_ranking entries...")
            self._bootstrap_rankings(ready_strategies)
            
            # Reporte final
            self.logger.info("\n" + "="*80)
            self.logger.info("BOOTSTRAP SUMMARY")
            self.logger.info("="*80)
            self._print_stats()
            
            # Validación post-bootstrap
            if not self.dry_run:
                self.logger.info("\n[4/3] Validating post-bootstrap state...")
                valid = self._validate_post_bootstrap()
                
                if not valid:
                    self.logger.error("❌ Post-bootstrap validation FAILED")
                    return False
                
                self.logger.info("✓ Post-bootstrap validation PASSED")
            
            self.logger.info("\n✅ BOOTSTRAP COMPLETED SUCCESSFULLY")
            return True
        
        except Exception as e:
            self.logger.error(f"❌ Bootstrap FAILED: {e}", exc_info=True)
            return False
    
    def _load_strategies(self) -> List[Dict]:
        """Cargar todas las estrategias de BD"""
        try:
            strategies = self.storage.get_all_strategies()
            
            for strat in strategies:
                if strat.get('readiness') == 'LOGIC_PENDING':
                    self.stats['logic_pending_strategies'] += 1
                else:
                    self.stats['ready_strategies'] += 1
            
            self.stats['total_strategies'] = len(strategies)
            return strategies
        
        except Exception as e:
            self.logger.error(f"Error loading strategies: {e}")
            raise
    
    def _filter_ready_strategies(self, strategies: List[Dict]) -> List[Dict]:
        """Filtrar solo las estrategias READY_FOR_ENGINE"""
        ready = []
        
        for strat in strategies:
            readiness = strat.get('readiness', 'UNKNOWN')
            class_id = strat.get('class_id', 'UNKNOWN')
            
            if readiness == 'READY_FOR_ENGINE':
                ready.append(strat)
                self.logger.debug(f"  ✓ {class_id}: {readiness}")
            
            elif readiness == 'LOGIC_PENDING':
                self.logger.debug(f"  ⊘ {class_id}: {readiness} (EXCLUDED per rule § 7.2)")
            
            else:
                self.logger.warning(f"  ? {class_id}: {readiness} (UNKNOWN state)")
        
        return ready
    
    def _bootstrap_rankings(self, strategies: List[Dict]) -> None:
        """Crear filas en strategy_ranking para cada estrategia READY_FOR_ENGINE"""
        for strat in strategies:
            strategy_id = strat.get('class_id')
            
            try:
                # Verificar si ya existe (idempotencia)
                existing = self.storage.get_strategy_ranking(strategy_id)
                
                if existing:
                    self.logger.info(f"  ⊘ {strategy_id}: Already exists (skipped)")
                    self.stats['skipped_existing'] += 1
                    continue
                
                # Crear nueva fila usando save_strategy_ranking
                if self.dry_run:
                    self.logger.info(f"  [DRY-RUN] Would create ranking for {strategy_id}")
                    self.stats['created_rankings'] += 1
                else:
                    trace_id = self.storage.save_strategy_ranking(
                        strategy_id=strategy_id,
                        ranking_data={
                            'execution_mode': 'SHADOW',  # Default initial mode
                            'profit_factor': 0.0,
                            'win_rate': 0.0,
                            'drawdown_max': 0.0,
                            'consecutive_losses': 0,
                            'total_trades': 0,
                            'completed_last_50': 0,
                            'trace_id': f"BOOTSTRAP-{datetime.utcnow().isoformat()}Z"
                        }
                    )
                    
                    self.logger.info(f"  ✓ {strategy_id}: Created with execution_mode=SHADOW (trace_id={trace_id})")
                    self.stats['created_rankings'] += 1
            
            except Exception as e:
                self.logger.error(f"  ❌ {strategy_id}: Error creating ranking: {e}")
                self.stats['errors'] += 1
    
    def _validate_post_bootstrap(self) -> bool:
        """Validar estado de BD después de bootstrap"""
        try:
            # Validación 1: Contar filas (debe haber al menos READY_FOR_ENGINE)
            all_rankings = self.storage.get_all_strategy_rankings()
            total_count = len(all_rankings)
            
            self.logger.info(f"  Total strategy_ranking entries: {total_count}")
            
            expected_count = self.stats['ready_strategies']  # Todas las READY
            if total_count < expected_count:
                self.logger.error(
                    f"  Expected at least {expected_count} entries, got {total_count}"
                )
                return False
            
            # Validación 2: Verificar SHADOW mode
            shadow_count = sum(
                1 for r in all_rankings 
                if r.get('execution_mode') == 'SHADOW'
            )
            
            self.logger.info(f"  SHADOW mode entries: {shadow_count}")
            
            if shadow_count < expected_count:
                self.logger.error(
                    f"  Expected at least {expected_count} entries in SHADOW, got {shadow_count}"
                )
                return False
            
            # Validación 3: Verificar SESS_EXT_0001 NO existe
            sess_ext_exists = any(
                r.get('strategy_id') == 'SESS_EXT_0001'
                for r in all_rankings
            )
            
            self.logger.info(f"  SESS_EXT_0001 in ranking: {sess_ext_exists}")
            
            if sess_ext_exists:
                self.logger.error("  SESS_EXT_0001 should NOT be in strategy_ranking!")
                return False
            
            return True
        
        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False
    
    def _print_stats(self) -> None:
        """Imprimir statisticas"""
        self.logger.info(f"Total Strategies Analyzed: {self.stats['total_strategies']}")
        self.logger.info(f"  - READY_FOR_ENGINE: {self.stats['ready_strategies']}")
        self.logger.info(f"  - LOGIC_PENDING: {self.stats['logic_pending_strategies']}")
        self.logger.info(f"\nBootstrap Results:")
        self.logger.info(f"  ✓ Created: {self.stats['created_rankings']}")
        self.logger.info(f"  ⊘ Skipped (already exists): {self.stats['skipped_existing']}")
        self.logger.info(f"  ❌ Errors: {self.stats['errors']}")
        
        total_processed = (
            self.stats['created_rankings'] + 
            self.stats['skipped_existing'] + 
            self.stats['errors']
        )
        self.logger.info(f"\nTotal Processed: {total_processed}/{self.stats['ready_strategies']}")


# ============================================================================
# CLI
# ============================================================================

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Bootstrap strategy_ranking table with READY_FOR_ENGINE strategies'
    )
    
    parser.add_argument(
        '--env',
        choices=['development', 'production'],
        default='development',
        help='Environment (development or production)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without actually doing it'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose logging output'
    )
    
    args = parser.parse_args()
    
    # Setup logging
    logger = setup_logging(verbose=args.verbose)
    
    logger.info(f"Environment: {args.env}")
    
    try:
        # Inicializar StorageManager
        logger.info("Initializing StorageManager...")
        storage = StorageManager()
        
        # Crear bootstrap
        bootstrap = StrategyRankingBootstrap(
            storage=storage,
            logger=logger,
            dry_run=args.dry_run
        )
        
        # Ejecutar
        success = bootstrap.run()
        
        sys.exit(0 if success else 1)
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
