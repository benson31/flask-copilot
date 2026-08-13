###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
API routes related to FLASK-copilot projects.
"""

import uuid
from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.orm import Bundle, aliased

from typing import List

from charge_backend.database import crud
from charge_backend.database.deps import GetSession, CurrentUser, ValidatedProject
from charge_backend.database.models import (
    Project,
    Experiment,
    ExperimentMetadataResponse,
    ProjectCreate,
    ProjectMigrate,
    ProjectResponse,
    ProjectMetadataResponse,
    ProjectResponseWithExperiments,
    ProjectUpdate,
)


router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    *, session: GetSession, project: ProjectCreate, user: CurrentUser
):
    return await crud.create_project(session, project, user)


# This function will receive a list of projects from the backend. If a
# project exists in the database already, it will be removed from the
# list of migrating projects. Any new projects will be created and
# added to the database.
@router.post("/migrate")
async def migrate_projects(
    *, session: GetSession, projects: List[ProjectMigrate], user: CurrentUser
):
    proj_ids = [project.id for project in projects]
    id_query = select(Project.id).where(Project.id.in_(proj_ids))
    id_query_results = await session.execute(id_query)
    existing_ids = set(id_query_results.scalars().all())

    # Short-circuit if all ids exist
    if len(existing_ids) != len(proj_ids):
        # Filter to ONLY the missing projects.
        proj_dicts = [
            project.model_dump(by_alias=False)
            for project in projects
            if project.id not in existing_ids
        ]

        db_projects = [
            Project(
                name=proj_dict["name"],
                id=proj_dict["id"],
                user_id=user.id,
                experiments=[
                    Experiment(
                        project_id=proj_dict["id"],
                        **experiment_dict,
                    )
                    for experiment_dict in proj_dict["experiments"]
                ],
            )
            for proj_dict in proj_dicts
        ]

        session.add_all(db_projects)
        await session.commit()

    # In the frontend, we call loadProjects way too much, and we will
    # call it right after this endpoint. As such, there's no benefit
    # to sending all that info yet another time, so we just send a
    # simple confirmation message.
    return {"ok": True, "added": len(proj_ids) - len(existing_ids)}


@router.get("", response_model=List[ProjectResponseWithExperiments])
async def get_projects(
    *,
    session: GetSession,
    current_user: CurrentUser,
):
    await session.refresh(current_user)
    return current_user.projects


@router.get("/meta", response_model=List[ProjectMetadataResponse])
async def get_projects_metadata(
    *,
    session: GetSession,
    current_user: CurrentUser,
):
    await session.refresh(current_user)
    return current_user.projects


@router.get("/{project_id}", response_model=ProjectResponseWithExperiments)
async def get_project(
    *,
    session: GetSession,
    db_project: ValidatedProject,
):
    return db_project


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    *,
    session: GetSession,
    db_project: ValidatedProject,
    project_update: ProjectUpdate,
):
    update_dict = project_update.model_dump(by_alias=False, exclude_unset=True)
    for key, value in update_dict.items():
        setattr(db_project, key, value)
    await session.commit()
    await session.refresh(db_project)
    return db_project


@router.delete("/{project_id}")
async def delete_project(
    *,
    session: GetSession,
    db_project: ValidatedProject,
):
    await session.delete(db_project)
    await session.commit()
    return {"ok": True}
