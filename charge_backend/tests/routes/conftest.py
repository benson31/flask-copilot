###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
Fixtures for database API route testing
"""

import pytest

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from typing import List

from charge_backend.charge_server import app
from charge_backend.database import crud
from charge_backend.database.models import Base, User, Project, Experiment
from charge_backend.database.routes import local, project, experiment
from charge_backend.database.deps import get_session, get_current_user

# FIXME: Move these to free functions in some other module?
from charge_backend.database.routes.project import delete_project

from httpx import ASGITransport, AsyncClient

from utils import (
    get_current_test_user,
    make_new_current_user,
    make_random_experiment,
    make_random_project,
)


@pytest.fixture(name="session", scope="module")
async def session_fix() -> AsyncSession:

    test_db_url = f"sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(
        test_db_url, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture(name="client", scope="module")
async def client_fix(session: AsyncSession) -> AsyncClient:
    async def local_session_override() -> AsyncSession:
        return session

    async def local_current_user_override() -> User:
        return get_current_test_user()

    app.dependency_overrides[get_session] = local_session_override
    app.dependency_overrides[get_current_user] = local_current_user_override

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest.fixture(name="current_user", scope="function")
async def current_user_fix(session: AsyncSession) -> User:
    user = await make_new_current_user(session)

    yield user

    await session.delete(user)
    await session.commit()


# @pytest.fixture(scope="function")
# def random_project(session: AsyncSession, current_user: User) -> Project:
#     project = await crud.create_project(
#         session=session, project=make_random_project(), user=current_user
#     )
#     yield project
#     await session.delete(project)
#     await session.commit()


# These return rather than yield because the current user will likely
# get "delete"'d, and that should cascade to cull projects.
@pytest.fixture(scope="function")
async def random_project(session: AsyncSession, current_user: User):
    project = await crud.create_project(
        session=session, project=make_random_project(), user=current_user
    )

    return project


@pytest.fixture(scope="function")
async def random_projects(
    session: AsyncSession, current_user: User, request
) -> List[Project]:
    marker = request.node.get_closest_marker("num_projects")
    if marker is None:
        num_projects = 2
    else:
        num_projects = marker.args[0]

    # I do not care that these projects are sequentially created.
    projects = [
        await crud.create_project(
            session=session, project=make_random_project(), user=current_user
        )
        for _ in range(num_projects)
    ]

    return projects


@pytest.fixture(scope="function")
async def random_experiment(
    session: AsyncSession, random_project: Project
) -> Experiment:
    experiment = await crud.create_experiment(
        session=session,
        experiment=make_random_experiment(),
        project=random_project,
    )

    return experiment


@pytest.fixture(scope="function")
async def random_experiments(
    session: AsyncSession, random_projects: Project, request
) -> List[List[Experiment]]:

    marker = request.node.get_closest_marker("num_experiments")
    if marker is None:
        num_experiments = 2
    else:
        num_experiments = marker.args[0]

    experiments = [
        [
            await crud.create_experiment(
                session=session,
                experiment=make_random_experiment(),
                project=project,
            )
            for _ in range(num_experiments)
        ]
        for project in random_projects
    ]

    return experiments
