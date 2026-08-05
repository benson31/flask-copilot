###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
FastAPI dependency injection for database operations.
"""

import uuid
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated

from .crud import create_user, get_user_by_username
from .database import get_session
from .models import Experiment, Project, User, UserCreate

from loguru import logger


GetSession = Annotated[AsyncSession, Depends(get_session)]


# FIXME (trb): Is there any token verification I should be doing?
# (Update: BVE says "no" -- if we get "x-forwarded-user", that is
# assumed to be trusted input)
#
# If the production "/docs" endpoint is accessible to the public, we
# should do _something_ because those will expose the
# 'x-forwarded-user` as a plain text input field.


async def get_current_user(
    session: GetSession,
    x_forwarded_user: Annotated[str | None, Header()] = None,
) -> User:
    """Get the database representation of the current user.

    The username is extracted from the http header automatically. If
    the headers do not contain a user, "nobody" is used. This is
    useful for local testing (when users can be added manually) --
    "nobody" will never be auto-added.

    """

    username = x_forwarded_user or "nobody"
    db_user = await get_user_by_username(session, username)

    # Handle a new user automatically.
    #
    # NOTE (trb): "nobody" is treated specially, and it is never
    # auto-added. At time of writing, that's the default username
    # selected for the FlaskUserSession, so that's the one I've been
    # using for testing. In my testing, I create that username
    # manually. In production, we do not want to allow that username.
    if not db_user and username != "nobody":
        logger.info(f"Creating new user: {username}")
        db_user = await create_user(session, UserCreate(name=username))

    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    return db_user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def validate_project_id(
    session: GetSession, user: CurrentUser, project_id: uuid.UUID
) -> Project:
    """A helper function to verify the project id is valid and
    writeable by this user.

    """
    db_proj = await session.get(Project, project_id)
    if db_proj is None:
        raise HTTPException(status_code=404, detail="Invalid project id")
    if db_proj.user_id != user.id:
        raise HTTPException(status_code=403, detail="Bad project permissions")
    return db_proj


ValidatedProject = Annotated[Project, Depends(validate_project_id)]


async def validate_experiment_id(
    session: GetSession, project: ValidatedProject, experiment_id: uuid.UUID
) -> Experiment:
    """A helper function to verify the experiment id relates to a
    valid experiment that is owned by the specified project, which is
    validated to belong to the current user.

    """
    db_experiment = await session.get(Experiment, experiment_id)
    if db_experiment is None:
        raise HTTPException(status_code=404, detail="Invalid experiment id")
    if db_experiment.project_id != project.id:
        # FIXME (trb): I *think* 409 is the right code here? The user
        # is valid, and the user has permissions for this project. The
        # issue is that there's a mismatch between the experiment id
        # and the project that owns it.
        raise HTTPException(status_code=409, detail="Bad experiment")

    return db_experiment


ValidatedExperiment = Annotated[Experiment, Depends(validate_experiment_id)]
