###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
Definitions of FLASK database interaction models.
"""

from datetime import datetime, timezone
from sqlalchemy import func, Column, DateTime, ForeignKey, JSON
from sqlalchemy.orm import (
    mapped_column,
    relationship,
    DeclarativeBase,
    Mapped,
    MappedAsDataclass,
    Session,
)
from sqlalchemy.ext.hybrid import hybrid_property
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Any, List, Optional
import uuid


# The silly "one-true-base" base class to make all the SQLA stuff
# work correctly. Everyone calls it "Base", so we do too.
class Base(DeclarativeBase):
    pass


class TimestampSQLMixin:
    """Add columns tracking creation and modification times for objects."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )
    last_modified: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        server_onupdate=func.now(),
        nullable=False,
    )


# We need User notions now. Yippee. Starting SUPER simple. I don't
# care about name/email or anything like that. Just a UUID id and a
# list of owned projects.
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str]

    # Make life easier. Deleting a user deletes their projects.
    projects: Mapped[List["Project"]] = relationship(
        cascade="all, delete-orphan",
        order_by="Project.created_at",
        lazy="selectin",
    )


# FIXME (trb): Add event listeners so that when experiments get
# inserted/deleted/updated, Project 'last_modified' get updated
# appropriately.
class Project(Base, TimestampSQLMixin):
    """Top-level organizational concept in FLASK-Copilot. Projects
    are repositories of experiments grouped under a common name.

    SQL table name: "projects"

    """

    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))

    name: Mapped[str]

    experiments: Mapped[List["Experiment"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        order_by="Experiment.created_at",
        lazy="selectin",
    )


# FIXME (trb): (Maybe) Flesh out the context. An issue here is that we
# don't have a strong incentive to expose the fields at a finer level
# of granularity -- both the backend and the frontend have the
# "experiment" notion (and they're different notions), and neither
# would interact with the database (at this time) at any finer
# granularity than "experiment". So we can go through the exercise of
# expanding all of the fields and just making the "complicated" ones
# into JSON data, which will likely result in a more efficient
# encoding but otherwise simplify nothing (and, indeed, if we expand
# the array fields into their own tables, it would make the queries
# much more complex), or we can just use this until a real reason to
# expand things reveals itself. Note that one can run queries with
# `.where()` clauses based on JSON fields, see SQLA docs for examples.
class Experiment(Base, TimestampSQLMixin):
    """Top-level operational concept in FLASK-Copilot. Experiments
    contain all of the execution context.

    Experiments contain slightly different data depending on whether
    we consider the frontend or the backend (the latter is generally a
    subset of the former's notion). Additionally, (front-end)
    experiments contain a LOT of nested data structures, graph
    structures, and arrays, most of which does not need to be expanded
    into SQL tables. To ameliorate both of these concerns, we simply
    collapse the experiment data into a plain dict object (stored as
    JSON in the database). SQLA provides a mechanism for directly
    querying against JSON keys, and this is sufficient for now.

    SQL table name: "experiments"

    """

    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))

    data: Mapped[dict] = mapped_column(JSON)

    project: Mapped["Project"] = relationship(back_populates="experiments")

    # Auto-extraction of the name field
    #
    # FIXME (trb): Also consider "index_property" from "sqlalchemy.ext.indexable"
    @hybrid_property
    def name(self) -> str | None:
        return self.data.get("name")

    @name.setter
    def name(self, value: str) -> None:
        if self.data is None:
            self.data = {}
            self.data["name"] = value

    # Make it work in query expressions
    @name.expression
    def name(cls):
        return cls.data["name"].as_string()


##############################
# PYDANTIC MODELS (schemas)
##############################


# Timestamps are database artifacts, not user-settables. So we mark
# these 'required' and will only use them for the "*Response" models
# below.
class TimestampMixin:
    created_at: datetime
    last_modified: datetime


class UserBase(BaseModel):
    name: str


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: uuid.UUID

    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# To support the different "modes" with which the front-end does/will
# deal with this data, we present a few forms of these models.
# Projects can include no experiment data, experiment "metadata", or
# full experiment data.


class ProjectBase(BaseModel):
    name: str


class ProjectCreate(ProjectBase):
    pass


class ProjectMigrate(ProjectBase):
    id: uuid.UUID
    experiments: List["ExperimentUpdate"]  # A little type upcycling here.


# This is basically "ProjectMetadata". If we just need a simple
# reference to the Project ID or Name, this is sufficent.
class ProjectResponse(ProjectBase, TimestampMixin):
    id: uuid.UUID
    user_id: uuid.UUID
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# This version represents experiments only by their metadata.
class ProjectMetadataResponse(ProjectResponse):
    experiments: List["ExperimentMetadataResponse"] = []


# This provides a full set of fully populated experiments, with their
# full contexts fully joined at the database level. This most easily
# shims into the copilot front-end, especially when cached in
# LocalStorage.
class ProjectResponseWithExperiments(ProjectResponse):
    experiments: List["ExperimentResponse"] = []


# The only thing we can change on a project is the name.
class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None)


# NOTE (trb): Currently, the copilot frontend only passes a "name"
# field to the createProject function. So that's all we require here.
# The full context gets added with an "update", so we defer the
# addition of that field until that point.
class ExperimentBase(BaseModel):
    name: str


class ExperimentCreate(ExperimentBase):
    pass


class ExperimentResponseBase(BaseModel, TimestampMixin):
    id: uuid.UUID
    project_id: uuid.UUID


# This is just the "metadata" response. The "name" field gets
# auto-extracted from the JSON.
class ExperimentMetadataResponse(ExperimentResponseBase):
    name: str
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# FIXME (trb): (Maybe) Flesh out the context. See discussion at the
# Experiment SQL table class above.
#
# This is the full experiment data, left in the JSON/dict object. For
# now, the "name" that gets passed in the ExperimentCreate internally
# gets wrapped into the "data" dict, hence it not being explicit here.
class ExperimentResponse(ExperimentResponseBase):
    data: dict[str, Any]
    model_config = ConfigDict(
        alias_generator=to_camel,
        from_attributes=True,
        populate_by_name=True,
        serialize_by_alias=True,
    )


# FIXME (trb): (Maybe) Flesh out the context. See discussion at the
# Experiment SQL table class above.
class ExperimentUpdate(BaseModel):
    data: dict[str, Any] | None = Field(default=None)
