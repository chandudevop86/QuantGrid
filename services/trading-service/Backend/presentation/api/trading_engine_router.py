"""
Trading Engine API Router

Responsibilities:
- Authentication
- Authorization
- Request validation
- Calling application services
- Audit logging
- API responses

Business logic belongs in application services.
"""

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
)

from sqlalchemy.orm import Session

from Backend.core.database import get_db
from Backend.domain.users.models import User
from Backend.presentation.dependencies.auth import current_user

from Backend.application.trading_engine.services import (
    trading_engine_dashboard,
    submit_paper_basket,
    scale_position,
)

from Backend.application.trading_engine.validators import (
    validate_basket_request,
    validate_scale_request,
)

from Backend.application.audit.audit_service import (
    write_audit_log,
)

from Backend.presentation.schemas.trading_engine import (
    TradingEngineDashboardResponse,
    TradingEngineBasketRequest,
    TradingEngineScaleRequest,
)


router = APIRouter(
    prefix="/api",
    tags=["Trading Engine"],
)


# ---------------------------------------------------------
# RBAC
# ---------------------------------------------------------

def _require_trading_engine_role(actor: User):
    """
    Trading engine permission check.
    """

    allowed_roles = {
        "admin",
        "trader",
        "quant",
    }

    if actor.role not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Trading engine access denied",
        )


# ---------------------------------------------------------
# Helpers
# ---------------------------------------------------------

def _execution_mode(value: str | None) -> str:
    """
    Normalize execution mode.
    """

    if not value:
        return "paper"

    return value.strip().lower()


def _model_to_dict(model):
    """
    Pydantic compatibility helper.
    """

    if hasattr(model, "model_dump"):
        return model.model_dump()

    return model.dict()


def _request_metadata(request: Request):

    return {
        "ip_address": (
            request.client.host
            if request.client
            else None
        ),
        "user_agent": request.headers.get(
            "user-agent"
        ),
    }


# =========================================================
# DASHBOARD
# =========================================================

@router.get(
    "/trading-engine/dashboard",
    response_model=TradingEngineDashboardResponse,
)
async def get_trading_engine_dashboard(
    actor: User = Depends(current_user),
):

    _require_trading_engine_role(actor)

    return trading_engine_dashboard()



# =========================================================
# SUBMIT PAPER BASKET
# =========================================================

@router.post(
    "/trading-engine/basket",
)
async def submit_trading_engine_basket(
    payload: TradingEngineBasketRequest,
    request: Request,
    actor: User = Depends(current_user),
    db: Session = Depends(get_db),
):

    _require_trading_engine_role(actor)


    execution_mode = _execution_mode(
        payload.execution_mode
    )


    try:

        validate_basket_request(
            payload
        )


        with db.begin():

            result = submit_paper_basket(
                legs=[
                    _model_to_dict(leg)
                    for leg in payload.legs
                ],
                execution_mode=execution_mode,
                reason=payload.reason,
                idempotency_key=payload.idempotency_key,
            )


            write_audit_log(
                db,

                action="paper_basket_submitted",

                actor=actor,

                target_type="basket",

                target_id=result["basket_id"],

                request=request,

                metadata={
                    **_request_metadata(request),

                    "status":
                        result["status"],

                    "created_count":
                        result["created_count"],

                    "error_count":
                        result["error_count"],

                    "execution_mode":
                        execution_mode,
                },
            )


        return result



    except ValueError as exc:


        write_audit_log(
            db,

            action="paper_basket_blocked",

            actor=actor,

            target_type="basket",

            target_id="paper",

            request=request,

            metadata={
                **_request_metadata(request),

                "reason": str(exc),

                "execution_mode":
                    execution_mode,
            },
        )


        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc



    except Exception:


        db.rollback()


        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Basket execution failed",
        )



# =========================================================
# SCALE POSITION
# =========================================================

@router.post(
    "/trading-engine/positions/{position_id}/scale",
)
async def submit_trading_engine_scale(

    position_id: int,

    payload: TradingEngineScaleRequest,

    request: Request,

    actor: User = Depends(current_user),

    db: Session = Depends(get_db),

):


    _require_trading_engine_role(actor)



    execution_mode = _execution_mode(
        payload.execution_mode
    )



    try:


        validate_scale_request(
            payload
        )


        with db.begin():


            result = scale_position(

                position_id,

                action=payload.action,

                quantity=payload.quantity,

                price=payload.price,

                reason=payload.reason,

                execution_mode=execution_mode,

            )



            write_audit_log(

                db,

                action="position_scaled",

                actor=actor,

                target_type="position",

                target_id=position_id,

                request=request,

                metadata={

                    **_request_metadata(request),


                    "action":
                        result["status"],


                    "old_quantity":
                        result["old_quantity"],


                    "new_quantity":
                        result["new_quantity"],


                    "price":
                        result["price"],


                    "realized_pnl":
                        result["realized_pnl"],


                    "execution_mode":
                        execution_mode,

                },

            )


        return result




    except ValueError as exc:



        write_audit_log(

            db,

            action="position_scale_blocked",

            actor=actor,

            target_type="position",

            target_id=position_id,

            request=request,

            metadata={

                **_request_metadata(request),

                "reason":
                    str(exc),

                "action":
                    payload.action,

                "execution_mode":
                    execution_mode,

            },

        )


        raise HTTPException(

            status_code=status.HTTP_400_BAD_REQUEST,

            detail=str(exc),

        ) from exc





    except Exception:



        db.rollback()



        raise HTTPException(

            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

            detail="Position scaling failed",

        )