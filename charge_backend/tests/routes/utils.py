from sqlalchemy.ext.asyncio import AsyncSession

from charge_backend.database.models import (
    User,
    UserCreate,
    ProjectCreate,
    ExperimentCreate,
)
from charge_backend.database.crud import create_user

CURRENT_TEST_USER = None
NEXT_USER_ID = 0
NEXT_PROJECT_ID = 0
NEXT_EXPERIMENT_ID = 0


def set_current_test_user(user: User | None = None) -> None:
    global CURRENT_TEST_USER
    CURRENT_TEST_USER = user


def get_current_test_user() -> None:
    return CURRENT_TEST_USER


def make_random_user() -> UserCreate:
    global NEXT_USER_ID
    NEXT_USER_ID += 1
    return UserCreate(name=f"test_user_{NEXT_USER_ID}")


def make_random_project() -> ProjectCreate:
    global NEXT_PROJECT_ID
    NEXT_PROJECT_ID += 1
    return ProjectCreate(name=f"test_project_{NEXT_PROJECT_ID}")


def make_random_experiment() -> ExperimentCreate:
    global NEXT_EXPERIMENT_ID
    NEXT_EXPERIMENT_ID += 1
    name = f"test_experiment_{NEXT_EXPERIMENT_ID}"
    return ExperimentCreate(
        name=f"test_experiment_{NEXT_EXPERIMENT_ID}",
    )


async def make_new_current_user(session: AsyncSession):
    user_create = make_random_user()
    db_user = await create_user(session, user_create)
    set_current_test_user(db_user)
    return db_user
