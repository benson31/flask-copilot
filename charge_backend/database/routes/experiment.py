###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
API routes related to FLASK-copilot experiments.
"""

from fastapi import APIRouter

from charge_backend.database import crud
from charge_backend.database.deps import (
    GetSession,
    ValidatedProject,
    ValidatedExperiment,
)
from charge_backend.database.models import (
    Experiment,
    ExperimentCreate,
    ExperimentResponse,
    ExperimentUpdate,
)

# The copilot interaction always carries the project_id in the
# {java,type}script interfaces. So I may as well use the nested route.
router = APIRouter(prefix="/projects/{project_id}/experiments", tags=["experiments"])


@router.post("", response_model=ExperimentResponse)
async def create_experiment(
    *,
    session: GetSession,
    experiment: ExperimentCreate,
    validated_project: ValidatedProject,
) -> Experiment:
    return await crud.create_experiment(session, experiment, validated_project)


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResponse,
)
async def get_experiment(*, db_experiment: ValidatedExperiment):
    return db_experiment


@router.put(
    "/{experiment_id}",
    response_model=ExperimentResponse,
)
async def update_experiment(
    *,
    session: GetSession,
    db_experiment: ValidatedExperiment,
    exp_update: ExperimentUpdate,
) -> Experiment:
    update_dict = exp_update.model_dump(by_alias=False, exclude_unset=True)

    if "data" in update_dict:
        new_data = update_dict.pop("data")

        # Merge dictionaries with update semantics
        db_experiment.data = db_experiment.data | new_data
        # NOTE (trb): CANNOT update in-place because sqlalchemy will
        # not recognize that subfields in the JSON have changed! To
        # remedy this, we could use a MutableDict type or just
        # reassign the field.

    # Other fields use assignment semantics
    for key, value in update_dict.items():
        setattr(db_experiment, key, value)

    session.add(db_experiment)
    await session.commit()
    await session.refresh(db_experiment)

    return db_experiment


@router.delete("/{experiment_id}")
async def delete_experiment(
    *,
    session: GetSession,
    db_experiment: ValidatedExperiment,
):
    await session.delete(db_experiment)
    await session.commit()
    return {"ok": True}
