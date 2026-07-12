import logging
from typing import Any

from aiohttp import web

from supernote.models.base import BaseResponse, BooleanEnum, create_error_response
from supernote.models.schedule import (
    AddScheduleTaskDTO,
    AddScheduleTaskGroupDTO,
    AddScheduleTaskGroupVO,
    AddScheduleTaskVO,
    ScheduleTaskAllVO,
    ScheduleTaskGroupItem,
    ScheduleTaskGroupVO,
    ScheduleTaskInfo,
    UpdateScheduleTaskDTO,
    UpdateScheduleTaskListDTO,
    UpdateScheduleTaskVO,
)
from supernote.server.services.schedule import ScheduleService
from supernote.server.utils.realtime import notify_finish_folder

logger = logging.getLogger(__name__)

routes = web.RouteTableDef()


@routes.post("/api/schedule/groups")
async def create_group(request: web.Request) -> web.Response:
    user = request["user"]
    try:
        data = await request.json()
        dto = AddScheduleTaskGroupDTO.from_dict(data)
    except Exception as e:
        return web.json_response(
            create_error_response(f"Invalid request: {e}").to_dict(), status=400
        )

    if not dto.title:
        return web.json_response(
            create_error_response("Title required").to_dict(), status=400
        )

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    try:
        group = await schedule_service.create_group(user_id, dto.title)
        await notify_finish_folder(request.app["sio"], user_id, directory_id=None)
        return web.json_response(
            AddScheduleTaskGroupVO(
                success=True, task_list_id=str(group.task_list_id)
            ).to_dict()
        )
    except ValueError as e:
        return web.json_response(create_error_response(str(e)).to_dict(), status=400)


@routes.get("/api/schedule/groups")
async def list_groups(request: web.Request) -> web.Response:
    user = request["user"]
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    groups = await schedule_service.list_groups(user_id)

    # Map to ScheduleTaskGroupItem
    items = [
        ScheduleTaskGroupItem(
            task_list_id=str(g.task_list_id),
            user_id=g.user_id,
            title=g.title,
            create_time=g.create_time,
        )
        for g in groups
    ]

    return web.json_response(
        ScheduleTaskGroupVO(success=True, schedule_task_group=items).to_dict()
    )


@routes.delete("/api/schedule/groups/{id}")
async def delete_group(request: web.Request) -> web.Response:
    user = request["user"]
    group_id = int(request.match_info["id"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    success = await schedule_service.delete_group(user_id, group_id)
    if not success:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)

    return web.json_response(BaseResponse(success=True).to_dict())


@routes.post("/api/schedule/tasks")
async def create_task(request: web.Request) -> web.Response:
    user = request["user"]
    try:
        data = await request.json()
        dto = AddScheduleTaskDTO.from_dict(data)
    except Exception as e:
        return web.json_response(
            create_error_response(f"Invalid request: {e}").to_dict(), status=400
        )

    if not dto.title:
        return web.json_response(
            create_error_response("Missing required fields").to_dict(), status=400
        )

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    if dto.task_list_id:
        group_id = int(dto.task_list_id)
    else:
        # Real firmware creates To-Do tasks without ever picking a list (the
        # OpenAPI spec confirms taskListId is optional on AddScheduleTaskDTO,
        # unlike this handler previously assumed) -- fall back to the user's
        # implicit default group instead of rejecting the sync.
        default_group = await schedule_service.get_or_create_default_group(user_id)
        group_id = default_group.task_list_id

    try:
        task = await schedule_service.create_task(
            user_id=user_id,
            group_id=group_id,
            title=dto.title,
            detail=dto.detail or "",
            status=dto.status or "needsAction",
            importance=dto.importance,
            due_time=dto.due_time,
            recurrence=dto.recurrence,
            is_reminder_on=(dto.is_reminder_on == BooleanEnum.YES),
        )
        await notify_finish_folder(request.app["sio"], user_id, directory_id=None)
        return web.json_response(
            AddScheduleTaskVO(success=True, task_id=str(task.task_id)).to_dict()
        )
    except ValueError as e:
        return web.json_response(create_error_response(str(e)).to_dict(), status=400)


@routes.get("/api/schedule/tasks")
async def list_tasks(request: web.Request) -> web.Response:
    user = request["user"]
    group_id_str = request.query.get("taskListId")
    group_id = int(group_id_str) if group_id_str else None

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    tasks_dos = await schedule_service.list_tasks(user_id, group_id)

    tasks_vos = [
        ScheduleTaskInfo(
            task_id=str(t.task_id),
            task_list_id=str(t.task_list_id),
            title=t.title,
            detail=t.detail,
            status=t.status,
            importance=t.importance,
            due_time=t.due_time,
            recurrence=t.recurrence,
            is_reminder_on=(BooleanEnum.YES if t.is_reminder_on else BooleanEnum.NO),
            last_modified=t.update_time,
        )
        for t in tasks_dos
    ]

    return web.json_response(
        ScheduleTaskAllVO(success=True, schedule_task=tasks_vos).to_dict()
    )


@routes.put("/api/schedule/tasks/{id}")
async def update_task(request: web.Request) -> web.Response:
    user = request["user"]
    task_id = int(request.match_info["id"])
    try:
        data = await request.json()
        dto = UpdateScheduleTaskDTO.from_dict(data)
    except Exception as e:
        return web.json_response(
            create_error_response(f"Invalid request: {e}").to_dict(), status=400
        )

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    updates: dict[str, Any] = {}
    if dto.title is not None:
        updates["title"] = dto.title
    if dto.detail is not None:
        updates["detail"] = dto.detail
    if dto.status is not None:
        updates["status"] = dto.status
    if dto.importance is not None:
        updates["importance"] = dto.importance
    if dto.due_time is not None:
        updates["due_time"] = dto.due_time
    if dto.recurrence is not None:
        updates["recurrence"] = dto.recurrence
    if dto.is_reminder_on is not None:
        updates["is_reminder_on"] = dto.is_reminder_on == BooleanEnum.YES
    if dto.task_list_id is not None:
        updates["task_list_id"] = int(dto.task_list_id)

    updated_task = await schedule_service.update_task(user_id, task_id, **updates)
    if not updated_task:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)

    return web.json_response(
        UpdateScheduleTaskVO(success=True, task_id=str(updated_task.task_id)).to_dict()
    )


