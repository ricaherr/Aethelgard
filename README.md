# AETHELGARD: AGNOSTIC ALGORITHMIC TRADING BRAIN

![Status](https://img.shields.io/badge/Status-ACTIVE-brightgreen)
![Version](https://img.shields.io/badge/Version-1.13.0-blue)
![OS](https://img.shields.io/badge/OS-Windows-lightgrey)

**Aethelgard** es un sistema autónomo, proactivo y agnóstico de trading multihilo, diseñado bajo estándares de alta disponibilidad e ingeniería financiera. Capacidad de auto-calibración y enfoque comercial (SaaS).

---

## 🏛️ Arquitectura Modular (Financial Domains)

El sistema se organiza en dominios especializados para garantizar la escalabilidad y el aislamiento de responsabilidades:

1.  **[01 ALPHA ENGINE](docs/01_ALPHA_ENGINE.md)**: Generación de Alpha, gestión de estrategias y motor de escaneo proactivo.
2.  **[02 RISK CONTROL](docs/02_RISK_CONTROL.md)**: Gestión de riesgo, compliance técnico y controles de exposición/drawdown.
3.  **[03 EXECUTION EMS](docs/03_EXECUTION_EMS.md)**: Execution Management System (EMS), enrutamiento de órdenes y fidelidad de fuente.
4.  **[04 PORTFOLIO MANAGEMENT](docs/04_PORTFOLIO_MANAGEMENT.md)**: Gestión de portafolio y posiciones, monitor de trades y aprendizaje EDGE.
5.  **[05 INFRASTRUCTURE](docs/05_INFRASTRUCTURE.md)**: Capa de persistencia (SSOT), orquestación resiliente y servicios de API.

---

## 📜 Documentación Complementaria

- **[SYSTEM LEDGER](docs/SYSTEM_LEDGER.md)**: Historial completo de implementación y registros técnicos históricos.
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
