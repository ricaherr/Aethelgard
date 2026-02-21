# AETHELGARD: 02 RISK CONTROL

## 🛡️ Gestión de Riesgo y Compliance Técnico
Guardia algorítmica y controles de exposición para la preservación de capital.

---

### ⚖️ Capas de Riesgo
- **Risk Per Trade**: Base de 1.0%, adaptativo por `EdgeTuner`.
- **Account Risk Limit**: Máximo 5% de riesgo total agregado en cuenta.
- **Symbol Limits**: Restricción de posiciones y lotaje máximo por instrumento.
- **Lockdown Mode**: Protocolo de seguridad por drawdown excesivo o pérdidas consecutivas.

---

### 📉 Fail-Safes Proactivos
- **Risk Sanity Check**: Gate de cordura aritmético pre-ejecución.
- **JPY/Metal Fix**: Triangulación real y cálculo dinámico de point value.
- **Circuit Breaker**: Bloqueo tras N fallos de cálculo consecutivos.

---

### 🛡️ Resilience Protocol
El `RiskManager` es la autoridad final. Ninguna orden puede ser despachada al mercado sin su sello de aprobación ("Approved").
