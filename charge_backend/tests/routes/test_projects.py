###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################

import pytest
import uuid

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from charge_backend.database.models import (
    User,
    Project,
    ProjectResponse,
    ProjectUpdate,
    ProjectResponseWithExperiments,
    Experiment,
)

from utils import (
    make_new_current_user,
    make_random_project,
)


async def test_project_create(client: AsyncClient, current_user: User):
    project_create = make_random_project()

    response = await client.post("/projects", json=project_create.model_dump())

    assert response.status_code == 200

    data = ProjectResponse.model_validate(response.json())

    assert data.name == project_create.name
    assert data.id is not None
    assert data.user_id == current_user.id


async def test_project_create_invalid_name_fails(
    client: AsyncClient, current_user: User
):
    response = await client.post("/projects", json={"name": 42})
    assert response.status_code == 422


async def test_project_update(
    client: AsyncClient,
    random_project: Project,
):

    project_update = ProjectUpdate(name="renamed project")

    response = await client.put(
        f"/projects/{random_project.id}", json=project_update.model_dump()
    )

    assert response.status_code == 200

    data = ProjectResponse.model_validate(response.json())

    assert data.id == random_project.id  # id doesn't change
    assert data.name == "renamed project"


async def test_project_update_with_bad_data_fails(
    client: AsyncClient, random_project: Project
):

    response = await client.put(f"/projects/{random_project.id}", json={"name": 42})

    assert response.status_code == 422


async def test_project_update_with_nonsense_data_noop(
    client: AsyncClient, random_project: Project
):

    response = await client.put(
        f"/projects/{random_project.id}", json={"nonsense": "field"}
    )

    assert response.status_code == 200  # This should be accepted.

    project = ProjectResponse.model_validate(response.json())

    assert project.id == random_project.id
    assert project.user_id == random_project.user_id
    assert project.name == random_project.name
    assert project.last_modified == random_project.last_modified
    assert project.created_at == random_project.created_at


async def test_project_update_invalid_id_fails(client: AsyncClient, current_user: User):

    nonsense_id = uuid.uuid4()

    response = await client.put(
        f"/projects/{nonsense_id}", json={"name": "best project ever"}
    )

    assert response.status_code == 404


async def test_update_project_from_another_user_fails(
    session: AsyncSession, client: AsyncClient, random_project: Project
):

    other_user = await make_new_current_user(session)

    response = await client.put(
        f"/projects/{random_project.id}", json={"name": "my project now"}
    )

    assert response.status_code == 403


@pytest.mark.num_projects(2)
async def test_get_all_projects(
    client: AsyncClient, current_user: User, random_projects: List[Project]
):

    response = await client.get("/projects")

    assert response.status_code == 200

    project_responses = [
        ProjectResponseWithExperiments.model_validate(p) for p in response.json()
    ]

    assert len(project_responses) == 2
    assert any(p.name == random_projects[0].name for p in project_responses)
    assert any(p.name == random_projects[1].name for p in project_responses)
    assert any(p.id == random_projects[0].id for p in project_responses)
    assert any(p.id == random_projects[1].id for p in project_responses)
    assert all(p.user_id == current_user.id for p in project_responses)


async def test_get_project_by_id(
    client: AsyncClient, current_user: User, random_project: Project
):

    response = await client.get(f"/projects/{random_project.id}")

    assert response.status_code == 200

    project = ProjectResponseWithExperiments.model_validate(response.json())

    assert project.id == random_project.id
    assert project.user_id == current_user.id


# NOTE (trb): I need the "current_user" here so I don't error out
# checking for the current user. There _might_ be a valid current user
# set if one wasn't cleaned up previously in the module, but there is
# no guarantee, and the each test is designed to stand on its own.
async def test_get_project_with_invalid_id_fails(
    client: AsyncClient, current_user: User
):

    nonsense_id = uuid.uuid4()
    response = await client.get(f"/projects/{nonsense_id}")

    assert response.status_code == 404


async def test_get_project_from_another_user_fails(
    session: AsyncSession, client: AsyncClient, random_project: Project
):

    other_user = await make_new_current_user(session)

    response = await client.get(f"/projects/{random_project.id}")

    assert response.status_code == 403


@pytest.mark.num_projects(2)
async def test_delete_project(
    session: AsyncSession,
    client: AsyncClient,
    current_user: User,
    random_projects: List[Project],
):

    await session.refresh(current_user)

    assert len(current_user.projects) == 2

    response = await client.delete(f"/projects/{random_projects[0].id}")

    assert response.status_code == 200

    await session.refresh(current_user)

    assert len(current_user.projects) == 1


