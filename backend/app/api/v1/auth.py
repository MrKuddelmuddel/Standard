from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import SESSION_COOKIE, client_ip, current_user
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.ratelimit import limiter
from app.core.security import DUMMY_HASH, hash_password, new_token, token_hash, verify_password
from app.db.session import get_db
from app.models import AuthSession, User
from app.schemas import Credentials, PreferencesIn, UserOut
from app.services.audit import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _start_session(db: Session, user: User, request: Request, response: Response) -> str:
    s = get_settings()
    token = new_token()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=token_hash(token),
            expires_at=datetime.now(UTC) + timedelta(days=s.session_days),
            user_agent=(request.headers.get("user-agent") or "")[:200],
        )
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=s.session_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return token


@router.post("/register", response_model=dict, status_code=201)
def register(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    limiter.check(f"register:{client_ip(request)}", 10)
    user = User(email=body.email.lower(), password_hash=hash_password(body.password), preferences={})
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ApiError(409, "email_taken", "An account with this email already exists.") from exc
    token = _start_session(db, user, request, response)
    audit(db, user.id, "auth.registered", "user", user.id, ip=client_ip(request))
    db.commit()
    return {"user": UserOut.model_validate(user).model_dump(mode="json"), "token": token}


@router.post("/login", response_model=dict)
def login(body: Credentials, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    limiter.check(f"login:{client_ip(request)}", 10)
    limiter.check(f"login:{body.email.lower()}", 10)
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if user is None or not ok or user.status != "active":
        audit(
            db, user.id if user else None, "auth.login_failed", "user", user.id if user else None, ip=client_ip(request)
        )
        db.commit()
        raise ApiError(401, "invalid_credentials", "Email or password is wrong.")
    token = _start_session(db, user, request, response)
    audit(db, user.id, "auth.login", "user", user.id, ip=client_ip(request))
    db.commit()
    return {"user": UserOut.model_validate(user).model_dump(mode="json"), "token": token}


@router.post("/logout", status_code=204)
def logout(
    request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    token = request.cookies.get(SESSION_COOKIE) or request.headers.get("authorization", "")[7:]
    db.execute(delete(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    audit(db, user.id, "auth.logout", "user", user.id)
    db.commit()
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@router.patch("/me/preferences", response_model=UserOut)
def update_preferences(body: PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    user.preferences = {**(user.preferences or {}), **body.model_dump(exclude_none=True)}
    db.commit()
    return user


@router.get("/me/export")
def export_account(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    """Personal data export (GDPR-style): account, strategies with versions, journal trades."""
    from app.models import JournalTrade, Strategy, StrategyVersion

    strategies = []
    for s in db.scalars(select(Strategy).where(Strategy.owner_id == user.id)):
        versions = db.scalars(
            select(StrategyVersion).where(StrategyVersion.strategy_id == s.id).order_by(StrategyVersion.version_number)
        )
        strategies.append(
            {
                "name": s.name,
                "description": s.description,
                "origin": s.origin,
                "status": s.status,
                "versions": [
                    {"number": v.version_number, "hash": v.canonical_hash, "definition": v.definition_json}
                    for v in versions
                ],
            }
        )
    trades = [
        {
            a.key: getattr(t, a.key)
            for a in JournalTrade.__mapper__.column_attrs
            if a.key not in ("owner_id", "dedupe_key")
        }
        for t in db.scalars(select(JournalTrade).where(JournalTrade.owner_id == user.id))
    ]
    return {
        "account": {"email": user.email, "created_at": user.created_at, "preferences": user.preferences},
        "strategies": strategies,
        "journal_trades": trades,
        "exported_at": datetime.now(UTC),
    }
