"""
UI Mapping Service - Transformación de Datos Técnicos a JSON para Frontend

Responsabilidad:
  - Convertir salidas técnicas de sensores (Market Structure, Fibonacci, FVG, etc.)
    a formato JSON compatible con librerías charting (Chart.js, TradingView, etc.)
  - Proporcionar objetos de dibujo (drawings) con coordenadas pixel, colores, estilos
  - Emitir eventos en tiempo real vía WebSocket o API REST para UI

Features:
  - Mapeo automático de coordenadas (precio → pixel vertical, timeframe → pixel horizontal)
  - Generador de Drawing Objects (líneas, zonas sombreadas, etiquetas)
  - Compatibilidad con sistema de Capas (Layers) de Terminal 2.0
  - Cache de elementos para optimización de performance

TRACE_ID: EXEC-ORCHESTRA-001
"""

import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class LayerType(Enum):
    """Enumeration of visual layers in Trader Page."""
    STRUCTURE = "structure"
    LIQUIDITY = "liquidity"
    MOVING_AVERAGES = "moving_averages"
    PATTERNS = "patterns"
    TARGETS = "targets"
    RISK = "risk"


class DrawingElementType(Enum):
    """Types of drawing elements."""
    LINE = "line"
    ZONE = "zone"
    LABEL = "label"
    MARKER = "marker"
    TOOLTIP = "tooltip"


@dataclass
class DrawingCoordinate:
    """Coordenada (precio x tiempo) para dibujo."""
    price: float  # Precio en unidades de instrumento
    time_index: int  # Índice de vela (0 = más antiguo)
    
    def to_dict(self) -> Dict[str, Any]:
        return {"price": self.price, "time_index": self.time_index}


@dataclass
class DrawingElement:
    """Elemento visual básico para renderizar en chart."""
    element_id: str  # Identificador único
    layer: LayerType  # Qué capa visual
    element_type: DrawingElementType  # Tipo de elemento
    coordinates: List[DrawingCoordinate]  # Puntos del elemento
    properties: Dict[str, Any]  # Color, grosor, estilo, etc.
    visible: bool = True
    z_index: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "layer": self.layer.value,
            "type": self.element_type.value,
            "coordinates": [c.to_dict() for c in self.coordinates],
            "properties": self.properties,
            "visible": self.visible,
            "z_index": self.z_index
        }


