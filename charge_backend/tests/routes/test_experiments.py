###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################

import pytest
import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from charge_backend.database.models import (
    Project,
    ProjectResponseWithExperiments,
    Experiment,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
)

from utils import make_new_current_user, make_random_experiment


async def test_create_experiment(client: AsyncClient, random_project: Project):
    exp_create = make_random_experiment()
    response = await client.post(
        f"/projects/{random_project.id}/experiments", json=exp_create.model_dump()
    )

    assert response.status_code == 200

    data = ExperimentResponse.model_validate(response.json())

    assert data.id is not None
    assert data.project_id == random_project.id
    assert "name" in data.data
    assert data.data["name"] == exp_create.name


async def test_experiment_create_invalid_name_fails(
    client: AsyncClient, random_project: Project
):

    response = await client.post(
        f"/projects/{random_project.id}/experiments", json={"name": 42}
    )

    assert response.status_code == 422


async def test_experiment_create_invalid_project_fails(client: AsyncClient):

    exp_create = make_random_experiment()
    nonsense_project_id = uuid.uuid4()

    response = await client.post(
        f"/projects/{nonsense_project_id}/experiments", json=exp_create.model_dump()
    )

    assert response.status_code == 404

    data = response.json()
    assert data["detail"] == "Invalid project id"


async def test_experiment_create_user_project_mismatch_fails(
    session: AsyncSession, client: AsyncClient, random_project: Project
):
    other_user = await make_new_current_user(session)

    exp_create = make_random_experiment()

    response = await client.post(
        f"/projects/{random_project.id}/experiments", json=exp_create.model_dump()
    )

    assert response.status_code == 403

    data = response.json()

    assert data["detail"] == "Bad project permissions"


@pytest.mark.num_projects(1)
@pytest.mark.num_experiments(3)
async def test_get_all_experiments(
    client: AsyncClient, random_projects: Project, random_experiments: List[Experiment]
):
    assert len(random_projects) == 1
    assert len(random_experiments) == 1

    project = random_projects[0]
    db_experiments = random_experiments[0]

    response = await client.get(f"/local/projects/{project.id}/experiments")

    assert response.status_code == 200

    experiments = [ExperimentResponse.model_validate(exp) for exp in response.json()]

    assert len(experiments) == len(db_experiments)
    assert all(exp.project_id == project.id for exp in experiments)


async def test_get_experiment_by_id(client: AsyncClient, random_experiment: Experiment):

    response = await client.get(
        f"/projects/{random_experiment.project_id}/experiments/{random_experiment.id}"
    )

    assert response.status_code == 200

    experiment = ExperimentResponse.model_validate(response.json())

    assert experiment.id == random_experiment.id
    assert experiment.project_id == random_experiment.project_id
    assert experiment.data == random_experiment.data


async def test_experiment_update(client: AsyncClient, random_experiment: Experiment):

    orig_data = random_experiment.data.copy()

    new_name = "awesome project"
    new_data = {"name": new_name, "new_field": "some other data"}

    assert "new field" not in random_experiment.data

    exp_update = ExperimentUpdate.model_validate({"data": new_data})

    experiment_id = random_experiment.id
    project_id = random_experiment.project_id
    response = await client.put(
        f"/projects/{project_id}/experiments/{experiment_id}",
        json=exp_update.model_dump(),
    )

    assert response.status_code == 200

    experiment = ExperimentResponse.model_validate(response.json())

    assert experiment.id == experiment_id
    assert experiment.project_id == project_id
    assert experiment.data == new_data


async def test_experiment_delete(client: AsyncClient, random_experiment: Experiment):

    response = await client.delete(
        f"/projects/{random_experiment.project_id}/experiments/{random_experiment.id}"
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


# FIXME (trb): Finish testing failure modes
