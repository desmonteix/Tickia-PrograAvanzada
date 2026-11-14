from fastapi import APIRouter, Depends, Request, HTTPException
from pydantic import BaseModel
from typing import Literal
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import get_current_user
from ..promotions import campaign_view, reward_view, expire_hold, reward_state
from .. import models
from ..rate_limit import limiter

router = APIRouter(prefix='/api', tags=['promotions'])


@router.get('/promotions')
def promotions(db: Session = Depends(get_db)):
    return campaign_view(db)


@router.get('/referrals')
@limiter.limit('15/minute')
def referrals(request: Request, user=Depends(get_current_user), db: Session = Depends(get_db)):
    return reward_view(db, user.id)


class RewardChoice(BaseModel):
    choice: Literal['BUY', 'SELL']


@router.post('/referrals/choice')
@limiter.limit('15/minute')
def choose_reward(request: Request, body: RewardChoice, user=Depends(get_current_user), db: Session = Depends(get_db)):
    reward = db.query(models.ReferralReward).filter_by(user_id=user.id).populate_existing().with_for_update().first()
    expire_hold(reward)
    if reward_state(reward) != 'AVAILABLE':
        raise HTTPException(409, 'Solo puedes elegir un beneficio disponible y sin reservas pendientes.')
    if body.choice == 'SELL' and reward.seller_commission_rate is None:
        raise HTTPException(422, 'Este beneficio solo es válido para una compra.')
    reward.choice = body.choice
    db.add(models.AuditLog(user_id=user.id, action='REWARD_CHOICE', entity_type='reward', entity_id=str(user.id), new_state=body.choice))
    db.commit()
    return reward_view(db, user.id)
