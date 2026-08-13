###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
Any CRUD-related operations needed for database interaction.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import (
    Experiment,
    ExperimentCreate,
    Project,
    ProjectCreate,
    User,
    UserCreate,
)

# These are used by testing or other backend functions, which is why
# they're extracted here (rather than just calling the endpoints
# directly). It's not strictly necessary to extract these, but I like
# the separation of concerns.


async def create_user(session: AsyncSession, user: UserCreate) -> User:
    db_user = User(**user.model_dump())
    session.add(db_user)
    await session.commit()
    await session.refresh(db_user)
    return db_user


async def get_user_by_username(session: AsyncSession, username: str) -> User:
    statement = select(User).where(User.name == username)
    db_user = await session.scalar(statement)
    return db_user


async def create_project(
    session: AsyncSession, project: ProjectCreate, user: User
) -> Project:
    proj_dict = project.model_dump(by_alias=False)
    proj_dict["user_id"] = user.id
    db_proj = Project(**proj_dict)
    session.add(db_proj)
    await session.commit()
    await session.refresh(db_proj)
    return db_proj


async def create_experiment(
    session: AsyncSession,
    experiment: ExperimentCreate,
    project: Project,
) -> Experiment:

    db_experiment = Experiment(
        project_id=project.id, data=experiment.model_dump(by_alias=False)
    )
    session.add(db_experiment)
    await session.commit()
    await session.refresh(db_experiment)
    await session.refresh(project)
    return db_experiment
