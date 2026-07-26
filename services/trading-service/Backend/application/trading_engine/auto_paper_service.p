def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()

@router.post("/auto-paper")
async def auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    engine: ExecutionEngine = Depends(get_engine),
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    db: Session = Depends(get_db),
):
    if not access.can("paper_trade.automated"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"error": "subscription_required", "feature": "paper_trade.automated", "current_plan": access.snapshot["plan_code"].upper(), "message": "Automated paper trading requires a Pro or Premium plan."})
    symbol = payload.symbol.upper()
    from Backend.application.kill_switch import kill_switch_status

    if execution_mode == "live" and not _request_is_https(request) and not _allow_insecure_live():
        result = _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason="Live trading requires HTTPS.",
            execution_mode=execution_mode,
            extra={"allowed": False},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    halt = kill_switch_status()
    if halt["active"]:
        result = _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason=f"KILL_SWITCH_ACTIVE: {halt.get('reason') or 'Trading halted'}",
            execution_mode=execution_mode,
            extra={"allowed": False, "kill_switch": halt},
        )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result
    write_audit_log(
        db,
        action="paper_auto_scan_triggered",
        actor=actor,
        target_type="symbol",
        target_id=symbol,
        request=request,
        metadata={"mode": execution_mode},
    )

    if execution_mode != "paper":
        return _paper_response(
            status_value="rejected",
            symbol=symbol,
            strategy=None,
            signal=None,
            reason="Auto execution is paper-only.",
            execution_mode=execution_mode,
        )

    candles_response = market_service.get_candles(symbol, interval=payload.interval, period=payload.period, limit=150)
    confirmation_response = market_service.get_candles(symbol, interval="5m", period=payload.period, limit=150)
    trend_response = market_service.get_candles(symbol, interval="15m", period=payload.period, limit=150)
    candles = _strategy_candles(candles_response)
    confirmation_candles = _strategy_candles(confirmation_response)
    trend_candles = _strategy_candles(trend_response)
    candle_validation = validate_live_candle(
        candles,
        interval=payload.interval,
        mode="paper",
        source=candles_response.get("source"),
        provider_fetched_at=candles_response.get("fetched_at"),
    )
    service = TradingService()
    strategies = payload.strategies or AUTO_SCAN_STRATEGIES
    strategy_diagnostics: dict[str, Any] = {}

    for strategy in strategies:
        try:
            raw_signals = service.run_strategy(
                strategy_name=strategy,
                data=candles,
                symbol=symbol,
                capital=payload.capital,
                risk_pct=payload.risk_pct,
                rr_ratio=payload.rr_ratio,
                params={"mtf_candles": confirmation_candles, "htf_candles": trend_candles},
            )
            observe_signal_generation(strategy, "success")
            validated_signals, data_source = validate_signals(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            diagnostics = diagnose_signal_run(
                raw_signals,
                symbol=symbol,
                candles=candles,
                candle_source=candles_response.get("source"),
            )
            strategy_diagnostics[strategy] = {
                "raw_signals": len(raw_signals),
                "validated_signals": len(validated_signals),
                "data_source": data_source,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": diagnostics,
            }
            if not validated_signals:
                continue

            selected = validated_signals[0]
            strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        except Exception as exc:
            observe_signal_generation(strategy, "error")
            strategy_diagnostics[strategy] = {
                "raw_signals": 0,
                "validated_signals": 0,
                "market_status": candle_validation.market_status,
                "validation": candle_validation.model_dump(),
                "diagnostics": [f"Strategy scan failed: {exc}"],
            }
            continue

        selected = validated_signals[0]
        strategy_diagnostics[strategy]["selected_signal"] = serialize_signal(selected)
        scan_market_status = str(getattr(candle_validation, "market_status", "LIVE MARKET"))
        if not candle_validation.valid_for_execution or scan_market_status.upper() != "LIVE MARKET":
            result = _paper_response(
                status_value="rejected",
                symbol=symbol,
                strategy=selected.strategy_name,
                signal=selected,
                reason=f"MARKET_NOT_LIVE_FOR_EXECUTION: {scan_market_status}",
                execution_mode=execution_mode,
                strategy_diagnostics=strategy_diagnostics,
                extra={"validation": candle_validation.model_dump()},
            )
            _audit_execution_result(db, request, actor, result)
            alert_execution_event(result)
            return result
        result = await _submit_paper_signal(
            selected,
            engine=engine,
            execution_mode=execution_mode,
            candles_1m=candles,
            candles_15m=trend_candles,
            strategy_diagnostics=strategy_diagnostics,
            broker_client=broker_client_for_mode(execution_mode),
            db=db,
            request=request,
            actor=actor,
        )
        if result.get("risk_decision"):
            _audit_risk_decision(
                db,
                request,
                actor,
                symbol=selected.symbol,
                strategy=selected.strategy_name,
                side=selected.side,
                risk_decision=result["risk_decision"],
            )
        _audit_execution_result(db, request, actor, result)
        alert_execution_event(result)
        return result

    result = _paper_response(
        status_value="no_trade",
        symbol=symbol,
        strategy=None,
        signal=None,
        reason="No validated signal found across auto-scan strategies.",
        execution_mode=execution_mode,
        strategy_diagnostics=strategy_diagnostics,
        extra={
            "candles_analyzed": len(candles),
            "strategies_checked": strategies,
            "validation": candle_validation.model_dump(),
        },
    )
    alert_execution_event(result)
    return result


@router.post("/auto-paper/jobs")
async def enqueue_auto_paper_order(
    payload: AutoPaperExecutionRequest,
    request: Request,
    actor: User = Depends(require_trade_execute),
    access: SubscriptionAccess = Depends(subscription_access),
    execution_mode: str = Depends(_execution_mode),
    engine: ExecutionEngine = Depends(get_engine),
):
    if not access.can("paper_trade.automated"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "subscription_required",
                "feature": "paper_trade.automated",
                "current_plan": access.snapshot["plan_code"].upper(),
                "message": "Automated paper trading requires a Pro or Premium plan.",
            },
        )

    if execution_mode != "paper":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Auto-paper jobs are paper-only.",
        )

    return {
    "status": "accepted",
    "message": "Auto paper job queued",
    "symbol": payload.symbol if hasattr(payload, "symbol") else None,
}
