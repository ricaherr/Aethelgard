# AETHELGARD: AGNOSTIC ALGORITHMIC TRADING BRAIN

![Status](https://img.shields.io/badge/Status-ACTIVE-brightgreen)
![Version](https://img.shields.io/badge/Version-2.5.0--UTF-blue)
![OS](https://img.shields.io/badge/OS-Windows-lightgrey)

**Aethelgard** es un sistema autónomo, proactivo y agnóstico de trading multihilo, diseñado bajo estándares de alta disponibilidad e ingeniería financiera. Capacidad de auto-calibración y enfoque comercial (SaaS).

**✨ Versión 2.5.0**: Universal Trading Foundation completado. Cálculo agnóstico de riesgo con precisión institucional (Decimal + ROUND_DOWN). Operación real habilitada para Forex, Crypto y Metals.

---

## 🏛️ Arquitectura Modular (5 Dominios Vigentes)

El sistema se organiza en 5 dominios especializados para garantizar escalabilidad y aislamiento de responsabilidades:

1.  **[01 CORE_ADAPTIVE_BRAIN](docs/01_CORE_ADAPTIVE_BRAIN.md)**: Generación de contexto de mercado, regímenes y aprendizaje adaptativo del EDGE.
2.  **[02 EXECUTOR_GOVERNANCE](docs/02_EXECUTOR_GOVERNANCE.md)**: Gobernanza de riesgo y ejecución agnóstica con vetos operativos.
3.  **[03 PERFORMANCE_DARWINISM](docs/03_PERFORMANCE_DARWINISM.md)**: Ciclo SHADOW/LIVE, coherencia matemática y ranking darwinista.
4.  **[04 DATA_SOVEREIGNTY_INFRA](docs/04_DATA_SOVEREIGNTY_INFRA.md)**: SSOT, persistencia multi-tenant y resiliencia de infraestructura.
5.  **[05 IDENTITY_SECURITY](docs/05_IDENTITY_SECURITY.md)**: Gatekeeper de identidad, RBAC y aislamiento SaaS.

---

## 📜 Documentación Complementaria

- **[SYSTEM LEDGER](governance/SYSTEM_LEDGER.md)**: Historial completo de implementación y registros técnicos históricos.
- **[ROADMAP](ROADMAP.md)**: Visión estratégica y hitos futuros del proyecto.
- **[AETHELGARD MANIFESTO](AETHELGARD_MANIFESTO.md)**: Misión, visión y principios filosóficos del sistema.

---

## 🚀 Quick Start (Production Mode)

1. **Requisitos**: Python 3.12+, MetaTrader 5 (Demo Account).
2. **Setup**:
   ```powershell
   python start.py
   ```
3. **Validación**:
   ```powershell
   python scripts/utilities/check_system.py
   ```

---

*Desarrollado con enfoque en la autonomía total y la resiliencia algorítmica.*

