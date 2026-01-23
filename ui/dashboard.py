"""
Dashboard de Control para Aethelgard
Interfaz Streamlit para monitorear el régimen de mercado, gestionar módulos y ver parámetros dinámicos
"""
import streamlit as st
import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Any
import sys
import random # Importar random para simulación de datos

# Añadir el directorio raíz al path para importar módulos
    sys.path.insert(0, str(Path(__file__).parent.parent))

from core_brain.discovery import DiscoveryEngine # Importar DiscoveryEngine
from core_brain.regime import RegimeClassifier
from core_brain.module_manager import get_module_manager, MembershipLevel
from core_brain.tuner import ParameterTuner
from core_brain.notificator import get_notifier
from data_vault.storage import StorageManager
from models.signal import MarketRegime

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración de la página
st.set_page_config(
    page_title="Aethelgard Dashboard",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializar componentes
@st.cache_resource
def get_classifier():
    """Obtiene una instancia del clasificador de régimen"""
    return RegimeClassifier()

@st.cache_resource
def get_storage():
    """Obtiene una instancia del gestor de almacenamiento"""
    return StorageManager()

@st.cache_resource
def get_tuner():
    """Obtiene una instancia del tuner de parámetros"""
    storage = get_storage()
    return ParameterTuner(storage)

def get_regime_color(regime: str) -> str:
    """Retorna un color para cada régimen"""
    color_map = {
        "TREND": "🟢",
        "RANGE": "🟡",
        "CRASH": "🔴",
        "NEUTRAL": "⚪"
    }
    return color_map.get(regime, "⚪")

def main():
    """Función principal del dashboard"""
    
    # Título
    st.title("🧠 Aethelgard - Dashboard de Control")
    st.markdown("---")
    
    # Sidebar para configuración
    with st.sidebar:
        st.header("⚙️ Configuración")

        # Selector de modo de escaneo
        scan_mode = st.selectbox(
            "Modo de Escaneo",
            options=["ECO", "STANDARD", "AGRESSIVE"],
            index=1,
            help="Perfil de escaneo (afecta uso de CPU y velocidad)"
        )

        # Selector de símbolo
        symbol = st.text_input("Símbolo", value="ES", help="Símbolo del instrumento a monitorear")

        # Selector de membresía
        membership = st.selectbox(
            "Nivel de Membresía",
            options=["basic", "premium"],
            index=0,
            help="Nivel de membresía para verificar permisos de módulos"
        )
        membership_level = MembershipLevel.BASIC if membership == "basic" else MembershipLevel.PREMIUM
        
        # Botón para recargar datos
        if st.button("🔄 Recargar Datos"):
            st.cache_resource.clear()
            st.rerun()
    
    # Obtener instancias
    classifier = get_classifier()
    storage = get_storage()
    module_manager = get_module_manager()
    tuner = get_tuner()
    
    # Tabs principales
    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Régimen en Tiempo Real",
        "🎛️ Gestión de Módulos",
        "⚙️ Parámetros Dinámicos",
        "📈 Estadísticas"
    ])
    
    # TAB 1: Régimen en Tiempo Real
    with tab1:
        st.header("Régimen de Mercado en Tiempo Real")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Entrada de Precio")
            price_input = st.number_input(
                "Precio Actual",
                value=5000.0,
                step=0.01,
                format="%.2f"
            )
            
            if st.button("🔍 Clasificar Régimen", type="primary"):
                regime = classifier.classify(current_price=price_input)
                metrics = classifier.get_metrics()
                
                st.session_state['current_regime'] = regime.value
                st.session_state['current_metrics'] = metrics
                st.session_state['last_update'] = datetime.now()
        
        with col2:
            st.subheader("Estado Actual")
            
            if 'current_regime' in st.session_state:
                regime_emoji = get_regime_color(st.session_state['current_regime'])
                st.metric(
                    "Régimen Detectado",
                    f"{regime_emoji} {st.session_state['current_regime']}"
                )
                
                if 'last_update' in st.session_state:
                    st.caption(f"Última actualización: {st.session_state['last_update'].strftime('%H:%M:%S')}")
            else:
                st.info("👆 Ingresa un precio y haz clic en 'Clasificar Régimen' para comenzar")
        
        # Métricas detalladas
        if 'current_metrics' in st.session_state:
            st.subheader("📈 Métricas Detalladas")
            
            metrics = st.session_state['current_metrics']
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("ADX", f"{metrics.get('adx', 0):.2f}")
            
            with col2:
                st.metric("Volatilidad", f"{metrics.get('volatility', 0):.4f}")
            
            with col3:
                sma_dist = metrics.get('sma_distance')
                if sma_dist is not None:
                    st.metric("Distancia SMA 200", f"{sma_dist:.2f}%")
                else:
                    st.metric("Distancia SMA 200", "N/A")
            
            with col4:
                bias = metrics.get('bias', 'N/A')
                st.metric("Sesgo", bias)
            
            # Información adicional
            with st.expander("🔍 Información Adicional"):
                st.json(metrics)
    
    # TAB 2: Gestión de Módulos
    with tab2:
        st.header("🎛️ Gestión de Módulos Activos")
        
        st.info(f"📋 Mostrando módulos para membresía: **{membership.upper()}**")
        
        # Obtener módulos activos
        active_modules = module_manager.get_active_modules(membership_level)
        all_modules_info = module_manager.get_all_modules_info()
        
        st.subheader("Módulos Disponibles")
        
        # Crear switches para cada módulo
        module_states = {}
        
        for module_name, module_config in all_modules_info.items():
            can_execute = module_manager.can_execute_module(module_name, membership_level)
            is_enabled = module_config.get("enabled", False)
            
            col1, col2, col3 = st.columns([1, 3, 2])
            
            with col1:
                # Switch para activar/desactivar
                new_state = st.checkbox(
                    module_name,
                    value=is_enabled,
                    disabled=not can_execute,
                    key=f"module_{module_name}"
                )
                module_states[module_name] = new_state
            
            with col2:
                st.write(f"*{module_config.get('description', 'Sin descripción')}*")
            
            with col3:
                if can_execute:
                    st.success("✅ Permitido")
                else:
                    st.error("❌ No permitido")
                
                regimes = ", ".join(module_config.get("required_regime", []))
                st.caption(f"Régimen: {regimes}")
        
        # Botón para aplicar cambios
        if st.button("💾 Guardar Cambios de Módulos", type="primary"):
            for module_name, new_state in module_states.items():
                current_state = all_modules_info[module_name].get("enabled", False)
                if new_state != current_state:
                    if new_state:
                        module_manager.enable_module(module_name)
                    else:
                        module_manager.disable_module(module_name)
            
            st.success("✅ Cambios guardados correctamente")
            st.rerun()
        
        # Mostrar módulos activos para el régimen actual
        if 'current_regime' in st.session_state:
            st.subheader("Módulos Disponibles para Régimen Actual")
            current_regime = st.session_state['current_regime']
            available_modules = module_manager.get_modules_for_regime(
                current_regime,
                membership_level
            )
            
            if available_modules:
                st.success(f"✅ {len(available_modules)} módulo(s) disponible(s) para régimen {current_regime}")
                for module_name in available_modules:
                    st.write(f"  • {module_name}")
            else:
                st.warning(f"⚠️ No hay módulos disponibles para régimen {current_regime}")
    
    # TAB 3: Parámetros Dinámicos (Antigua tab3)
    with tab_params:
        st.header("⚙️ Parámetros Dinámicos del Tuner")
        
        # Cargar parámetros actuales
        try:
            current_params = tuner.get_optimal_params()
            
            st.subheader("Parámetros Actuales")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### Umbrales ADX")
                st.metric("ADX Trend Threshold", f"{current_params.get('adx_trend_threshold', 0):.2f}")
                st.metric("ADX Range Threshold", f"{current_params.get('adx_range_threshold', 0):.2f}")
                st.metric("ADX Range Exit Threshold", f"{current_params.get('adx_range_exit_threshold', 0):.2f}")
            
            with col2:
                st.markdown("### Parámetros de Volatilidad")
                st.metric("Volatility Shock Multiplier", f"{current_params.get('volatility_shock_multiplier', 0):.2f}")
                st.metric("Shock Lookback", f"{current_params.get('shock_lookback', 0)}")
                st.metric("Min Volatility ATR Period", f"{current_params.get('min_volatility_atr_period', 0)}")
            
            st.markdown("### Otros Parámetros")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("ADX Period", f"{current_params.get('adx_period', 0)}")
            with col2:
                st.metric("SMA Period", f"{current_params.get('sma_period', 0)}")
            with col3:
                st.metric("Persistence Candles", f"{current_params.get('persistence_candles', 0)}")
            
            # Información de última actualización
            last_updated = current_params.get('last_updated')
            if last_updated:
                st.caption(f"Última actualización: {last_updated}")
            
            # Botón para ejecutar auto-calibración
            st.markdown("---")
            st.subheader("Auto-Calibración")
            
            limit_input = st.number_input(
                "Número de registros históricos a analizar",
                min_value=100,
                max_value=10000,
                value=1000,
                step=100
            )
            
            if st.button("🔄 Ejecutar Auto-Calibración", type="primary"):
                with st.spinner("Ejecutando auto-calibración... Esto puede tomar unos minutos."):
                    try:
                        new_params = tuner.auto_calibrate(limit=int(limit_input))
                        st.success("✅ Auto-calibración completada exitosamente")
                        st.json(new_params)
                        
                        # Recargar parámetros
                        st.cache_resource.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error en auto-calibración: {e}")
                        logger.error(f"Error en auto-calibración: {e}", exc_info=True)
            
            # Mostrar parámetros en formato JSON
            with st.expander("📄 Ver Parámetros en JSON"):
                st.json(current_params)
        
        except Exception as e:
            st.error(f"Error cargando parámetros: {e}")
            logger.error(f"Error cargando parámetros: {e}", exc_info=True)
    
    # TAB 4: Estadísticas (Antigua tab4)
    with tab_stats:
        st.header("📈 Estadísticas del Sistema")
        
        try:
            stats = storage.get_statistics()
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Total de Señales", stats.get('total_signals', 0))
            
            with col2:
                signals_by_connector = stats.get('signals_by_connector', {})
                total_connectors = len(signals_by_connector)
                st.metric("Conectores Activos", total_connectors)
            
            with col3:
                signals_by_regime = stats.get('signals_by_regime', {})
                total_regimes = len(signals_by_regime)
                st.metric("Regímenes Detectados", total_regimes)
            
            # Señales por conector
            if signals_by_connector:
                st.subheader("Señales por Conector")
                st.bar_chart(signals_by_connector)
            
            # Señales por régimen
            if signals_by_regime:
                st.subheader("Señales por Régimen")
                st.bar_chart(signals_by_regime)
            
            # Estadísticas de ejecución
            executed_stats = stats.get('executed_signals')
            if executed_stats:
                st.subheader("Estadísticas de Ejecución")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Total Ejecutadas", executed_stats.get('total', 0))
                
                with col2:
                    avg_pnl = executed_stats.get('avg_pnl', 0)
                    st.metric("PNL Promedio", f"{avg_pnl:.2f}")
                
                with col3:
                    winning_trades = executed_stats.get('winning_trades', 0)
                    st.metric("Trades Ganadores", winning_trades)
                
                with col4:
                    win_rate = executed_stats.get('win_rate', 0)
                    st.metric("Win Rate", f"{win_rate:.2%}")
        
        except Exception as e:
            st.error(f"Error cargando estadísticas: {e}")
            logger.error(f"Error cargando estadísticas: {e}", exc_info=True)
        
        # Estado del notificador
        st.markdown("---")
        st.subheader("Estado del Sistema")
        
        notifier = get_notifier()
        if notifier and notifier.is_configured():
            st.success("✅ Notificador de Telegram configurado")
            st.caption(f"Estado: {'Habilitado' if notifier.enabled else 'Deshabilitado'}")
        else:
            st.warning("⚠️ Notificador de Telegram no configurado")


if __name__ == "__main__":
    main()