async def test_delete_project_invalid_id_fails(client: AsyncClient, current_user: User):

    nonsense_id = uuid.uuid4()
    response = await client.delete(f"/projects/{nonsense_id}")

    assert response.status_code == 404


async def test_delete_project_of_another_user_fails(
    session: AsyncSession, client: AsyncClient, random_project: Project
):

    other_user = await make_new_current_user(session)

    response = await client.delete(f"/projects/{random_project.id}")

    assert response.status_code == 403


async def test_migrate_projects_all_added(
    session: AsyncSession,
    client: AsyncClient,
):

    # I want these later.
    project_ids = [uuid.uuid4() for _ in range(2)]

    # Projects come in from the front-end with UUID ids
    input_projects = [
        {
            "name": f"project_{i}",
            "id": str(proj_id),
            "experiments": [
                {
                    "data": {
                        "name": f"experiment_{i}_{j}",
                        "foo": f"some data for experiment_{i}_{j}",
                    },
                }
                for j in range(2)
            ],
        }
        for i, proj_id in enumerate(project_ids)
    ]

    response = await client.post(f"/projects/migrate", json=input_projects)

    # Check HTTP response
    assert response.status_code == 200

    result = response.json()

    assert result["ok"] is True
    assert result["added"] == 2

    # Verify the database
    stmt = select(Project).where(Project.id.in_(project_ids))
    db_projects = (await session.scalars(stmt)).all()

    # All expected projects are found.
    assert len(db_projects) == len(project_ids)

    # Each project has 2 experiments
    assert all(len(db_proj.experiments) == 2 for db_proj in db_projects)

    # Each experiment has "data.name" and "data.foo"
    assert all(
        all(
            all(k in experiment.data for k in ("name", "foo"))
            for experiment in project.experiments
        )
        for project in db_projects
    )


async def test_migrate_projects_existing_id(
    session: AsyncSession,
    client: AsyncClient,
    random_project: Project,
    random_experiment: Experiment,
):

    project_ids = [random_project.id, uuid.uuid4()]

    input_projects = [
        {
            "name": f"project_{i}",
            "id": str(proj_id),
            "experiments": [
                {
                    "data": {
                        "name": f"experiment_{i}_{j}",
                        "foo": f"some data for experiment_{i}_{j}",
                    },
                }
                for j in range(2)
            ],
        }
        for i, proj_id in enumerate(project_ids)
    ]

    response = await client.post(f"/projects/migrate", json=input_projects)

    # Check HTTP response
    assert response.status_code == 200

    result = response.json()

    assert result["ok"] is True
    assert result["added"] == 1

    # Verify the database
    stmt = select(Project).where(Project.id.in_(project_ids))
    db_projects = (await session.scalars(stmt)).all()

    original_project = next((p for p in db_projects if p.id == random_project.id), None)
    assert original_project is not None
    assert original_project.experiments == random_project.experiments

    new_project = next((p for p in db_projects if p.id != random_project.id), None)
    assert new_project is not None
    assert all(
        all(k in experiment.data for k in ("name", "foo"))
        for experiment in new_project.experiments
    )

    # Repeat with the same input_projects.
    response = await client.post(f"/projects/migrate", json=input_projects)

    # Check HTTP response
    assert response.status_code == 200

    result = response.json()

    assert result["ok"] is True
    assert result["added"] == 0


async def test_migrate_projects_uuid_collision(
    session: AsyncSession,
    client: AsyncClient,
    random_project: Project,
    random_experiment: Experiment,
):

    project_ids = [random_project.id, uuid.uuid4()]

    # Now pop over to a new user
    other_user = await make_new_current_user(session)

    input_projects = [
        {
            "name": f"project_{i}",
            "id": str(proj_id),
            "experiments": [
                {
                    "data": {
                        "name": f"experiment_{i}_{j}",
                        "foo": f"some data for experiment_{i}_{j}",
                    },
                }
                for j in range(2)
            ],
        }
        for i, proj_id in enumerate(project_ids)
    ]

    response = await client.post(f"/projects/migrate", json=input_projects)

    assert response.status_code == 200

    result = response.json()

    assert result["ok"] is True
    assert result["added"] == 2
    assert len(result["new_ids"]) == 1
    assert str(project_ids[0]) in result["new_ids"]
