import json
from typing import cast
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from src.application.dtos import ActorContext
from src.application.interfaces import (
    CloudKeypointClassifierPort,
    TokenProviderPort,
    UnitOfWorkFactory,
)
from src.application.use_cases.streaming import AuthorizeKeypointStreamUseCase
from src.domain.exceptions import DomainError, DomainValidationError, EntityNotFoundError
from src.domain.value_objects import Lb6Frame
from src.infrastructure.ml import CausalLb6SlidingWindowProcessor
from src.presentation.schemas import WsLb6FrameMessage, WsWindowPredictionMessage

router = APIRouter(tags=["Cloud Fallback Streaming"])


@router.websocket("/ws/v1/stream/keypoints/{session_id}")
async def stream_keypoints_fallback(websocket: WebSocket, session_id: UUID) -> None:
    """Real-time 15 Hz LB6 keypoint streaming fallback emitting 1.0s window predictions."""
    auth_header = websocket.headers.get("authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        await websocket.close(code=4401, reason="Unauthorized")
        return

    token_provider = cast(TokenProviderPort, websocket.app.state.token_provider)
    raw_jwt = auth_header[7:].strip()
    try:
        claims = token_provider.decode_access_token(raw_jwt)
    except DomainError:
        await websocket.close(code=4401, reason="Invalid or expired token")
        return

    actor = ActorContext(
        user_id=claims.user_id,
        role=claims.role,
        device_id=claims.device_id,
    )
    uow_factory = cast(UnitOfWorkFactory, websocket.app.state.uow_factory)
    auth_uc = AuthorizeKeypointStreamUseCase(uow_factory)
    try:
        await auth_uc.execute(actor, session_id)
    except EntityNotFoundError:
        await websocket.close(code=4404, reason="Session not found")
        return
    except DomainError as exc:
        await websocket.close(code=4403, reason=exc.error_code)
        return

    await websocket.accept()
    classifier = cast(CloudKeypointClassifierPort, websocket.app.state.cloud_classifier)
    processor = CausalLb6SlidingWindowProcessor(classifier)

    while True:
        try:
            raw_text = await websocket.receive_text()
        except WebSocketDisconnect:
            break

        try:
            raw_obj = json.loads(raw_text)
            msg = WsLb6FrameMessage.model_validate(raw_obj)
            frame = Lb6Frame(
                keypoints=tuple(
                    (float(j[0]), float(j[1]), float(j[2])) for j in msg.lb6_xyc
                )
            )
        except (json.JSONDecodeError, ValidationError, DomainValidationError) as exc:
            detail = exc.detail if isinstance(exc, DomainValidationError) else "Invalid LB6_FRAME."
            await websocket.send_json(
                {
                    "type": "ERROR",
                    "error_code": "INVALID_FRAME",
                    "detail": detail,
                }
            )
            continue

        prediction = processor.push_frame(frame)
        if prediction is not None:
            out_msg = WsWindowPredictionMessage(
                window_idx=prediction.window_idx,
                raw_prob=prediction.raw_prob,
                calibrated_score=prediction.calibrated_score,
                alert_tier=prediction.alert_tier,
                freeze_index_ankle=prediction.freeze_index_ankle,
            )
            await websocket.send_json(out_msg.model_dump(mode="json"))