@routes.delete("/api/schedule/tasks/{id}")
async def delete_task(request: web.Request) -> web.Response:
    user = request["user"]
    task_id = int(request.match_info["id"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    success = await schedule_service.delete_task(user_id, task_id)
    if not success:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)

    return web.json_response(BaseResponse(success=True).to_dict())


# ---------------------------------------------------------------------------
# Device-compatible aliases. The real Supernote firmware calls the paths
# documented in this repo's own api-spec/openapi.yaml (/api/file/schedule/...,
# POST-based "all" listing endpoints) rather than the /api/schedule/... paths
# implemented above — confirmed live against a real device on 2026-07-10
# (POST /api/file/schedule/group/all returned 404 during an actual sync).
# These aliases delegate to the exact same ScheduleService calls so there is
# only one source of truth for the business logic; only the wire shape
# differs to match what firmware actually sends.
# ---------------------------------------------------------------------------


@routes.post("/api/file/schedule/group/all")
async def list_groups_device(request: web.Request) -> web.Response:
    return await list_groups(request)


@routes.post("/api/file/schedule/group")
async def create_group_device(request: web.Request) -> web.Response:
    return await create_group(request)


@routes.get("/api/file/schedule/group/{taskListId}")
async def get_group_device(request: web.Request) -> web.Response:
    user = request["user"]
    group_id = int(request.match_info["taskListId"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    groups = await schedule_service.list_groups(user_id)
    match = next((g for g in groups if g.task_list_id == group_id), None)
    if not match:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    return web.json_response(
        ScheduleTaskGroupVO(
            success=True,
            schedule_task_group=[
                ScheduleTaskGroupItem(
                    task_list_id=str(match.task_list_id),
                    user_id=match.user_id,
                    title=match.title,
                    create_time=match.create_time,
                )
            ],
        ).to_dict()
    )


@routes.delete("/api/file/schedule/group/{taskListId}")
async def delete_group_device(request: web.Request) -> web.Response:
    user = request["user"]
    group_id = int(request.match_info["taskListId"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    success = await schedule_service.delete_group(user_id, group_id)
    if not success:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)
    return web.json_response(BaseResponse(success=True).to_dict())


@routes.post("/api/file/schedule/task/all")
async def list_tasks_device(request: web.Request) -> web.Response:
    user = request["user"]
    try:
        data = await request.json()
    except Exception:
        data = {}
    group_id_raw = data.get("taskListId")
    group_id = int(group_id_raw) if group_id_raw else None

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    tasks_dos = await schedule_service.list_tasks(user_id, group_id)
    tasks_vos = [
        ScheduleTaskInfo(
            task_id=str(t.task_id),
            task_list_id=str(t.task_list_id),
            title=t.title,
            detail=t.detail,
            status=t.status,
            importance=t.importance,
            due_time=t.due_time,
            recurrence=t.recurrence,
            is_reminder_on=(BooleanEnum.YES if t.is_reminder_on else BooleanEnum.NO),
            last_modified=t.update_time,
        )
        for t in tasks_dos
    ]
    return web.json_response(
        ScheduleTaskAllVO(success=True, schedule_task=tasks_vos).to_dict()
    )


@routes.post("/api/file/schedule/task")
async def create_task_device(request: web.Request) -> web.Response:
    return await create_task(request)


@routes.put("/api/file/schedule/task")
async def update_task_device_noid(request: web.Request) -> web.Response:
    user = request["user"]
    try:
        data = await request.json()
        dto = UpdateScheduleTaskDTO.from_dict(data)
    except Exception as e:
        return web.json_response(
            create_error_response(f"Invalid request: {e}").to_dict(), status=400
        )

    task_id_raw = data.get("taskId")
    if not task_id_raw:
        return web.json_response(
            create_error_response("taskId required").to_dict(), status=400
        )
    task_id = int(task_id_raw)

    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)

    updates: dict[str, Any] = {}
    if dto.title is not None:
        updates["title"] = dto.title
    if dto.detail is not None:
        updates["detail"] = dto.detail
    if dto.status is not None:
        updates["status"] = dto.status
    if dto.importance is not None:
        updates["importance"] = dto.importance
    if dto.due_time is not None:
        updates["due_time"] = dto.due_time
    if dto.recurrence is not None:
        updates["recurrence"] = dto.recurrence
    if dto.is_reminder_on is not None:
        updates["is_reminder_on"] = dto.is_reminder_on == BooleanEnum.YES
    if dto.task_list_id is not None:
        updates["task_list_id"] = int(dto.task_list_id)

    updated_task = await schedule_service.update_task(user_id, task_id, **updates)
    if not updated_task:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)

    return web.json_response(
        UpdateScheduleTaskVO(success=True, task_id=str(updated_task.task_id)).to_dict()
    )


@routes.get("/api/file/schedule/task/{taskId}")
async def get_task_device(request: web.Request) -> web.Response:
    user = request["user"]
    task_id = int(request.match_info["taskId"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    tasks_dos = await schedule_service.list_tasks(user_id, None)
    match = next((t for t in tasks_dos if t.task_id == task_id), None)
    if not match:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    return web.json_response(
        ScheduleTaskInfo(
            task_id=str(match.task_id),
            task_list_id=str(match.task_list_id),
            title=match.title,
            detail=match.detail,
            status=match.status,
            importance=match.importance,
            due_time=match.due_time,
            recurrence=match.recurrence,
            is_reminder_on=(
                BooleanEnum.YES if match.is_reminder_on else BooleanEnum.NO
            ),
            last_modified=match.update_time,
        ).to_dict()
    )


@routes.delete("/api/file/schedule/task/{taskId}")
async def delete_task_device(request: web.Request) -> web.Response:
    user = request["user"]
    task_id = int(request.match_info["taskId"])
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    success = await schedule_service.delete_task(user_id, task_id)
    if not success:
        return web.json_response(
            create_error_response("Not found").to_dict(), status=404
        )
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)
    return web.json_response(BaseResponse(success=True).to_dict())


@routes.put("/api/file/schedule/task/list")
async def update_task_list_device(request: web.Request) -> web.Response:
    # Endpoint: PUT /api/file/schedule/task/list
    # Purpose: Bulk update of multiple schedule tasks in one call (the real
    # device sends this after a batch of local edits, e.g. marking several
    # tasks completed and reordering them -- confirmed via trace log body
    # {"updateScheduleTaskList": [{"taskId": ..., "status": "completed",
    # ...}, ...]}). Previously 404'd since only the single-task PUT
    # /api/file/schedule/task route existed. Applies the same per-task
    # field mapping as update_task_device_noid to each item in the list.
    # Response: BaseResponse
    user = request["user"]
    try:
        data = await request.json()
        dto = UpdateScheduleTaskListDTO.from_dict(data)
    except Exception as e:
        return web.json_response(
            create_error_response(f"Invalid request: {e}").to_dict(), status=400
        )
    schedule_service: ScheduleService = request.app["schedule_service"]
    user_id = await request.app["user_service"].get_user_id(user)
    for task_dto in dto.update_schedule_task_list:
        if not task_dto.task_id:
            continue
        task_id = int(task_dto.task_id)
        updates: dict[str, Any] = {}
        if task_dto.title is not None:
            updates["title"] = task_dto.title
        if task_dto.detail is not None:
            updates["detail"] = task_dto.detail
        if task_dto.status is not None:
            updates["status"] = task_dto.status
        if task_dto.importance is not None:
            updates["importance"] = task_dto.importance
        if task_dto.due_time is not None:
            updates["due_time"] = task_dto.due_time
        if task_dto.completed_time is not None:
            updates["completed_time"] = task_dto.completed_time
        if task_dto.recurrence is not None:
            updates["recurrence"] = task_dto.recurrence
        if task_dto.is_reminder_on is not None:
            updates["is_reminder_on"] = task_dto.is_reminder_on == BooleanEnum.YES
        if task_dto.task_list_id is not None:
            updates["task_list_id"] = int(task_dto.task_list_id)
        if updates:
            await schedule_service.update_task(user_id, task_id, **updates)
    await notify_finish_folder(request.app["sio"], user_id, directory_id=None)
    return web.json_response(BaseResponse(success=True).to_dict())