class UIDrawingFactory:
    """Factory para crear elementos de dibujo desde datos técnicos."""
    
    # Paleta de colores institucional (MANIFESTO Sección VI)
    COLORS = {
        "hh_hl_bullish": "#00FFFF",      # Cyan line
        "lh_ll_bearish": "#FF00FF",      # Magenta line
        "bos_break": "#00FFFF",          # Cyan neón
        "breaker_block": "#2A2A2A",      # Dark gray
        "fvg": "#1E90FF",                # Light blue (semitransparent)
        "imbalance": "#FF8C00",          # Orange tenuue
        "sma20": "#00FFFF",              # Cyan
        "sma200": "#FF8C00",             # Orange
        "tp1_fib127": "#1A9A9A",         # Dark cyan
        "tp2_fib618": "#00FFFF",         # Bright cyan
        "stop_loss": "#FF3131",          # Neon red
        "rejection_tail": "#E0E0E0",     # Bright gray
        "elephant_bull": "#00FF00",      # Bright green
        "elephant_bear": "#FF3131",      # Neon red
    }
    
    # Estilos de líneas
    STYLES = {
        "solid": {"pattern": "solid", "width": 1.5},
        "dashed": {"pattern": "dashed", "width": 1.5},
        "thick_solid": {"pattern": "solid", "width": 2.0},
        "thick_dashed": {"pattern": "dashed", "width": 2.0},
        "thin_solid": {"pattern": "solid", "width": 1.0},
    }
    
    @staticmethod
    def create_hh_hl_lines(
        hh_points: List[Tuple[int, float]],  # [(time_index, price), ...]
        hl_points: List[Tuple[int, float]],
        name: str = "Structure_HH_HL"
    ) -> List[DrawingElement]:
        """
        Crea líneas de HH (Higher High) y HL (Higher Low) para estructura alcista.
        
        Args:
            hh_points: Puntos de máximos más altos
            hl_points: Puntos de mínimos más altos
            name: Nombre de la estructura
            
        Returns:
            Lista de DrawingElements (líneas)
        """
        elements = []
        
        # Línea HH (máximos conectados)
        if len(hh_points) >= 2:
            hh_coords = [DrawingCoordinate(price=p[1], time_index=p[0]) for p in hh_points]
            hh_element = DrawingElement(
                element_id=f"{name}_HH",
                layer=LayerType.STRUCTURE,
                element_type=DrawingElementType.LINE,
                coordinates=hh_coords,
                properties={
                    "color": UIDrawingFactory.COLORS["hh_hl_bullish"],
                    "style": UIDrawingFactory.STYLES["solid"],
                    "label": f"HH{len(hh_points)}",
                    "description": "Higher Highs: Línea de máximos consecutivos más altos. Confirma tendencia alcista institucional."
                },
                z_index=20  # Líneas base
            )
            elements.append(hh_element)
        
        # Línea HL (mínimos conectados)
        if len(hl_points) >= 2:
            hl_coords = [DrawingCoordinate(price=p[1], time_index=p[0]) for p in hl_points]
            hl_element = DrawingElement(
                element_id=f"{name}_HL",
                layer=LayerType.STRUCTURE,
                element_type=DrawingElementType.LINE,
                coordinates=hl_coords,
                properties={
                    "color": UIDrawingFactory.COLORS["hh_hl_bullish"],
                    "style": UIDrawingFactory.STYLES["solid"],
                    "label": f"HL{len(hl_points)}",
                    "description": "Higher Lows: Línea de mínimos consecutivos más altos. Valida fuerza de tendencia alcista."
                },
                z_index=20
            )
            elements.append(hl_element)
        
        return elements
    
    @staticmethod
    def create_breaker_block(
        breaker_high: float,
        breaker_low: float,
        start_time_index: int,
        end_time_index: int,
        name: str = "BreakBlock"
    ) -> DrawingElement:
        """
        Crea sombreado de Breaker Block (zona de quiebre).
        
        Args:
            breaker_high: Precio alto de la zona
            breaker_low: Precio bajo de la zona
            start_time_index: Índice de vela inicial
            end_time_index: Índice de vela final
            
        Returns:
            DrawingElement de sombreado
        """
        # Rectángulo: top-left, top-right, bottom-right, bottom-left
        coords = [
            DrawingCoordinate(price=breaker_high, time_index=start_time_index),
            DrawingCoordinate(price=breaker_high, time_index=end_time_index),
            DrawingCoordinate(price=breaker_low, time_index=end_time_index),
            DrawingCoordinate(price=breaker_low, time_index=start_time_index),
        ]
        
        return DrawingElement(
            element_id=name,
            layer=LayerType.STRUCTURE,
            element_type=DrawingElementType.ZONE,
            coordinates=coords,
            properties={
                "color": UIDrawingFactory.COLORS["breaker_block"],
                "opacity": 0.5,
                "border_style": "dashed",
                "border_color": "#FFFFFF",
                "tooltip": f"Breaker Block: {breaker_high:.5f} - {breaker_low:.5f} [{abs(breaker_high - breaker_low) * 10000:.0f} pips]",
                "description": "Breaker Block: Zona de confirmación donde ocurrió el quiebre de estructura. Stop Loss crítico está aquí."
            },
            z_index=10  # Fondos
        )
    
    @staticmethod
    def create_fvg_zone(
        fvg_high: float,
        fvg_low: float,
        start_time_index: int,
        end_time_index: int,
        name: str = "FVG"
    ) -> DrawingElement:
        """
        Crea zona Fair Value Gap (desequilibrio a llenar).
        
        Args:
            fvg_high: Precio alto del gap
            fvg_low: Precio bajo del gap
            start_time_index: Índice inicial
            end_time_index: Índice final
            
        Returns:
            DrawingElement de sombreado
        """
        coords = [
            DrawingCoordinate(price=fvg_high, time_index=start_time_index),
            DrawingCoordinate(price=fvg_high, time_index=end_time_index),
            DrawingCoordinate(price=fvg_low, time_index=end_time_index),
            DrawingCoordinate(price=fvg_low, time_index=start_time_index),
        ]
        
        return DrawingElement(
            element_id=name,
            layer=LayerType.LIQUIDITY,
            element_type=DrawingElementType.ZONE,
            coordinates=coords,
            properties={
                "color": UIDrawingFactory.COLORS["fvg"],
                "opacity": 0.3,
                "tooltip": f"Fair Value Gap: {fvg_high:.5f} - {fvg_low:.5f}",
                "description": "Fair Value Gap (FVG): Desequilibrio de precio que el Smart Money busca llenar. Zona de absorción institucional."
            },
            z_index=10
        )
    
    @staticmethod
    def create_imbalance_zone(
        imb_high: float,
        imb_low: float,
        start_time_index: int,
        end_time_index: int,
        name: str = "Imbalance"
    ) -> DrawingElement:
        """Crea zona de desequilibrio de volumen (liquidez)."""
        coords = [
            DrawingCoordinate(price=imb_high, time_index=start_time_index),
            DrawingCoordinate(price=imb_high, time_index=end_time_index),
            DrawingCoordinate(price=imb_low, time_index=end_time_index),
            DrawingCoordinate(price=imb_low, time_index=start_time_index),
        ]
        
        return DrawingElement(
            element_id=name,
            layer=LayerType.LIQUIDITY,
            element_type=DrawingElementType.ZONE,
            coordinates=coords,
            properties={
                "color": UIDrawingFactory.COLORS["imbalance"],
                "opacity": 0.3,
                "label": "LIQ",
                "tooltip": f"Imbalance Zone (seek liquidez)",
                "description": "Imbalance (Desequilibrio): Zona donde el delta de volumen es extremo. Smart Money ejecuta liquidaciones aquí."
            },
            z_index=10
        )
    
    @staticmethod
    def create_moving_average_line(
        ma_points: List[Tuple[int, float]],
        ma_period: int,
        name: str = "SMA"
    ) -> DrawingElement:
        """
        Crea línea de media móvil.
        
        Args:
            ma_points: Puntos [(time_index, sma_value), ...]
            ma_period: Período (20, 200, etc.)
            name: Nombre identificador
        """
        color = UIDrawingFactory.COLORS["sma20"] if ma_period <= 50 else UIDrawingFactory.COLORS["sma200"]
        
        coords = [DrawingCoordinate(price=p[1], time_index=p[0]) for p in ma_points]
        
        return DrawingElement(
            element_id=f"{name}_{ma_period}",
            layer=LayerType.MOVING_AVERAGES,
            element_type=DrawingElementType.LINE,
            coordinates=coords,
            properties={
                "color": color,
                "style": UIDrawingFactory.STYLES["solid"],
                "label": f"SMA{ma_period}",
                "description": f"SMA{ma_period}: Media móvil de {ma_period} períodos. Soporte dinámico en pullbacks y reversal zones."
            },
            z_index=20
        )
    
    @staticmethod
    def create_target_line(
        target_price: float,
        timeframe_start: int,
        timeframe_end: int,
        target_type: str = "TP1",
        name: str = "Target"
    ) -> DrawingElement:
        """
        Crea línea de objetivo (TP1, TP2).
        
        Args:
            target_price: Precio del objetivo
            timeframe_start: Índice de inicio
            timeframe_end: Índice de fin
            target_type: "TP1" (FIB127) o "TP2" (FIB618)
            name: Identificador
        """
        color = UIDrawingFactory.COLORS["tp1_fib127"] if target_type == "TP1" else UIDrawingFactory.COLORS["tp2_fib618"]
        
        coords = [
            DrawingCoordinate(price=target_price, time_index=timeframe_start),
            DrawingCoordinate(price=target_price, time_index=timeframe_end)
        ]
        
        return DrawingElement(
            element_id=f"{name}_{target_type}",
            layer=LayerType.TARGETS,
            element_type=DrawingElementType.LINE,
            coordinates=coords,
            properties={
                "color": color,
                "style": UIDrawingFactory.STYLES["thick_dashed"],
                "label": f"{target_type} {target_price:.5f}",
                "description": f"{target_type}: Objetivo de ganancia basado en extensión Fibonacci. TP1=127%, TP2=618% Golden Ratio."
            },
            z_index=40
        )
    
    @staticmethod
    def create_stop_loss_line(
        sl_price: float,
        timeframe_start: int,
        timeframe_end: int,
        risk_pips: float,
        name: str = "StopLoss"
    ) -> DrawingElement:
        """
        Crea línea de Stop Loss (riesgo definitivo).
        
        Args:
            sl_price: Precio del SL
            timeframe_start: Índice inicio
            timeframe_end: Índice fin
            risk_pips: Riesgo en pips
            name: Identificador
        """
        coords = [
            DrawingCoordinate(price=sl_price, time_index=timeframe_start),
            DrawingCoordinate(price=sl_price, time_index=timeframe_end)
        ]
        
        return DrawingElement(
            element_id=name,
            layer=LayerType.RISK,
            element_type=DrawingElementType.LINE,
            coordinates=coords,
            properties={
                "color": UIDrawingFactory.COLORS["stop_loss"],
                "style": {"pattern": "solid", "width": 2.0, "gradient": True},
                "tooltip": f"SL: {sl_price:.5f} | Risk: {risk_pips:.0f} pips",
                "animation": "none",
                "description": "Stop Loss: Nivel de cierre obligatorio por riesgo máximo. Protege el 1% capital por operación."
            },
            z_index=30
        )
    
    @staticmethod
    def create_label(
        price: float,
        time_index: int,
        text: str,
        layer: LayerType,
        name: str = "Label"
    ) -> DrawingElement:
        """Crea etiqueta de texto en el chart."""
        return DrawingElement(
            element_id=name,
            layer=layer,
            element_type=DrawingElementType.LABEL,
            coordinates=[DrawingCoordinate(price=price, time_index=time_index)],
            properties={
                "text": text,
                "color": "#FFFFFF",
                "font_size": 10,
                "background": "rgba(0, 0, 0, 0.5)"
            },
            z_index=50
        )


