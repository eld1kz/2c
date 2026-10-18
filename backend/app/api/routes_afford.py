"""Can I afford it? (SPEC §6.9): POST /afford, see services/afford.py.

Owner or accountant (it runs a simulation and spends AI budget; viewers get an audited 403, and the
model is never called). Same rate limits, daily budget and one-turn-in-flight lock as chat. The
verdict comes from the engine; nothing is stored.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.runner import ChatModel
from app.api import routes_chat
from app.api.deps import Principal, current_principal, get_chat_model, get_session
from app.api.routes_whatif import require_simulation_role
from app.api.schemas import AffordAskIn, AffordOut, CitationOut
from app.config import Settings, get_settings
from app.engine.whatif import ScenarioError
from app.services import afford
from app.services.afford import AffordUnavailable

router = APIRouter(tags=["afford"])


@router.post("/afford", response_model=AffordOut)
def ask(body: AffordAskIn, principal: Principal = Depends(current_principal), session: Session = Depends(get_session),
        settings: Settings = Depends(get_settings), model: ChatModel = Depends(get_chat_model)) -> AffordOut:
    user, owner = principal.user, routes_chat.chat_owner(principal, settings)
    require_simulation_role(session, user, "check_affordability")
    budget = routes_chat.admit(session, user, settings, owner)
    try:
        answer = afford.ask(session, user, model, settings.demo_today, body.question, budget)
    except AffordUnavailable as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from None
    except ScenarioError as e:  # the tool accepted it, so this only happens if the books changed mid-turn
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(e)) from None
    finally:
        routes_chat.conversations.end(owner)
    return AffordOut(verdict=answer.verdict, earliest_safe_start=answer.earliest_safe_start, message=answer.message,
                     citations=[CitationOut(**c) for c in answer.citations], warnings=answer.warnings,
                     scenarios=answer.scenarios)
