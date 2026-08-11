###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from charge_backend.database.models import User

from utils import make_new_current_user, make_random_user


async def test_user_create(client: AsyncClient):
    user_create = make_random_user()
    response = await client.post("/local/users", json=user_create.model_dump())
    data = response.json()

    assert response.status_code == 200
    assert data["name"] == user_create.name
    assert data["id"] is not None


async def test_user_create_invalid_name(client: AsyncClient):

    response = await client.post("/local/users", json={"name": 13})
    assert response.status_code == 422


async def test_user_create_user_exists(client: AsyncClient, current_user: User):

    response = await client.post("/local/users", json={"name": current_user.name})
    assert response.status_code == 409


async def test_user_delete(session: AsyncSession, client: AsyncClient):
    # Do NOT use the current_user fixture, which deletes the user.
    db_user = await make_new_current_user(session)

    response = await client.delete("/local/users/me")

    assert response.status_code == 200

    data = response.json()

    assert data["ok"] is True