class UITraderPageState:
    """Estado global de la Página Trader con todos los elementos visuales.
    
    EXEC-UI-VALIDATION-FIX: Diferencia datos de Análisis (prioridad alta)
    de datos de Trader para renderizar en ambas pestañas simultáneamente.
    """
    
    def __init__(self):
        self.elements: Dict[str, DrawingElement] = {}  # element_id -> DrawingElement
        self.active_strategies: Dict[str, str] = {}  # asset -> strategy_name
        self.visible_layers: set = {
            LayerType.STRUCTURE,
            LayerType.LIQUIDITY,
            LayerType.MOVING_AVERAGES,
            LayerType.TARGETS
        }
        self.timestamp = datetime.now()
        self.priority: str = "normal"  # "normal" o "high" para datos de Análisis
        self.analysis_signals: Dict[str, Any] = {}  # Datos de análisis para pestaña Análisis
        self.analysis_detected: bool = False  # Indica si hay datos detectados
    
    def add_element(self, element: DrawingElement) -> None:
        """Agrega elemento a la página."""
        self.elements[element.element_id] = element
    
    def remove_element(self, element_id: str) -> None:
        """Elimina elemento."""
        if element_id in self.elements:
            del self.elements[element_id]
    
    def toggle_layer(self, layer: LayerType) -> None:
        """Activa/desactiva una capa visual."""
        if layer in self.visible_layers:
            self.visible_layers.remove(layer)
        else:
            self.visible_layers.add(layer)
        
        logger.info(f"[UI] Layer {layer.value} toggled. Visible: {[l.value for l in self.visible_layers]}")
    
    def get_visible_elements(self) -> List[DrawingElement]:
        """Retorna solo elementos en capas visibles, ordenados por z_index."""
        visible = [
            e for e in self.elements.values()
            if e.layer in self.visible_layers and e.visible
        ]
        return sorted(visible, key=lambda e: e.z_index)
    
    def to_json(self) -> Dict[str, Any]:
        """Serializa estado a JSON para WebSocket/API."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "active_strategies": self.active_strategies,
            "visible_layers": [l.value for l in self.visible_layers],
            "elements": [e.to_dict() for e in self.get_visible_elements()],
            "element_count": len(self.elements),
            "priority": self.priority,
            "analysis_signals": self.analysis_signals,
            "analysis_detected": self.analysis_detected
        }


class UIMappingService:
    """
    Servicio central de mapeo de datos técnicos a UI.
    
    Funciones:
    1. Recibe datos de sensores (MarketStructureAnalyzer, etc.)
    2. Convierte a DrawingElements
    3. Mantiene estado de página (TraderPageState)
    4. Emite eventos vía WebSocket/API
    """
    
    def __init__(self, socket_service=None):
        """
        Inicializa el servicio de UI.
        
        Args:
            socket_service: SocketService para emitir eventos en tiempo real
        """
        self.socket_service = socket_service
        self.trader_page_state = UITraderPageState()
        self.factory = UIDrawingFactory()
        
        logger.info("[UI_MAPPING] Service initialized")
    
    async def emit_trader_page_update(self) -> None:
        """Emite actualización de página Trader vía WebSocket.
        
        EXEC-UI-VALIDATION-FIX: Emite con emit_event() correctamente,
        con esquema JSON estándar y flag de prioridad para Análisis.
        """
        if not self.socket_service:
            logger.error("[UI_MAPPING] SocketService is None. Cannot emit trader page update.")
            return
        
        page_json = self.trader_page_state.to_json()
        
        # Emitir con prioridad alta si hay datos de análisis
        event_type = "ANALYSIS_UPDATE" if self.trader_page_state.priority == "high" else "TRADER_PAGE_UPDATE"
        
        logger.info(
            f"[UI_MAPPING] EMITTING {event_type} | "
            f"priority={page_json.get('priority')} | "
            f"analysis_detected={page_json.get('analysis_detected')} | "
            f"analysis_signals={len(page_json.get('analysis_signals', {}))} | "
            f"elements={page_json.get('element_count')} | "
            f"payload_size={len(str(page_json))} bytes"
        )
        
        try:
            await self.socket_service.emit_event(
                event_type=event_type,
                payload=page_json
            )
            logger.debug(f"[UI_MAPPING][✅] {event_type} emitted successfully to {self.socket_service.get_connection_count()} clients")
        except Exception as e:
            logger.error(f"[UI_MAPPING] Exception in emit_event: {type(e).__name__}: {e}", exc_info=True)
    
    def add_structure_signal(self, asset: str, structure_data: Dict[str, Any]) -> None:
        """
        Agrega elementos de estructura detectada (SEÑAL DE ANÁLISIS).
        
        EXEC-UI-VALIDATION-FIX: Esta es una señal de ANÁLISIS (prioridad alta).
        Se registra en analysis_signals para mostrar en pestaña Análisis Y Trader.
        
        Args:
            asset: Par de divisas
            structure_data: Dict con HH/HL/LH/LL points/indices, structure_type, etc.
        """
        try:
            # Support both old format (hh_points) and new format (hh_indices)
            hh_indices = structure_data.get("hh_indices", [])
            hl_indices = structure_data.get("hl_indices", [])
            lh_indices = structure_data.get("lh_indices", [])
            ll_indices = structure_data.get("ll_indices", [])
            structure_type = structure_data.get("structure_type", "UNKNOWN")
            confidence = structure_data.get("confidence", "unknown")
            is_valid = structure_data.get("is_valid", False)
            
            # Check if we have any pivot data
            has_pivots = any([hh_indices, hl_indices, lh_indices, ll_indices])
            
            if not has_pivots:
                logger.warning(f"[UI_MAPPING] No pivots detected for {asset}")
                return
            
            # Log the structure signal details
            logger.debug(
                f"[UI_MAPPING] Structure signal: {asset} {structure_type} "
                f"(HH={len(hh_indices)}, HL={len(hl_indices)}, "
                f"LH={len(lh_indices)}, LL={len(ll_indices)}, confidence={confidence})"
            )
            
            # EXEC-UI-VALIDATION-FIX: Marcar como ANÁLISIS - Prioridad Alta
            self.trader_page_state.priority = "high"
            self.trader_page_state.analysis_detected = True
            self.trader_page_state.analysis_signals[f"{asset}_structure"] = {
                "type": "structure",
                "asset": asset,
                "structure_type": structure_type,
                "hh_count": len(hh_indices),
                "hl_count": len(hl_indices),
                "lh_count": len(lh_indices),
                "ll_count": len(ll_indices),
                "valid": is_valid,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"[UI_MAPPING] Added structure signal for {asset}: {structure_type} ({confidence})")
        
        except Exception as e:
            logger.error(f"[UI_MAPPING] Error adding structure signal: {e}", exc_info=True)
    
    def add_target_signals(self, asset: str, tp1: float, tp2: float, start_idx: int, end_idx: int) -> None:
        """Agrega líneas de objetivos (TP1, TP2) - SEÑAL DE ANÁLISIS.
        
        EXEC-UI-VALIDATION-FIX: Prioridad alta, para Análisis y Trader.
        """
        try:
            if not isinstance(tp1, (int, float)) or not isinstance(tp2, (int, float)):
                logger.warning(f"[UI_MAPPING] Invalid TP values for {asset}: TP1={tp1}, TP2={tp2}")
                return
            
            tp1_elem = self.factory.create_target_line(tp1, start_idx, end_idx, "TP1", f"{asset}_TP1")
            tp2_elem = self.factory.create_target_line(tp2, start_idx, end_idx, "TP2", f"{asset}_TP2")
            
            self.trader_page_state.add_element(tp1_elem)
            self.trader_page_state.add_element(tp2_elem)
            
            # EXEC-UI-VALIDATION-FIX: Marcar como ANÁLISIS - Prioridad Alta
            self.trader_page_state.priority = "high"
            self.trader_page_state.analysis_detected = True
            self.trader_page_state.analysis_signals[f"{asset}_targets"] = {
                "type": "targets",
                "asset": asset,
                "tp1": tp1,
                "tp2": tp2,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(
                f"[UI_MAPPING] Added ANALYSIS targets for {asset}: "
                f"TP1={tp1:.5f}, TP2={tp2:.5f} | priority=HIGH"
            )
        
        except Exception as e:
            logger.error(f"[UI_MAPPING] Exception in add_target_signals({asset}): {str(e)}")
    
    def add_stop_loss(self, asset: str, sl_price: float, risk_pips: float, start_idx: int, end_idx: int) -> None:
        """Agrega línea de Stop Loss - SEÑAL DE ANÁLISIS.
        
        EXEC-UI-VALIDATION-FIX: Stop Loss es crítico, prioridad alta.
        """
        try:
            if not isinstance(sl_price, (int, float)) or sl_price <= 0:
                logger.warning(f"[UI_MAPPING] Invalid SL price for {asset}: {sl_price}")
                return
            
            sl_elem = self.factory.create_stop_loss_line(sl_price, start_idx, end_idx, risk_pips, f"{asset}_SL")
            self.trader_page_state.add_element(sl_elem)
            
            # EXEC-UI-VALIDATION-FIX: Marcar como ANÁLISIS - Prioridad Alta
            self.trader_page_state.priority = "high"
            self.trader_page_state.analysis_detected = True
            self.trader_page_state.analysis_signals[f"{asset}_stop_loss"] = {
                "type": "stop_loss",
                "asset": asset,
                "sl_price": sl_price,
                "risk_pips": risk_pips,
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(
                f"[UI_MAPPING] Added ANALYSIS SL for {asset}: "
                f"{sl_price:.5f} ({risk_pips:.0f} pips) | priority=HIGH"
            )
        
        except Exception as e:
            logger.error(f"[UI_MAPPING] Exception in add_stop_loss({asset}): {str(e)}")
