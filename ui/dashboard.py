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
from core_brain.data_provider_manager import DataProviderManager
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

@st.cache_resource
def get_provider_manager():
    """Obtiene una instancia del gestor de proveedores de datos"""
    return DataProviderManager()

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
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "🛡️ Monitor de Resiliencia",
        "📊 Régimen en Tiempo Real",
        "🎛️ Gestión de Módulos",
        "⚙️ Parámetros Dinámicos",
        "📈 Estadísticas",
        "⚡ Señales de Trading",
        "📡 Proveedores de Datos"
    ])
    
    # TAB 1: Monitor de Resiliencia
    with tab1:
        st.header("🛡️ Monitor de Resiliencia - Orquestador")
        
        # Obtener estado del sistema
        try:
            system_state = storage.get_system_state()
            session_data = system_state.get("session_stats", {})
            
            # Verificar si hay datos de sesión
            has_session_data = bool(session_data)
            
            # Sección de Uptime y Estado de Recuperación
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("⏱️ Uptime del Sistema")
                
                if has_session_data:
                    last_update = session_data.get("last_update", "N/A")
                    if last_update != "N/A":
                        try:
                            last_update_dt = datetime.fromisoformat(last_update)
                            uptime_seconds = (datetime.now() - last_update_dt).total_seconds()
                            
                            # Formatear uptime
                            hours = int(uptime_seconds // 3600)
                            minutes = int((uptime_seconds % 3600) // 60)
                            seconds = int(uptime_seconds % 60)
                            
                            st.metric(
                                "Tiempo Activo",
                                f"{hours:02d}:{minutes:02d}:{seconds:02d}",
                                delta="En línea"
                            )
                            st.caption(f"Última actualización: {last_update_dt.strftime('%Y-%m-%d %H:%M:%S')}")
                        except (ValueError, TypeError):
                            st.metric("Tiempo Activo", "N/A")
                    else:
                        st.metric("Tiempo Activo", "N/A")
                else:
                    st.info("Sistema inicializándose...")
                    st.metric("Tiempo Activo", "00:00:00")
            
            with col2:
                st.subheader("💾 Estado de Recuperación")
                
                if has_session_data:
                    st.success("✅ Estadísticas Recuperadas de DB")
                    session_date = session_data.get("date", "N/A")
                    st.metric("Fecha de Sesión", session_date)
                    
                    # Verificar si es de hoy
                    try:
                        from datetime import date
                        stored_date = date.fromisoformat(session_date)
                        is_today = stored_date == date.today()
                        
                        if is_today:
                            st.caption("🟢 Sesión activa del día actual")
                        else:
                            st.caption("🟡 Datos de sesión anterior")
                    except (ValueError, TypeError):
                        pass
                else:
                    st.warning("⚠️ No hay datos de sesión previos")
                    st.caption("Primera ejecución o sesión nueva")
            
            st.markdown("---")
            
            # Contadores de Sesión (Conectado a SessionStats)
            st.subheader("📊 Contadores de Sesión")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                signals_processed = session_data.get("signals_processed", 0)
                st.metric(
                    "Señales Procesadas",
                    signals_processed,
                    delta=f"+{signals_processed}" if signals_processed > 0 else None
                )
            
            with col2:
                signals_executed = session_data.get("signals_executed", 0)
                st.metric(
                    "Señales Ejecutadas",
                    signals_executed,
                    delta=f"+{signals_executed}" if signals_executed > 0 else None,
                    delta_color="normal"
                )
            
            with col3:
                errors_count = session_data.get("errors_count", 0)
                st.metric(
                    "Errores",
                    errors_count,
                    delta=f"+{errors_count}" if errors_count > 0 else None,
                    delta_color="inverse"
                )
            
            with col4:
                cycles_completed = session_data.get("cycles_completed", 0)
                st.metric(
                    "Ciclos Completados",
                    cycles_completed
                )
            
            st.markdown("---")
            
            # Indicador de Latido (Heartbeat Indicator)
            st.subheader("💓 Indicador de Latido")
            
            # Obtener el régimen actual desde el estado del sistema
            current_regime_str = st.session_state.get('current_regime', 'RANGE')
            
            # Mapear régimen a intervalo de sleep
            regime_sleep_map = {
                "TREND": 5,
                "RANGE": 30,
                "VOLATILE": 15,
                "SHOCK": 60
            }
            
            sleep_interval = regime_sleep_map.get(current_regime_str, 30)
            
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                # Barra de progreso visual para el latido
                st.markdown(f"**Régimen Actual:** {current_regime_str}")
                st.progress(min(sleep_interval / 60, 1.0))
            
            with col2:
                st.metric("Sleep Interval", f"{sleep_interval}s")
            
            with col3:
                # Indicador de velocidad
                if sleep_interval <= 5:
                    st.markdown("🔴 **RÁPIDO**")
                elif sleep_interval <= 15:
                    st.markdown("🟡 **MEDIO**")
                else:
                    st.markdown("🟢 **LENTO**")
            
            st.caption(
                f"El sistema ejecuta un ciclo cada **{sleep_interval} segundos** "
                f"cuando está en régimen **{current_regime_str}**."
            )
            
            # Descripción del régimen
            regime_descriptions = {
                "TREND": "Mercado en tendencia clara - Ciclos rápidos para capturar movimientos",
                "RANGE": "Mercado lateral - Ciclos lentos para evitar sobre-operación",
                "VOLATILE": "Volatilidad elevada - Ciclos medios para balance entre oportunidad y riesgo",
                "SHOCK": "Shock de mercado - Ciclos muy lentos para protección"
            }
            
            regime_desc = regime_descriptions.get(current_regime_str, "Régimen desconocido")
            st.info(f"ℹ️ {regime_desc}")
            
            st.markdown("---")
            
            # Live Feed (Simulación de logs en tiempo real)
            st.subheader("📡 Live Feed - Actividad del Orquestador")
            
            # Contenedor vacío para logs en tiempo real
            live_feed_container = st.empty()
            
            # Simular logs del orquestador
            if has_session_data:
                log_entries = []
                
                # Generar logs basados en las estadísticas
                if cycles_completed > 0:
                    log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Ciclo {cycles_completed}: Completado")
                
                if signals_processed > 0:
                    log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🔍 Escaneando mercado... ({signals_processed} señales procesadas hoy)")
                
                if signals_executed > 0:
                    log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] 🎯 Señal ejecutada correctamente")
                    log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Riesgo validado")
                
                if errors_count > 0:
                    log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] ⚠️ Error detectado - Total de errores: {errors_count}")
                
                # Agregar log de régimen actual
                log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] 📊 Régimen actual: {current_regime_str}")
                log_entries.append(f"[{datetime.now().strftime('%H:%M:%S')}] 💓 Próximo ciclo en {sleep_interval}s...")
                
                # Mostrar en el contenedor
                log_text = "\n".join(log_entries[-10:])  # Últimas 10 líneas
                live_feed_container.code(log_text, language="log")
            else:
                live_feed_container.info("⏳ Esperando actividad del orquestador...")
            
            # Botón de refresco
            if st.button("🔄 Refrescar Monitor", type="primary"):
                st.rerun()
                
        except Exception as e:
            st.error(f"❌ Error cargando datos del monitor: {e}")
            logger.error(f"Error en monitor de resiliencia: {e}", exc_info=True)
    
    # TAB 2: Régimen en Tiempo Real
    with tab2:
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
    
    # TAB 3: Gestión de Módulos
    with tab3:
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
    
    # TAB 4: Parámetros Dinámicos
    with tab4:
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
    
    # TAB 5: Estadísticas
    with tab5:
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
    
    # TAB 6: Señales de Trading
    with tab6:
        st.header("⚡ Señales de Trading en Tiempo Real")
        
        # Auto-refresh automático cada 3 segundos
        st.markdown("""
        <style>
        .refresh-indicator {
            position: fixed;
            top: 70px;
            right: 20px;
            background: #00ff00;
            color: black;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 12px;
            z-index: 999;
        }
        </style>
        <div class="refresh-indicator">🔄 Auto-refresh: 3s</div>
        """, unsafe_allow_html=True)
        
        # Contenedor para actualización automática
        auto_refresh = st.empty()
        
        with auto_refresh.container():
            # Filtros
            col1, col2, col3, col4 = st.columns(4)
        
            with col1:
                filter_type = st.selectbox(
                    "Tipo de Señal",
                    options=["Todas", "BUY", "SELL"],
                    index=0,
                    key="signal_type_filter"
                )
            
            with col2:
                filter_tier = st.selectbox(
                    "Nivel de Membresía",
                    options=["Todos", "FREE", "PREMIUM", "ELITE"],
                    index=0,
                    key="tier_filter"
                )
            
            with col3:
                limit_signals = st.number_input(
                    "Mostrar últimas N señales",
                    min_value=5,
                    max_value=100,
                    value=20,
                    step=5,
                    key="limit_signals"
                )
            
            with col4:
                # Timestamp de última actualización
                st.metric("Última actualización", datetime.now().strftime("%H:%M:%S"))
            
            st.markdown("---")
            
            # Obtener señales de hoy
            try:
                signals_today = storage.get_signals_today()
                
                if not signals_today:
                    st.info("📭 No hay señales generadas hoy")
                    st.caption("Las señales aparecerán aquí cuando el sistema detecte oportunidades en TREND")
                    st.caption(f"⏰ Sistema escaneando... próxima actualización automática en 3s")
                else:
                    # Aplicar filtros
                    filtered_signals = signals_today
                    
                    if filter_type != "Todas":
                        filtered_signals = [s for s in filtered_signals if s.get('signal_type') == filter_type]
                    
                    if filter_tier != "Todos":
                        filtered_signals = [s for s in filtered_signals if s.get('metadata', {}).get('membership_tier') == filter_tier]
                    
                    # Limitar número de señales
                    filtered_signals = filtered_signals[-limit_signals:]
                    
                    # Resumen de señales
                    st.subheader(f"📊 Resumen ({len(filtered_signals)} señales)")
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        buy_signals = sum(1 for s in filtered_signals if s.get('signal_type') == 'BUY')
                        st.metric("🟢 Señales BUY", buy_signals)
                    
                    with col2:
                        sell_signals = sum(1 for s in filtered_signals if s.get('signal_type') == 'SELL')
                        st.metric("🔴 Señales SELL", sell_signals)
                    
                    with col3:
                        premium_signals = sum(1 for s in filtered_signals if s.get('metadata', {}).get('membership_tier') in ['PREMIUM', 'ELITE'])
                        st.metric("💎 Premium/Elite", premium_signals)
                    
                    with col4:
                        avg_score = sum(s.get('metadata', {}).get('score', 0) for s in filtered_signals) / len(filtered_signals) if filtered_signals else 0
                        st.metric("⭐ Score Promedio", f"{avg_score:.1f}")
                    
                    st.markdown("---")
                    
                    # Tabla de señales
                    st.subheader("📋 Señales Detalladas")
                    
                    for idx, signal in enumerate(reversed(filtered_signals)):
                        # Crear un expander para cada señal
                        metadata = signal.get('metadata', {})
                        signal_type = signal.get('signal_type', 'N/A')
                        symbol = signal.get('symbol', 'N/A')
                        score = metadata.get('score', 0)
                        tier = metadata.get('membership_tier', 'FREE')
                        timestamp = signal.get('timestamp', 'N/A')
                        
                        # Emoji según tipo
                        type_emoji = "🟢" if signal_type == "BUY" else "🔴"
                        
                        # Color según tier
                        tier_color = {
                            'ELITE': '🌟',
                            'PREMIUM': '💎',
                            'FREE': '📌'
                        }.get(tier, '📌')
                        
                        with st.expander(f"{type_emoji} {symbol} - {signal_type} | Score: {score:.1f} {tier_color} {tier} | {timestamp}"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                st.markdown("**📊 Precios**")
                                st.write(f"Entry: `{signal.get('entry_price', 'N/A')}`")
                                st.write(f"Stop Loss: `{signal.get('stop_loss', 'N/A')}`")
                                st.write(f"Take Profit: `{signal.get('take_profit', 'N/A')}`")
                            
                            with col2:
                                st.markdown("**🎯 Indicadores Técnicos**")
                                st.write(f"Régimen: `{metadata.get('regime', 'N/A')}`")
                                st.write(f"ATR: `{metadata.get('atr', 'N/A')}`")
                                st.write(f"Body/ATR Ratio: `{metadata.get('body_atr_ratio', 'N/A')}`")
                                st.write(f"SMA20 Dist: `{metadata.get('sma20_dist_pct', 'N/A')}%`")
                            
                            with col3:
                                st.markdown("**✅ Validaciones**")
                                st.write(f"Vela Elefante: `{'✅' if metadata.get('is_elephant_candle') else '❌'}`")
                                st.write(f"Cerca de SMA20: `{'✅' if metadata.get('near_sma20') else '❌'}`")
                                st.write(f"Confidence: `{signal.get('confidence', 0):.2%}`")
                                st.write(f"Strategy: `{metadata.get('strategy_id', 'N/A')}`")
                            
                            # Mostrar metadata completa en JSON
                            if st.checkbox(f"Ver JSON completo (señal #{len(filtered_signals) - idx})", key=f"json_{signal.get('id', idx)}"):
                                st.json(signal)
                    
            except Exception as e:
                st.error(f"Error cargando señales: {e}")
                logger.error(f"Error cargando señales: {e}", exc_info=True)
    
    # TAB 7: Proveedores de Datos
    with tab7:
        st.header("📡 Gestión de Proveedores de Datos")
        
        try:
            provider_manager = get_provider_manager()
            
            # Información general
            st.markdown("""
            Configura múltiples fuentes de datos para obtener información de mercado. 
            El sistema selecciona automáticamente el mejor proveedor disponible basado en prioridad.
            """)
            
            st.markdown("---")
            
            # Sección: Proveedores Gratuitos (sin autenticación)
            st.subheader("🆓 Proveedores Gratuitos (Sin API Key)")
            
            free_providers = provider_manager.get_free_providers()
            
            if free_providers:
                for provider_info in free_providers:
                    name = provider_info["name"]
                    enabled = provider_info["enabled"]
                    description = provider_info.get("description", "")
                    supports = provider_info.get("supports", [])
                    
                    with st.expander(f"{'✅' if enabled else '❌'} {name.upper()} - {description}", expanded=enabled):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.markdown(f"**Soporta:** {', '.join(supports)}")
                            
                            # Mostrar estado
                            status = provider_manager.get_provider_status(name)
                            if status:
                                if status.available:
                                    st.success("✅ Disponible")
                                else:
                                    st.error("❌ No disponible (librería no instalada)")
                        
                        with col2:
                            # Toggle para habilitar/deshabilitar
                            if enabled:
                                if st.button(f"Deshabilitar", key=f"disable_{name}"):
                                    provider_manager.disable_provider(name)
                                    st.success(f"Proveedor {name} deshabilitado")
                                    st.rerun()
                            else:
                                if st.button(f"Habilitar", key=f"enable_{name}"):
                                    provider_manager.enable_provider(name)
                                    st.success(f"Proveedor {name} habilitado")
                                    st.rerun()
                        
                        # Configuración adicional para CCXT
                        if name == "ccxt":
                            config = provider_manager.get_provider_config(name)
                            current_exchange = config.additional_config.get("exchange_id", "binance")
                            
                            new_exchange = st.selectbox(
                                "Exchange",
                                options=["binance", "coinbase", "kraken", "bitfinex", "huobi", "okx"],
                                index=["binance", "coinbase", "kraken", "bitfinex", "huobi", "okx"].index(current_exchange) if current_exchange in ["binance", "coinbase", "kraken", "bitfinex", "huobi", "okx"] else 0,
                                key=f"exchange_{name}"
                            )
                            
                            if new_exchange != current_exchange:
                                provider_manager.configure_provider(name, exchange_id=new_exchange)
                                st.success(f"Exchange actualizado a {new_exchange}")
            else:
                st.info("No hay proveedores gratuitos disponibles")
            
            st.markdown("---")
            
            # Sección: Proveedores con API Key
            st.subheader("🔑 Proveedores con API Key (Tier Gratuito Disponible)")
            
            auth_providers = provider_manager.get_auth_required_providers()
            
            if auth_providers:
                for provider_info in auth_providers:
                    name = provider_info["name"]
                    enabled = provider_info["enabled"]
                    configured = provider_info.get("configured", False)
                    description = provider_info.get("description", "")
                    supports = provider_info.get("supports", [])
                    
                    # Emoji de estado
                    status_emoji = "✅" if enabled and configured else "⚙️" if enabled else "❌"
                    
                    with st.expander(f"{status_emoji} {name.upper()} - {description}", expanded=False):
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.markdown(f"**Soporta:** {', '.join(supports)}")
                            
                            # Mostrar estado
                            status = provider_manager.get_provider_status(name)
                            if status:
                                if not status.available:
                                    st.error("❌ Librería no instalada")
                                elif not status.credentials_configured:
                                    st.warning("⚠️ API Key no configurada")
                                else:
                                    st.success("✅ Configurado y listo")
                            
                            # Links para obtener API keys
                            api_key_links = {
                                "alphavantage": "https://www.alphavantage.co/support/#api-key",
                                "twelvedata": "https://twelvedata.com/pricing",
                                "polygon": "https://polygon.io/",
                                "mt5": "Requiere MetaTrader 5 instalado localmente"
                            }
                            
                            if name in api_key_links:
                                link = api_key_links[name]
                                if link.startswith("http"):
                                    st.markdown(f"[🔗 Obtener API Key gratuita]({link})")
                                else:
                                    st.info(f"ℹ️ {link}")
                        
                        with col2:
                            # Toggle para habilitar/deshabilitar
                            if enabled:
                                if st.button(f"Deshabilitar", key=f"disable_{name}"):
                                    provider_manager.disable_provider(name)
                                    st.success(f"Proveedor {name} deshabilitado")
                                    st.rerun()
                            else:
                                if st.button(f"Habilitar", key=f"enable_{name}"):
                                    provider_manager.enable_provider(name)
                                    st.success(f"Proveedor {name} habilitado")
                                    st.rerun()
                        
                        st.markdown("---")
                        
                        # Formulario para configurar API Key
                        if name != "mt5":
                            with st.form(key=f"config_form_{name}"):
                                st.markdown("**Configuración**")
                                
                                config = provider_manager.get_provider_config(name)
                                current_key = config.api_key if config else ""
                                
                                api_key_input = st.text_input(
                                    "API Key",
                                    value=current_key if current_key else "",
                                    type="password",
                                    help="Tu API key del proveedor"
                                )
                                
                                submitted = st.form_submit_button("💾 Guardar Configuración")
                                
                                if submitted and api_key_input:
                                    provider_manager.configure_provider(name, api_key=api_key_input)
                                    st.success(f"✅ API Key guardada para {name}")
                                    st.rerun()
                        else:
                            # Configuración especial para MT5
                            with st.form(key=f"config_form_{name}"):
                                st.markdown("**Configuración MT5**")
                                
                                config = provider_manager.get_provider_config(name)
                                mt5_config = config.additional_config if config else {}
                                
                                login = st.text_input("Login", value=mt5_config.get("login", ""))
                                password = st.text_input("Password", value="", type="password")
                                server = st.text_input("Server", value=mt5_config.get("server", ""))
                                
                                submitted = st.form_submit_button("💾 Guardar Configuración")
                                
                                if submitted and login and server:
                                    provider_manager.configure_provider(
                                        name,
                                        login=login,
                                        password=password if password else mt5_config.get("password", ""),
                                        server=server
                                    )
                                    st.success(f"✅ Configuración guardada para MT5")
                                    st.rerun()
            else:
                st.info("No hay proveedores con autenticación disponibles")
            
            st.markdown("---")
            
            # Sección: Estado Actual
            st.subheader("📊 Estado Actual del Sistema")
            
            active_providers = provider_manager.get_active_providers()
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric("Proveedores Activos", len(active_providers))
                
                if active_providers:
                    st.markdown("**Lista de activos (por prioridad):**")
                    for idx, prov in enumerate(active_providers, 1):
                        st.write(f"{idx}. {prov['name'].upper()} (prioridad: {prov['priority']})")
            
            with col2:
                # Proveedor actual seleccionado
                best_provider = provider_manager.get_best_provider()
                
                if best_provider:
                    provider_name = best_provider.__class__.__name__.replace("Provider", "").replace("DataProvider", "")
                    st.success(f"✅ Proveedor activo: **{provider_name}**")
                else:
                    st.error("❌ Ningún proveedor disponible")
                
                # Botón para probar conexión
                if st.button("🔍 Probar Conexión"):
                    with st.spinner("Probando conexión..."):
                        if best_provider:
                            try:
                                # Intentar fetch de datos de prueba
                                test_data = provider_manager.fetch_ohlc("AAPL", "D1", 10)
                                
                                if test_data is not None and len(test_data) > 0:
                                    st.success(f"✅ Conexión exitosa! {len(test_data)} velas obtenidas")
                                    st.dataframe(test_data.tail(5))
                                else:
                                    st.warning("⚠️ Conexión establecida pero sin datos")
                            except Exception as e:
                                st.error(f"❌ Error en la conexión: {str(e)}")
                        else:
                            st.error("❌ No hay proveedor disponible para probar")
        
        except Exception as e:
            st.error(f"Error en gestión de proveedores: {e}")
            logger.error(f"Error en tab proveedores: {e}", exc_info=True)
        
        # Auto-refresh cada 3 segundos
        import time
        time.sleep(3)
        st.rerun()


if __name__ == "__main__":
    main()
