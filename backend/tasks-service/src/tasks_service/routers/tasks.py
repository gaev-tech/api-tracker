from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from tasks_service.cursor import CursorError
from tasks_service.deps import CurrentUserDep, SessionDep
from tasks_service.models import Task
from tasks_service.rsql.parser import RSQLError
from tasks_service.schemas import (
    BatchCreateResult,
    BatchResult,
    BulkCreateRequest,
    BulkCreateResult,
    BulkPatchRequest,
    BulkResult,
    HistoryEvent,
    HistoryPage,
    TaskCreate,
    TaskListPage,
    TaskRead,
    TaskUpdate,
)
from tasks_service.services import history, tasks
from tasks_service.services.prefix_lookup import resolve_prefix
from tasks_service.services.tasks import TaskNotFound, TooManyMatches

router = APIRouter(prefix="/v1", tags=["tasks"])


@router.get("/tasks", response_model=TaskListPage)
async def list_tasks(
    session: SessionDep,
    user: CurrentUserDep,
    filter: Annotated[str | None, Query(description="RSQL filter")] = None,
    cursor: Annotated[str | None, Query(description="opaque cursor")] = None,
    limit: Annotated[int, Query(ge=1, le=tasks.MAX_LIMIT)] = tasks.DEFAULT_LIMIT,
) -> TaskListPage:
    try:
        items, next_cursor = await tasks.list_tasks(
            session,
            current_user=user,
            filter_str=filter,
            cursor=cursor,
            limit=limit,
        )
    except (RSQLError, CursorError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return TaskListPage(items=items, next_cursor=next_cursor)


@router.post("/tasks", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreate,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskRead:
    try:
        return await tasks.create_task(session, current_user=user, payload=payload)
    except TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/tasks/{task_id}", response_model=TaskRead)
async def get_task(
    task_id: str,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskRead:
    full_id = await resolve_prefix(
        session, id_column=Task.id, discriminator_column=Task.title, key=task_id
    )
    try:
        return await tasks.get_task(session, full_id, current_user=user)
    except TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/tasks/{task_id}", response_model=TaskRead)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    session: SessionDep,
    user: CurrentUserDep,
) -> TaskRead:
    full_id = await resolve_prefix(
        session, id_column=Task.id, discriminator_column=Task.title, key=task_id
    )
    try:
        return await tasks.update_task(
            session, current_user=user, task_id=full_id, patch=payload
        )
    except TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/tasks/bulk-update", response_model=BulkResult)
async def bulk_update(
    payload: BulkPatchRequest,
    session: SessionDep,
    user: CurrentUserDep,
    filter: Annotated[str, Query(description="RSQL filter (обязателен)")],
) -> BulkResult:
    try:
        results, total, succeeded = await tasks.bulk_update(
            session, current_user=user, filter_str=filter, patch=payload.patch
        )
    except TooManyMatches as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RSQLError, CursorError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return BulkResult(results=results, total=total, succeeded=succeeded)


@router.post("/tasks/batch-update", response_model=BatchResult)
async def batch_update(
    payload: BulkPatchRequest,
    session: SessionDep,
    user: CurrentUserDep,
    filter: Annotated[str, Query(description="RSQL filter (обязателен)")],
) -> BatchResult:
    try:
        affected = await tasks.batch_update(
            session, current_user=user, filter_str=filter, patch=payload.patch
        )
    except TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except TooManyMatches as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except (RSQLError, CursorError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return BatchResult(affected=affected)


@router.post("/tasks/bulk-create", response_model=BulkCreateResult)
async def bulk_create(
    payload: BulkCreateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> BulkCreateResult:
    results = await tasks.bulk_create(session, current_user=user, items=payload.items)
    return BulkCreateResult(results=results)


@router.post(
    "/tasks/batch-create",
    response_model=BatchCreateResult,
    status_code=status.HTTP_201_CREATED,
)
async def batch_create(
    payload: BulkCreateRequest,
    session: SessionDep,
    user: CurrentUserDep,
) -> BatchCreateResult:
    try:
        ids = await tasks.batch_create(session, current_user=user, items=payload.items)
    except TaskNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return BatchCreateResult(task_ids=ids)


@router.get("/history", response_model=HistoryPage)
async def list_history(
    session: SessionDep,
    user: CurrentUserDep,
    task_id: Annotated[str | None, Query()] = None,
    user_email: Annotated[str | None, Query(alias="user_id")] = None,
    cursor: Annotated[str | None, Query()] = None,
) -> HistoryPage:
    """История по task_id или user_id (email). Ровно один параметр обязателен."""
    if task_id is None and user_email is None:
        raise HTTPException(status_code=400, detail="task_id or user_id is required")
    if task_id is not None and user_email is not None:
        raise HTTPException(
            status_code=400, detail="provide only one of task_id or user_id"
        )

    if task_id is not None:
        task_id = await resolve_prefix(
            session, id_column=Task.id, discriminator_column=Task.title, key=task_id
        )
        try:
            items, next_cursor = await history.list_history_for_task(
                session, task_id, cursor
            )
        except CursorError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return HistoryPage(
            items=[HistoryEvent.model_validate(i) for i in items],
            next_cursor=next_cursor,
        )

    # user_email path
    assert user_email is not None
    from tasks_service.user_resolver import resolve_and_cache_email

    if user_email == "me":
        target_user_id = user.id
    else:
        target_user_id_resolved = await resolve_and_cache_email(session, user_email)
        if target_user_id_resolved is None:
            raise HTTPException(status_code=404, detail=f"user not found: {user_email}")
        target_user_id = target_user_id_resolved
    try:
        items, next_cursor = await history.list_history_for_user(
            session, requester=user, target_user_id=target_user_id, cursor=cursor
        )
    except CursorError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return HistoryPage(
        items=[HistoryEvent.model_validate(i) for i in items],
        next_cursor=next_cursor,
    )
