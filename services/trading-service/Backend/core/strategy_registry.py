from Backend.domain.strategies.amd import AMDStrategy
from Backend.domain.strategies.breakout import BreakoutStrategy
from Backend.domain.strategies.btst import BTSTStrategy
from Backend.domain.strategies.mean_reversion import MeanReversionStrategy
from Backend.domain.strategies.mtf import MTFStrategy
from Backend.domain.strategies.mtfa import MTFAStrategy
from Backend.domain.strategies.supply_demand import SupplyDemandStrategy

from .trading_core import StrategyRegistration

STRATEGIES = [
    StrategyRegistration("amd", "AMD", AMDStrategy()),
    StrategyRegistration("breakout", "Breakout", BreakoutStrategy()),
    StrategyRegistration("btst", "BTST", BTSTStrategy()),
    StrategyRegistration("mtf", "MTF", MTFStrategy()),
    StrategyRegistration("mtfa", "MTFA", MTFAStrategy()),
    StrategyRegistration("supply_demand", "Supply Demand", SupplyDemandStrategy()),
    StrategyRegistration("mean_reversion", "Mean Reversion", MeanReversionStrategy()),
]