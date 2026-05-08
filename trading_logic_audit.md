# QuantGrid Trading Logic Audit

## 🎯 Purpose

This document catalogs all trading-related logic in QuantGrid and defines what must be migrated into the domain layer as part of EPIC-1 (Trading Engine Refactor).

---

# 🧠 Current Architecture (Observed)

### API Layer (FastAPI)
- Backend/presentation/api/main.py
- Backend/presentation/api/trading_api.py
- Backend/presentation/api/execution.py
- Backend/presentation/api/auth.py

### Application Layer
- Backend/application/trading_service.py
- Backend/application/dto.py

### Domain Layer (Partial)
- Backend/domain/models/signal.py
- Backend/domain/engine/execution_engine.py

---

# ⚠️ Core Problem

Trading logic is currently **split across layers**:

❌ API partially orchestrates logic  
❌ TradingService contains business logic  
❌ Domain is incomplete  

This violates clean architecture.

---

# 📦 TRADING LOGIC INVENTORY

---

## 1. Strategy Execution Logic

📍 Location:
- `Backend/application/trading_service.py`

### Responsibilities:
- Select strategy by name
- Execute strategy on candle data
- Coordinate signal generation

### Inputs:
- strategy_name
- candles
- capital
- risk_pct
- rr_ratio

### Outputs:
- List[StrategySignal]

### Dependencies:
- Strategy engine (internal)
- DTO serializer
- Possibly API payload structure

### Issues:
❌ Not in domain  
❌ Tightly coupled to service layer  
❌ Hard to test independently  

### ✅ Target:
Move to:domain/strategies/

---

## 2. Signal Generation Logic

📍 Location:
- Inside strategy execution (via TradingService)

### Responsibilities:
- Generate BUY / SELL / HOLD
- Assign confidence
- Assign price

### Outputs:
- StrategySignal

### Issues:
❌ No strict contract enforcement  
❌ Mixed with execution logic  

### ✅ Target:
- Pure domain logic
- Enforced schema

---

## 3. Decision Rules (Core Trading Brain)

📍 Location:
- Embedded in strategy logic

### Responsibilities:
- Define entry conditions
- Define exit conditions
- Decide BUY / SELL / HOLD

### Issues:
❌ Not isolated  
❌ Not reusable  
❌ Hidden inside service layer  

### ✅ Target:
- Pure functions inside domain strategies

---

## 4. Execution Logic

📍 Location:
- `Backend/domain/engine/execution_engine.py`

### Responsibilities:
- Convert StrategySignal → Order
- Prepare execution payload

### Inputs:
- StrategySignal

### Outputs:
- Order

### Issues:
⚠️ Currently OK but:
- No broker abstraction yet
- No infrastructure separation

### ✅ Target:
- Keep core logic in domain
- Move broker integration → infrastructure

---

## 5. API Layer Logic

📍 Location:
- `trading_api.py`
- `execution.py`

### Responsibilities:
- Accept requests
- Call TradingService
- Return JSON

### Issues:
⚠️ Risk of business logic leakage  
⚠️ Routing + orchestration mixed  

### ✅ Target:
API should ONLY:
- validate request
- call service
- return response

---

# 🔗 DEPENDENCY FLOW (CURRENT)
API
↓
TradingService
↓
Strategy Logic (mixed)
↓
ExecutionEngine


---

# ✅ TARGET ARCHITECTURE
API (presentation)
↓
Application Service
↓
Domain Strategies
↓
Execution Engine
↓
Infrastructure (future)


---

# 🧱 DOMAIN LAYER DESIGN (TARGET)
domain/
├── strategies/
│ ├── base_strategy.py
│ ├── breakout.py
│ ├── mean_reversion.py
│
├── models/
│ ├── signal.py
│ ├── order.py
│
├── engine/
│ ├── execution_engine.py


---

# 📊 SIGNAL CONTRACT (MANDATORY)

All strategies must return:

```json
{
  "action": "BUY | SELL | HOLD",
  "confidence": 0.0-1.0,
  "price": float
}


REFACTOR PLAN
Phase 1
Extract all strategy logic from TradingService
Move into domain/strategies
Phase 2
Create BaseStrategy interface
Enforce signal contract
Phase 3
Clean TradingService (only orchestration)
Phase 4
Remove business logic from API
Phase 5
Introduce infrastructure layer (future)
✅ SUCCESS CRITERIA
Strategies run without FastAPI
Domain layer has zero external dependencies
API layer has no business logic
Signal format is consistent
Execution engine is isolated
🧠 FINAL TRANSFORMATION

Before:
❌ API-driven trading logic

After:
✅ Domain-driven trading engine (production-grade)



---

# 🚀 What this means (real insight)

 now I have

✔ A **clear map of your trading system**  
✔ Exact **logic that must move to domain layer**  
✔ Defined **architecture transformation**  

This is exactly what:
- hedge funds  
- quant infra teams  
- backend architects  

do before refactoring.

---

# 🔥 NEXT STEP (VERY IMPORTANT)

Now don’t stop here.

👉  next Jira task becomes actionable:

### **SCRUM-104: Refactor Trading Logic into Domain Layer**

If you want, I’ll next:
- :contentReference[oaicite:2]{index=2}
- or :contentReference[oaicite:3]{index=3}
- or :contentReference[oaicite:4]{index=4}

Just say 👍
::contentReference[oaicite:1]{index=1}