"""
Dashboard de Control para Aethelgard
Interfaz Streamlit para monitorear el régimen de mercado, gestionar módulos y ver parámetros dinámicos
"""
import streamlit as st
import asyncio
import json
import logging
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, Optional, List, Any
import sys
import random # Importar random para simulación de datos
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import traceback
import importlib

# Añadir el directorio raíz al path para importar módulos
sys.path.insert(0, str(Path(__file__).parent.parent))

# from connectors.mt5_discovery import DiscoveryEngine # MT5 Discovery (optional utility)
from core_brain.regime import RegimeClassifier
from core_brain.module_manager import get_module_manager, MembershipLevel
from core_brain.tuner import ParameterTuner
from core_brain.notificator import get_notifier
from core_brain.data_provider_manager import DataProviderManager
from core_brain.instrument_manager import InstrumentManager
from data_vault.storage import StorageManager
from core_brain.health import HealthManager
# from models.signal import MarketRegime

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

@st.cache_resource
def get_health_manager():
    """Obtiene una instancia del motor de diagnóstico"""
    return HealthManager()

@st.cache_resource
def get_instrument_manager():
    """Obtiene una instancia del gestor de instrumentos"""
    return InstrumentManager()

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
    # Fix for UnboundLocalError by ensuring global access to plotly and pandas
    global pd, px, go
    
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
        
        st.markdown("---")
        st.subheader("🛠️ Soporte Técnico")
        st.caption("Accede a la pestaña '🛡️ Sistema' para diagnósticos.")
            
        # Botón para recargar datos
        if st.button("🔄 Recargar Datos"):
            st.cache_resource.clear()
            st.rerun()
    
    # Obtener instancias
    classifier = get_classifier()
    storage = get_storage()
    module_manager = get_module_manager()
    tuner = get_tuner()
    
    # Navegación Principal en Sidebar
    menu_selection = None
    with st.sidebar:
        st.markdown("---")
        st.subheader("🧭 Navegación")
        
        # Categorías de navegación
        category = st.selectbox(
            "Categoría",
            ["🏠 Inicio", "Operación Hub", "Análisis & Mercado", "Configuración"],
            index=0
        )
        
        if category == "🏠 Inicio":
            menu_selection = "🏠 Inicio"
        elif category == "Operación Hub":
            menu_selection = st.radio(
                "Módulo",
                ["🛡️ Sistema & Diagnóstico", "🔌 Configuración de Brokers", "🛡️ Monitor de Resiliencia", "⚡ Señales de Trading"]
            )
        elif category == "Análisis & Mercado":
            menu_selection = st.radio(
                "Vista",
                ["📊 Régimen en Tiempo Real", "📈 Estadísticas", "💰 Análisis de Activos"]
            )
        else: # Configuración
            menu_selection = st.radio(
                "Ajustes",
                ["🎛️ Gestión de Módulos", "⚙️ Parámetros Dinámicos", "📡 Proveedores de Datos", "🎯 Gestión de Instrumentos"]
            )
    
    
    # Renderizar vista seleccionada
    if menu_selection == "🏠 Inicio":
        st.header("🏠 Panel de Control Principal")
        # --- COMMAND CENTER HEADER ---
        col1, col2, col3, col4 = st.columns(4)
        
        # Get statistics and active trades
        try:
            # Check if storage or provider_manager are stale
            storage_stale = not hasattr(storage, 'get_open_operations')
            
            # We also check ProviderConfig indirectly via DataProviderManager
            # But simpler to just check if we have the new fields
            prov_manager = get_provider_manager()
            config_sample = prov_manager.get_active_providers()
            # If active providers don't have is_system in their metadata or config
            prov_stale = False
            if config_sample:
                test_name = config_sample[0]['name']
                test_conf = prov_manager.get_provider_config(test_name)
                prov_stale = not hasattr(test_conf, 'is_system')

            if storage_stale or prov_stale:
                # Force reload of core modules and clear cache
                st.cache_resource.clear()
                
                import data_vault.storage
                importlib.reload(data_vault.storage)
                from data_vault.storage import StorageManager
                
                import core_brain.data_provider_manager
                importlib.reload(core_brain.data_provider_manager)
                from core_brain.data_provider_manager import DataProviderManager
                
                st.info("🔄 Se detectó una versión antigua del motor de datos o proveedores. Limpiando caché y reiniciando conexión...")
                st.rerun() # Rerun to ensure clean state
            
            stats = storage.get_statistics()
            open_trades = storage.get_open_operations()
            recent_trades = storage.get_recent_trades(limit=50)
            
            # Calculate daily P/L and Balance (simulated or real from broker if connected)
            total_pnl = sum(t.get('profit_loss', 0) for t in recent_trades)
            win_rate = stats.get('executed_signals', {}).get('win_rate', 0)
            
            with col1:
                st.metric("Equity Total", f"${10540.50 + total_pnl:,.2f}", delta=f"{total_pnl:+.2f}")
            with col2:
                st.metric("Balance", f"${10540.50:,.2f}")
            with col3:
                st.metric("Win Rate (Total)", f"{win_rate:.1%}")
            with col4:
                st.metric("Ops. Abiertas", len(open_trades))
        except Exception as e:
            st.error(f"⚠️ Error cargando estadísticas principales: {e}")
            st.code(traceback.format_exc())
            stats = {}
            open_trades = []
            recent_trades = []

        st.markdown("---")
        
        # --- ACTIVE OPERATIONS ---
        st.subheader("🚀 Operaciones Activas")
        if open_trades:
            # Table of active trades
            trade_data = []
            for t in open_trades:
                meta = t.get('metadata', {})
                trade_data.append({
                    "ID": t.get('id')[:8],
                    "Símbolo": t.get('symbol'),
                    "Tipo": t.get('signal_type'),
                    "Entrada": t.get('entry_price'),
                    "SL": t.get('stop_loss'),
                    "TP": t.get('take_profit'),
                    "Score": f"{meta.get('score', 0):.1f}",
                    "Tiempo": t.get('timestamp', '').split('T')[-1][:5]
                })
            
            df_open = pd.DataFrame(trade_data)
            st.dataframe(df_open, use_container_width=True, hide_index=True)
            
            # Action buttons for first few trades
            for t in open_trades[:3]:
                with st.expander(f"Gestionar {t['symbol']} ({t['signal_type']})"):
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(f"Cerrar {t['symbol']}", key=f"close_{t['id']}"):
                            st.warning(f"Solicitando cierre de {t['id']}...")
                    with c2:
                        st.info(f"SL: {t['stop_loss']} | TP: {t['take_profit']}")
        else:
            st.info("No hay operaciones abierta en este momento.")

        st.markdown("---")
        
        # --- ANALYTICS & CHARTS ---
        col_c1, col_c2 = st.columns([2, 1])
        
        with col_c1:
            st.subheader("📈 Rendimiento Acumulado")
            if recent_trades:
                # Simple P/L accumulation
                pnl_history = []
                current_acc = 0
                for t in reversed(recent_trades):
                    current_acc += t.get('profit_loss', 0)
                    pnl_history.append({"time": t.get('timestamp'), "pnl": current_acc})
                
                df_pnl = pd.DataFrame(pnl_history)
                fig = px.line(df_pnl, x="time", y="pnl", title="Curva de P/L (Reciente)")
                fig.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("No hay datos históricos suficientes para graficar.")
                
        with col_c2:
            st.subheader("🎯 Win/Loss")
            if recent_trades:
                wins = sum(1 for t in recent_trades if t.get('is_win'))
                losses = len(recent_trades) - wins
                fig_pie = px.pie(values=[wins, losses], names=['Wins', 'Losses'], 
                                color_discrete_sequence=['#00CC96', '#EF553B'])
                fig_pie.update_layout(height=300, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_pie, use_container_width=True)

        st.markdown("---")
        # --- BROKER HEALTH CARDS ---
        st.subheader("🔌 Estado de Brokers/Conectores")
        accounts = storage.get_broker_accounts()
        if accounts:
            cols = st.columns(len(accounts) if len(accounts) < 5 else 4)
            for i, acc in enumerate(accounts):
                with cols[i % 4]:
                    status_color = "🟢" if acc.get('enabled') else "🔴"
                    st.info(f"{status_color} **{acc.get('broker_id', 'N/A').upper()}**\n\n{acc.get('account_number', 'N/A')}\n\nBalance: ${acc.get('balance', 0):,.2f}")
        else:
            st.info("No hay cuentas de broker configuradas.")

    elif menu_selection == "🛡️ Sistema & Diagnóstico":
        st.header("🛡️ Aethelgard System Monitor")
        health_manager = get_health_manager()
        
        # Botón de reparación manual
        if st.button("🔧 Ejecutar Auto-Reparación de DB"):
            if health_manager.try_auto_repair():
                st.success("✅ Intento de reparación completado. Refrescando...")
                st.rerun()
            else:
                st.error("❌ Falló la auto-reparación. Revisa los logs.")

        summary = health_manager.run_full_diagnostic()
        status = summary["overall_status"]
        status_emoji = {"GREEN": "✅", "YELLOW": "⚠️", "RED": "🚨"}.get(status, "⚪")
        
        st.subheader(f"Estado Global: {status_emoji} {status}")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("CPU Usage", f"{summary['resources'].get('cpu_percent', 0)}%")
        with col2:
            st.metric("RAM (Process)", f"{summary['resources'].get('memory_mb', 0):.1f} MB")
        with col3:
            st.metric("Threads", summary['resources'].get('threads', 0))
        with col4:
            st.metric("Timestamp", datetime.fromisoformat(summary["timestamp"]).strftime("%H:%M:%S"))

        st.markdown("---")
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("📂 Configuración")
            for d in summary["config"]["details"]:
                st.write(f"{'🟢' if 'SUCCESS' in d else '🔴'} {d}")
        with c2:
            st.subheader("🗄️ Base de Datos")
            for d in summary["db"]["details"]:
                st.write(f"{'🟢' if 'SUCCESS' in d else '🟡' if 'WARNING' in d else '🔴'} {d}")
    
    # TAB 1: Monitor de Resiliencia
    elif menu_selection == "🛡️ Monitor de Resiliencia":
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
            # st.error(f"❌ Error cargando datos del monitor: {e}")
            # logger.error(f"Error en monitor de resiliencia: {e}", exc_info=True)
            st.info("Monitor desactivado para debug")
    
    # TAB 2: Régimen en Tiempo Real
    elif menu_selection == "📊 Régimen en Tiempo Real":
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
    elif menu_selection == "🎛️ Gestión de Módulos":
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
    elif menu_selection == "⚙️ Parámetros Dinámicos":
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
    elif menu_selection == "📈 Estadísticas":
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
    elif menu_selection == "⚡ Señales de Trading":
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
    elif menu_selection == "📡 Proveedores de Datos":
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
                                
                            # Add is_system for free providers
                            config = provider_manager.get_provider_config(name)
                            is_sys = st.checkbox("Usar como fuente para el Scanner (System Data)", value=getattr(config, 'is_system', False), key=f"sys_free_{name}")
                            if is_sys != config.is_system:
                                provider_manager.set_system_provider(name, is_sys)
                                st.success(f"Estado de sistema actualizado para {name}")
                                st.rerun()
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
                                    st.error(f"❌ Librería/Software no detectado")
                                    if name == "mt5":
                                        st.caption("💡 Para MT5: Asegúrate de tener MetaTrader 5 instalado y configurado.")
                                elif not status.credentials_configured:
                                    msg = "⚠️ Credenciales no configuradas" if name == "mt5" else "⚠️ API Key no configurada"
                                    st.warning(msg)
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
                                
                                is_system = st.checkbox("Usar como fuente para el Scanner (System Data)", value=getattr(config, 'is_system', False), key=f"sys_auth_{name}")
                                
                                submitted = st.form_submit_button("💾 Guardar Configuración")
                                
                                if submitted and api_key_input:
                                    provider_manager.configure_provider(name, api_key=api_key_input)
                                    provider_manager.set_system_provider(name, is_system)
                                    st.success(f"✅ Configuración guardada para {name}")
                                    st.rerun()
                        else:
                            # Configuración especial para MT5
                            with st.form(key=f"config_form_{name}"):
                                st.markdown("**Configuración MT5**")
                                
                                config = provider_manager.get_provider_config(name)
                                mt5_config = config.additional_config if config else {}
                                
                                login = st.text_input("Login", value=mt5_config.get("login", ""))
                                
                                # Hint visual para contraseña guardada
                                has_pwd = bool(mt5_config.get("password"))
                                pwd_label = "Password" + (" (🔒 Guardado)" if has_pwd else "")
                                password = st.text_input(pwd_label, value="", type="password", help="Deja vacío para mantener la contraseña actual. Si es la primera vez, ingrésala aquí.")
                                
                                
                                server = st.text_input("Server", value=mt5_config.get("server", ""))
                                
                                is_system = st.checkbox("Usar como fuente para el Scanner (System Data)", value=getattr(config, 'is_system', False), key=f"sys_mt5_{name}")
                                
                                submitted = st.form_submit_button("💾 Guardar Configuración")
                                
                                if submitted and login and server:
                                    provider_manager.configure_provider(
                                        name,
                                        login=login,
                                        password=password if password else mt5_config.get("password", ""),
                                        server=server
                                    )
                                    provider_manager.set_system_provider(name, is_system)
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
    
    # TAB 8: Análisis de Activos (NEW - Feedback Loop)
    elif menu_selection == "💰 Análisis de Activos":
        st.header("💰 Análisis de Rentabilidad por Activo")
        st.markdown("Análisis basado en resultados reales de trading (Feedback Loop)")
        
        # Filtro de días
        col1, col2 = st.columns([2, 1])
        
        with col1:
            days_filter = st.slider(
                "Período de análisis (días)",
                min_value=1,
                max_value=90,
                value=30,
                step=1
            )
        
        with col2:
            if st.button("🔄 Actualizar Datos"):
                st.rerun()
        
        st.markdown("---")
        
        try:
            # KPIs Principales - Calculados desde la DB real
            st.subheader("📊 KPIs Principales")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_profit = storage.get_total_profit(days=days_filter)
                delta_color = "normal" if total_profit >= 0 else "inverse"
                st.metric(
                    "Profit Total",
                    f"${total_profit:,.2f}",
                    delta=f"{'↑' if total_profit > 0 else '↓'} {abs(total_profit):.2f}",
                    delta_color=delta_color
                )
            
            with col2:
                win_rate = storage.get_win_rate(days=days_filter)
                st.metric(
                    "Win Rate",
                    f"{win_rate:.1f}%",
                    delta="Últimos " + str(days_filter) + " días"
                )
            
            with col3:
                all_trades = storage.get_all_trades(limit=1000)
                recent_trades = [t for t in all_trades if t.get('date') >= (datetime.now().date() - __import__('datetime').timedelta(days=days_filter)).isoformat()]
                total_trades = len(recent_trades)
                st.metric(
                    "Total Trades",
                    total_trades
                )
            
            with col4:
                if total_trades > 0:
                    avg_profit = total_profit / total_trades
                    st.metric(
                        "Profit Promedio",
                        f"${avg_profit:.2f}"
                    )
                else:
                    st.metric("Profit Promedio", "$0.00")
            
            st.markdown("---")
            
            # Gráfico de barras: Profit por símbolo
            st.subheader("📈 Profit Acumulado por Símbolo")
            
            profit_by_symbol = storage.get_profit_by_symbol(days=days_filter)
            
            if profit_by_symbol:
                import pandas as pd
                
                # Preparar datos para gráfico
                df_profit = pd.DataFrame(profit_by_symbol)
                
                # Gráfico de barras con colores
                import plotly.express as px
                
                fig = px.bar(
                    df_profit,
                    x='symbol',
                    y='profit',
                    color='profit',
                    color_continuous_scale=['red', 'yellow', 'green'],
                    labels={'symbol': 'Símbolo', 'profit': 'Profit ($)'},
                    title=f'Rentabilidad por Activo (últimos {days_filter} días)',
                    text='profit'
                )
                
                fig.update_traces(texttemplate='$%{text:.2f}', textposition='outside')
                fig.update_layout(showlegend=False)
                
                st.plotly_chart(fig, use_container_width=True)
                
                st.markdown("---")
                
                # Tabla detallada por activo
                st.subheader("📋 Tabla Detallada de Rentabilidad")
                
                # Agregar columna de color para resultado
                df_profit['Resultado'] = df_profit['profit'].apply(
                    lambda x: '🟢 Ganador' if x > 0 else ('🔴 Perdedor' if x < 0 else '⚪ Neutro')
                )
                
                # Formatear columnas
                df_display = df_profit[['symbol', 'total_trades', 'win_rate', 'profit', 'avg_profit', 'total_pips', 'Resultado']].copy()
                df_display.columns = ['Símbolo', 'Total Trades', 'Win Rate (%)', 'Profit Total ($)', 'Profit Promedio ($)', 'PIPs Totales', 'Resultado']
                
                # Aplicar estilo condicional
                def color_resultado(row):
                    if row['Profit Total ($)'] > 0:
                        return ['background-color: #90EE90'] * len(row)
                    elif row['Profit Total ($)'] < 0:
                        return ['background-color: #FFB6C1'] * len(row)
                    else:
                        return [''] * len(row)
                
                st.dataframe(
                    df_display.style.apply(color_resultado, axis=1).format({
                        'Win Rate (%)': '{:.2f}%',
                        'Profit Total ($)': '${:.2f}',
                        'Profit Promedio ($)': '${:.2f}',
                        'PIPs Totales': '{:.1f}'
                    }),
                    use_container_width=True
                )
                
                st.markdown("---")
                
                # Señales recientes con resultado real
                st.subheader("🎯 Últimas Señales con Resultado")
                
                recent_trades_display = storage.get_recent_trades(limit=20)
                
                if recent_trades_display:
                    df_trades = pd.DataFrame(recent_trades_display)
                    
                    # Seleccionar columnas relevantes
                    df_trades_display = df_trades[['symbol', 'entry_price', 'exit_price', 'pips', 'profit_loss', 'is_win', 'exit_reason', 'timestamp']].copy()
                    
                    # Agregar columna de resultado visual
                    df_trades_display['Resultado'] = df_trades_display['is_win'].apply(
                        lambda x: '🟢 Ganada' if x else '🔴 Perdida'
                    )
                    
                    # Formatear timestamp
                    df_trades_display['timestamp'] = pd.to_datetime(df_trades_display['timestamp']).dt.strftime('%Y-%m-%d %H:%M')
                    
                    df_trades_display.columns = ['Símbolo', 'Entrada', 'Salida', 'PIPs', 'Profit ($)', 'Win', 'Razón Salida', 'Fecha/Hora', 'Resultado']
                    
                    # Aplicar color por resultado
                    def color_trade(row):
                        if row['Resultado'] == '🟢 Ganada':
                            return ['background-color: #90EE90'] * len(row)
                        else:
                            return ['background-color: #FFB6C1'] * len(row)
                    
                    st.dataframe(
                        df_trades_display.style.apply(color_trade, axis=1).format({
                            'Entrada': '{:.5f}',
                            'Salida': '{:.5f}',
                            'PIPs': '{:.2f}',
                            'Profit ($)': '${:.2f}'
                        }).hide(['Win'], axis=1),
                        use_container_width=True
                    )
                else:
                    st.info("📭 No hay trades cerrados aún. Los resultados aparecerán cuando el Monitor cierre posiciones.")
            else:
                st.info("📭 No hay datos de trading para el período seleccionado")
                st.caption(f"💡 Ejecuta señales y espera a que se cierren para ver análisis detallado")
        
        except Exception as e:
            st.error(f"Error en análisis de activos: {e}")
            logger.error(f"Error en tab análisis de activos: {e}", exc_info=True)
        
        # Auto-refresh cada 3 segundos
        import time
        time.sleep(3)
        st.rerun()
    
    # TAB 9: Configuración de Brokers (DEBUG MODE)
    # TAB: Configuración de Brokers y Cuentas
    elif menu_selection == "🔌 Configuración de Brokers":
        st.header("🔌 Configuración de Brokers y Cuentas")
        st.markdown("Gestiona brokers, plataformas y cuentas de trading")
        
        try:
            # Botón de refresh
            col_ref1, col_ref2 = st.columns([6, 1])
            with col_ref2:
                if st.button("🔄 Actualizar", key="refresh_brokers"):
                    st.cache_resource.clear()
                    st.rerun()
            
            # Cargar datos
            brokers = storage.get_brokers()
            platforms = storage.get_platforms()
            accounts = storage.get_broker_accounts()
            
            # Sección: Resumen de Cuentas
            st.subheader("💼 Tus Cuentas de Trading")
            
            if accounts:
                # Filtros simplificados para evitar layouts anidados que puedan romper
                col_f1, col_f2 = st.columns(2)
                with col_f1:
                    filter_status = st.selectbox("Estado", ["Todas", "Habilitadas", "Deshabilitadas"], key="f_status")
                with col_f2:
                    filter_type = st.selectbox("Tipo", ["Todas", "DEMO", "REAL"], key="f_type")
                
                # Aplicar filtros
                filtered_accounts = accounts
                if filter_status == "Habilitadas":
                    filtered_accounts = [a for a in filtered_accounts if a['enabled'] == 1]
                elif filter_status == "Deshabilitadas":
                    filtered_accounts = [a for a in filtered_accounts if a['enabled'] == 0]
                
                if filter_type != "Todas":
                    filtered_accounts = [a for a in filtered_accounts if a['account_type'] == filter_type.lower()]
                
                st.markdown(f"**{len(filtered_accounts)} cuenta(s) encontrada(s)**")
                
                # Mostrar cuentas
                for account in filtered_accounts:
                    account_id = account['account_id']
                    broker_id = account['broker_id']
                    platform_id = account['platform_id']
                    account_name = account['account_name']
                    account_type = account['account_type']
                    enabled = bool(account['enabled'])
                    
                    status_emoji = "🟢" if enabled else "🔴"
                    type_emoji = "🎮" if account_type == "demo" else "💰"
                    
                    with st.expander(f"{status_emoji} {type_emoji} **{account_name}** ({broker_id})"):
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**ID:** `{account_id}`")
                            st.write(f"**Platform:** {platform_id}")
                            st.write(f"**Login:** {account.get('login', 'N/A')}")
                        
                        with col2:
                            if st.button("🗑️ Eliminar", key=f"del_{account_id}"):
                                storage.delete_account(account_id)
                                st.success("Eliminado")
                                st.rerun()
                            
                            new_state = st.checkbox("Habilitada", value=enabled, key=f"en_{account_id}")
                            if new_state != enabled:
                                storage.update_account_enabled(account_id, new_state)
                                st.rerun()

            else:
                st.info("No tienes cuentas configuradas.")
            
            st.markdown("---")
            
            # Botón para agregar nueva cuenta
            if st.checkbox("➕ Agregar Nueva Cuenta", key="show_add_form"):
                st.subheader("Nueva Cuenta")
                
                with st.form("add_account_form"):
                    col1, col2 = st.columns(2)
                    with col1:
                        b_sel = st.selectbox("Broker", [b['broker_id'] for b in brokers])
                        p_sel = st.selectbox("Plataforma", [p['platform_id'] for p in platforms])
                    
                    with col2:
                        name = st.text_input("Nombre de Cuenta")
                        a_type = st.selectbox("Tipo", ["demo", "real"])
                    
                    col3, col4 = st.columns(2)
                    with col3:
                        login = st.text_input("Login (Cuenta)", help="Tu número de cuenta de MT5")
                        server = st.text_input("Servidor", help="Ejemplo: XMGlobal-Demo")
                    with col4:
                        pwd = st.text_input("Password", type="password", help="Tu contraseña se guardará de forma encriptada en la base de datos.")
                        st.caption("ℹ️ El Broker ID se asigna según tu selección arriba (ej. XM).")
                    
                    if st.form_submit_button("💾 Guardar Cuenta"):
                        if name and login:
                            storage.save_broker_account(
                                broker_id=b_sel,
                                platform_id=p_sel,
                                account_name=name,
                                account_type=a_type,
                                server=server,
                                login=login,
                                password=pwd,
                                enabled=True
                            )
                            st.success("Cuenta guardada correctamente")
                            st.rerun()
                        else:
                            st.error("Nombre y Login son obligatorios")
            
            # Sección: Información de Brokers
            st.markdown("---")
            if st.checkbox("📚 Ver Catálogo de Brokers", key="show_catalog"):
                st.table(pd.DataFrame(brokers)[['name', 'type', 'website']])

        except Exception as e:
            st.error("Error visualizando configuración")
            st.exception(e)
    
    # TAB: Gestión de Instrumentos
    elif menu_selection == "🎯 Gestión de Instrumentos":
        st.header("🎯 Gestión de Instrumentos y Filtrado por Score")
        
        st.markdown("""
        Configura qué instrumentos están habilitados para trading y los scores mínimos requeridos por categoría.
        Los instrumentos con score por debajo del umbral configurado serán rechazados automáticamente.
        """)
        
        try:
            instrument_manager = get_instrument_manager()
            
            # Información general del sistema
            st.markdown("---")
            col1, col2, col3 = st.columns(3)
            
            enabled_symbols = instrument_manager.get_enabled_symbols()
            total_symbols = len(instrument_manager.symbol_cache)
            
            with col1:
                st.metric("Total Símbolos", total_symbols)
            with col2:
                st.metric("Habilitados", len(enabled_symbols))
            with col3:
                st.metric("Deshabilitados", total_symbols - len(enabled_symbols))
            
            st.markdown("---")
            
            # Tabs por mercado
            market_tabs = st.tabs(["💱 FOREX", "₿ CRYPTO", "📈 STOCKS", "🔮 FUTURES", "⚙️ Global Settings"])
            
            # TAB 1: FOREX
            with market_tabs[0]:
                st.subheader("💱 Mercado FOREX")
                
                if "FOREX" in instrument_manager.config:
                    forex_config = instrument_manager.config["FOREX"]
                    
                    for subcategory, settings in forex_config.items():
                        with st.expander(f"📊 {subcategory.upper()}", expanded=True):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.markdown(f"**Descripción:** {settings.get('description', 'N/A')}")
                                
                                # Mostrar instrumentos
                                instruments = settings.get('instruments', [])
                                if instruments:
                                    st.caption(f"**Instrumentos ({len(instruments)}):**")
                                    st.code(", ".join(instruments[:10]) + ("..." if len(instruments) > 10 else ""))
                            
                            with col2:
                                # Estado actual
                                enabled = settings.get('enabled', False)
                                min_score = settings.get('min_score', 75.0)
                                risk_mult = settings.get('risk_multiplier', 1.0)
                                
                                st.metric("Estado", "✅ Habilitado" if enabled else "🔴 Deshabilitado")
                                st.metric("Score Mínimo", f"{min_score:.0f}")
                                st.metric("Risk Multiplier", f"{risk_mult:.1f}x")
                            
                            # Configuración editable
                            st.markdown("---")
                            with st.form(key=f"forex_{subcategory}"):
                                col_a, col_b, col_c = st.columns(3)
                                
                                with col_a:
                                    new_enabled = st.checkbox(
                                        "Habilitar", 
                                        value=enabled,
                                        key=f"forex_{subcategory}_enabled"
                                    )
                                
                                with col_b:
                                    new_min_score = st.slider(
                                        "Score Mínimo",
                                        min_value=0,
                                        max_value=100,
                                        value=int(min_score),
                                        step=5,
                                        key=f"forex_{subcategory}_score"
                                    )
                                
                                with col_c:
                                    new_risk_mult = st.slider(
                                        "Risk Multiplier",
                                        min_value=0.1,
                                        max_value=2.0,
                                        value=float(risk_mult),
                                        step=0.1,
                                        key=f"forex_{subcategory}_risk"
                                    )
                                
                                submitted = st.form_submit_button("💾 Guardar Cambios")
                                
                                if submitted:
                                    # Actualizar config en memoria (por ahora)
                                    settings['enabled'] = new_enabled
                                    settings['min_score'] = float(new_min_score)
                                    settings['risk_multiplier'] = float(new_risk_mult)
                                    
                                    # Guardar a JSON
                                    config_path = Path("config/instruments.json")
                                    with open(config_path, 'w', encoding='utf-8') as f:
                                        json.dump(instrument_manager.config, f, indent=2, ensure_ascii=False)
                                    
                                    # Limpiar cache para forzar recarga
                                    st.cache_resource.clear()
                                    
                                    st.success(f"✅ Configuración guardada para FOREX/{subcategory}")
                                    st.info("🔄 Reiniciando InstrumentManager...")
                                    st.rerun()
                else:
                    st.warning("No hay configuración FOREX disponible")
            
            # TAB 2: CRYPTO
            with market_tabs[1]:
                st.subheader("₿ Mercado CRYPTO")
                
                if "CRYPTO" in instrument_manager.config:
                    crypto_config = instrument_manager.config["CRYPTO"]
                    
                    for subcategory, settings in crypto_config.items():
                        with st.expander(f"📊 {subcategory.upper()}", expanded=True):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.markdown(f"**Descripción:** {settings.get('description', 'N/A')}")
                                
                                instruments = settings.get('instruments', [])
                                if instruments:
                                    st.caption(f"**Instrumentos ({len(instruments)}):**")
                                    st.code(", ".join(instruments))
                            
                            with col2:
                                enabled = settings.get('enabled', False)
                                min_score = settings.get('min_score', 75.0)
                                risk_mult = settings.get('risk_multiplier', 1.0)
                                
                                st.metric("Estado", "✅ Habilitado" if enabled else "🔴 Deshabilitado")
                                st.metric("Score Mínimo", f"{min_score:.0f}")
                                st.metric("Risk Multiplier", f"{risk_mult:.1f}x")
                            
                            st.markdown("---")
                            with st.form(key=f"crypto_{subcategory}"):
                                col_a, col_b, col_c = st.columns(3)
                                
                                with col_a:
                                    new_enabled = st.checkbox("Habilitar", value=enabled, key=f"crypto_{subcategory}_enabled")
                                with col_b:
                                    new_min_score = st.slider("Score Mínimo", 0, 100, int(min_score), 5, key=f"crypto_{subcategory}_score")
                                with col_c:
                                    new_risk_mult = st.slider("Risk Multiplier", 0.1, 2.0, float(risk_mult), 0.1, key=f"crypto_{subcategory}_risk")
                                
                                submitted = st.form_submit_button("💾 Guardar Cambios")
                                
                                if submitted:
                                    settings['enabled'] = new_enabled
                                    settings['min_score'] = float(new_min_score)
                                    settings['risk_multiplier'] = float(new_risk_mult)
                                    
                                    config_path = Path("config/instruments.json")
                                    with open(config_path, 'w', encoding='utf-8') as f:
                                        json.dump(instrument_manager.config, f, indent=2, ensure_ascii=False)
                                    
                                    st.cache_resource.clear()
                                    st.success(f"✅ Configuración guardada para CRYPTO/{subcategory}")
                                    st.rerun()
                else:
                    st.warning("No hay configuración CRYPTO disponible")
            
            # TAB 3: STOCKS
            with market_tabs[2]:
                st.subheader("📈 Mercado STOCKS")
                
                if "STOCKS" in instrument_manager.config:
                    stocks_config = instrument_manager.config["STOCKS"]
                    
                    for subcategory, settings in stocks_config.items():
                        with st.expander(f"📊 {subcategory.upper()}", expanded=True):
                            enabled = settings.get('enabled', False)
                            min_score = settings.get('min_score', 75.0)
                            
                            st.markdown(f"**Descripción:** {settings.get('description', 'N/A')}")
                            st.metric("Estado", "✅ Habilitado" if enabled else "🔴 Deshabilitado")
                            
                            with st.form(key=f"stocks_{subcategory}"):
                                new_enabled = st.checkbox("Habilitar", value=enabled)
                                new_min_score = st.slider("Score Mínimo", 0, 100, int(min_score), 5)
                                
                                submitted = st.form_submit_button("💾 Guardar")
                                
                                if submitted:
                                    settings['enabled'] = new_enabled
                                    settings['min_score'] = float(new_min_score)
                                    
                                    config_path = Path("config/instruments.json")
                                    with open(config_path, 'w', encoding='utf-8') as f:
                                        json.dump(instrument_manager.config, f, indent=2, ensure_ascii=False)
                                    
                                    st.cache_resource.clear()
                                    st.success(f"✅ Guardado STOCKS/{subcategory}")
                                    st.rerun()
                else:
                    st.warning("No hay configuración STOCKS disponible")
            
            # TAB 4: FUTURES
            with market_tabs[3]:
                st.subheader("🔮 Mercado FUTURES")
                
                if "FUTURES" in instrument_manager.config:
                    futures_config = instrument_manager.config["FUTURES"]
                    
                    for subcategory, settings in futures_config.items():
                        with st.expander(f"📊 {subcategory.upper()}", expanded=True):
                            col1, col2 = st.columns([2, 1])
                            
                            with col1:
                                st.markdown(f"**Descripción:** {settings.get('description', 'N/A')}")
                                instruments = settings.get('instruments', [])
                                if instruments:
                                    st.code(", ".join(instruments))
                            
                            with col2:
                                enabled = settings.get('enabled', False)
                                min_score = settings.get('min_score', 75.0)
                                
                                st.metric("Estado", "✅ Habilitado" if enabled else "🔴 Deshabilitado")
                                st.metric("Score Mínimo", f"{min_score:.0f}")
                            
                            with st.form(key=f"futures_{subcategory}"):
                                new_enabled = st.checkbox("Habilitar", value=enabled)
                                new_min_score = st.slider("Score Mínimo", 0, 100, int(min_score), 5)
                                
                                submitted = st.form_submit_button("💾 Guardar")
                                
                                if submitted:
                                    settings['enabled'] = new_enabled
                                    settings['min_score'] = float(new_min_score)
                                    
                                    config_path = Path("config/instruments.json")
                                    with open(config_path, 'w', encoding='utf-8') as f:
                                        json.dump(instrument_manager.config, f, indent=2, ensure_ascii=False)
                                    
                                    st.cache_resource.clear()
                                    st.success(f"✅ Guardado FUTURES/{subcategory}")
                                    st.rerun()
                else:
                    st.warning("No hay configuración FUTURES disponible")
            
            # TAB 5: Global Settings
            with market_tabs[4]:
                st.subheader("⚙️ Configuración Global")
                
                global_settings = instrument_manager.config.get("_global_settings", {})
                
                st.markdown("### Defaults para Instrumentos Desconocidos")
                
                with st.form(key="global_settings"):
                    default_min_score = st.slider(
                        "Score Mínimo por Defecto",
                        min_value=0,
                        max_value=100,
                        value=int(global_settings.get('default_min_score', 80)),
                        step=5,
                        help="Score mínimo para instrumentos no clasificados"
                    )
                    
                    default_risk_mult = st.slider(
                        "Risk Multiplier por Defecto",
                        min_value=0.1,
                        max_value=2.0,
                        value=float(global_settings.get('default_risk_multiplier', 0.8)),
                        step=0.1,
                        help="Multiplicador de riesgo para instrumentos desconocidos"
                    )
                    
                    unknown_action = st.selectbox(
                        "Acción para Instrumentos Desconocidos",
                        options=["reject", "allow"],
                        index=0 if global_settings.get('unknown_instrument_action') == 'reject' else 1,
                        help="'reject' = rechazar automáticamente, 'allow' = permitir con defaults conservadores"
                    )
                    
                    log_rejections = st.checkbox(
                        "Registrar Rechazos en Logs",
                        value=global_settings.get('log_all_rejections', True),
                        help="Guardar en logs todos los setups rechazados por score bajo"
                    )
                    
                    submitted = st.form_submit_button("💾 Guardar Configuración Global")
                    
                    if submitted:
                        global_settings['default_min_score'] = float(default_min_score)
                        global_settings['default_risk_multiplier'] = float(default_risk_mult)
                        global_settings['unknown_instrument_action'] = unknown_action
                        global_settings['log_all_rejections'] = log_rejections
                        
                        instrument_manager.config['_global_settings'] = global_settings
                        
                        config_path = Path("config/instruments.json")
                        with open(config_path, 'w', encoding='utf-8') as f:
                            json.dump(instrument_manager.config, f, indent=2, ensure_ascii=False)
                        
                        st.cache_resource.clear()
                        st.success("✅ Configuración global guardada correctamente")
                        st.rerun()
                
                st.markdown("---")
                st.markdown("### Información del Sistema")
                st.info(f"""
                **Archivo de Configuración:** `config/instruments.json`  
                **Total de Categorías:** {sum(len(v) for k, v in instrument_manager.config.items() if not k.startswith('_'))}  
                **Símbolos en Cache:** {len(instrument_manager.symbol_cache)}  
                **Política Actual:** {global_settings.get('fallback_behavior', 'conservative')}
                """)
        
        except Exception as e:
            st.error(f"Error cargando gestión de instrumentos: {e}")
            st.exception(e)


if __name__ == "__main__":
    main()
