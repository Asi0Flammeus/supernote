"""Real-time Socket.IO push notifications for connected Supernote clients.

Mirrors the original Ratta cloud's `finishFolderMessage` event (see
`ARCHITECTURE.md` section 7.2.2, reverse-engineered from the proprietary
backend): after a mutation persists, the server notifies every OTHER session
belonging to the same user so their clients can refresh without polling.

Payload shape is not fully documented by the reverse-engineered notes (only
the event name is known, not its fields), so we use a minimal, self
describing payload:
  - `directoryId`: the affected directory when known (str), else `null` for
    mutations without a single clear directory context (e.g. clearing the
    whole recycle bin, or non-file changes like schedule/todo mutations).
  - `timestamp`: server epoch-milliseconds, so clients can dedupe/order.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import socketio
from socketio.asyncio_manager import AsyncManager

# python-socketio 4.6.1's AsyncManager.emit() passes bare coroutines to
# asyncio.wait(), which Python 3.14 now rejects outright ("Passing
# coroutines is forbidden, use tasks explicitly") instead of merely
# deprecating. This only triggers when a room has 2+ participants (e.g. the
# same account connected from two devices), so it went unnoticed until
# multi-session fan-out was exercised. Wrap each coroutine in a Task before
# handing it to asyncio.wait(); behavior is otherwise unchanged.

async def _async_manager_emit_task_safe(
    self: AsyncManager,
    event: str,
    data: Any,
    namespace: str,
    room: str | None = None,
    skip_sid: Any = None,
    callback: Any = None,
    **kwargs: Any,
) -> None:
    if namespace not in self.rooms or room not in self.rooms[namespace]:
        return
    tasks = []
    skip_sids = skip_sid if isinstance(skip_sid, list) else [skip_sid]
    for sid in self.get_participants(namespace, room):
        if sid not in skip_sids:
            ack_id = (
                self._generate_ack_id(sid, namespace, callback)
                if callback is not None
                else None
            )
            tasks.append(
                asyncio.ensure_future(
                    self.server._emit_internal(sid, event, data, namespace, ack_id)
                )
            )
    if not tasks:
        return
    await asyncio.wait(tasks)


AsyncManager.emit = _async_manager_emit_task_safe

FINISH_FOLDER_EVENT = "finishFolderMessage"


def user_room(user_id: int) -> str:
    """Room name for all Socket.IO sessions belonging to a given user."""
    return f"user:{user_id}"


async def notify_finish_folder(
    sio: socketio.AsyncServer,
    user_id: int,
    directory_id: int | str | None = None,
) -> None:
    """Emit a `finishFolderMessage` event to every connected session of `user_id`."""
    payload: dict[str, Any] = {
        "directoryId": str(directory_id) if directory_id is not None else None,
        "timestamp": int(time.time() * 1000),
    }
    await sio.emit(FINISH_FOLDER_EVENT, payload, room=user_room(user_id))
