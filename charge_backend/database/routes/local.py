###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
API routes for FLASK-copilot local development and testing.
"""

# NOTE (trb): These are handy utilities that I've used a bunch for
# manually testing the database API functionality throughout
# development. For now, they're set aside here and only loaded when
# using a "local" or "test" environment (some actually have tests!).

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from typing import List

from charge_backend.database import crud
from charge_backend.database.deps import GetSession, CurrentUser, ValidatedProject
from charge_backend.database.models import (
    Experiment,
    ExperimentMetadataResponse,
    ExperimentResponse,
    Project,
    ProjectMetadataResponse,
    ProjectResponseWithExperiments,
    UserCreate,
    UserResponse,
)


router = APIRouter(prefix="/local", tags=["local"])


@router.post("/users", response_model=UserResponse)
async def create_user(*, session: GetSession, user: UserCreate):
    existing_user = await crud.get_user_by_username(session, user.name)
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="username already exists")
    return await crud.create_user(session, user)


@router.delete("/users/me")
async def delete_user_me(session: GetSession, user: CurrentUser):
    """
    Delete the current user
    """

    await session.delete(user)
    await session.commit()
    return {"ok": True}


@router.get("/projects/debug-all", response_model=List[ProjectResponseWithExperiments])
async def get_all_projects(
    *,
    session: GetSession,
):
    """
    Retrieve all projects in the database
    """
    return (await session.scalars(select(Project))).all()


@router.get("/projects/debug-all/meta", response_model=List[ProjectMetadataResponse])
async def get_all_projects_metadata(
    *,
    session: GetSession,
):
    """
    Retrieve all projects in the database, metadata only.
    """
    return (await session.scalars(select(Project))).all()


@router.get("/experiments/debug-all", response_model=List[ExperimentResponse])
async def get_all_experiments(
    *,
    session: GetSession,
):
    """
    Retrieve all experiments in the database
    """
    return (await session.scalars(select(Experiment))).all()


@router.get(
    "/experiments/debug-all/meta", response_model=List[ExperimentMetadataResponse]
)
async def get_all_experiments_metadata(
    *,
    session: GetSession,
):
    """
    Retrieve all experiments in the database, metadata only.
    """
    return (await session.scalars(select(Experiment))).all()


@router.get(
    "/projects/{project_id}/experiments", response_model=List[ExperimentResponse]
)
async def get_project_experiments(
    *,
    session: GetSession,
    validated_project: ValidatedProject,
):
    """
    Retrieve all Experiments associated with 'project_id'
    """
    await session.refresh(validated_project)
    return validated_project.experiments


@router.get(
    "/projects/{project_id}/experiments/meta",
    response_model=List[ExperimentMetadataResponse],
)
async def get_project_experiments_metadata(
    *,
    session: GetSession,
    validated_project: ValidatedProject,
):
    """
    Retrieve all Experiments associated with 'project_id', metadata only
    """
    await session.refresh(validated_project)
    return validated_project.experiments
