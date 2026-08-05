###############################################################################
## Copyright 2025-2026 Lawrence Livermore National Security, LLC.
## See the top-level LICENSE file for details.
##
## SPDX-License-Identifier: Apache-2.0
###############################################################################
"""
Settings controlling various aspects of SQL database interaction.
"""

from pydantic import computed_field, AnyUrl, UrlConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict

from typing import Annotated, Literal

# MariaDB stuff
#
# NOTE (trb): I don't know that we *need* the MariaDB-specific schemes
# here -- I did not use any MariaDB-specific features or options when
# doing the initial setup. However, I do know that we are targeting
# MariaDB, not MySQL, so I may as well just be that specific.
#
# NOTE (trb): As for aiomysql vs asyncmy, both seem fine. The former
# is older and has more GH stars; the latter claims to have improved
# performance with a Cython-compiled core. I'm leaving both in the
# "allowed_schemes" list so we can try both and see if it makes any
# difference for us. My hope/guess is "no".
MariaDbAsyncDsn = Annotated[
    AnyUrl,
    UrlConstraints(
        allowed_schemes=[
            "mariadb+aiomysql",
            "mariadb+asyncmy",
        ],
        host_required=True,
        default_port=3306,
    ),
]


# Right now I'm just exposing database stuff; maybe other fields later?
class FlaskDbSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="charge_backend/db_settings.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Currently this is only used to remove some endpoints from the
    # API; may have other uses down the road?
    environment: Literal["deploy", "local"] = "local"

    # Controls whether SQLAlchemy echos SQL to stderr.
    verbose_sql: bool = False

    # MariaDB stuff ("deploy" env only)
    mariadb_host: str = ""
    mariadb_name: str = ""
    mariadb_password: str = ""
    mariadb_port: int = 3306
    mariadb_scheme: Literal["mariadb+asyncmy", "mariadb+aiomysql"] = "mariadb+asyncmy"
    mariadb_user: str = ""

    @computed_field
    @property
    def mariadb_uri() -> MariaDbAsyncDsn:
        return MariaDbAsyncDsn.build(
            host=self.mariadb_host,
            password=self.mariadb_password,
            path=self.mariadb_name,
            port=self.mariadb_port,
            scheme=self.mariadb_scheme,
            username=self.mariadb_user,
        )

    # SQLite config ("local" or "test")
    sqlite_uri: AnyUrl = "sqlite+aiosqlite:///changeme-database.db"

    @computed_field
    @property
    def sqla_db_uri(self) -> AnyUrl:
        return self.mariadb_uri if self.environment == "deploy" else self.sqlite_uri


db_settings: FlaskDbSettings = FlaskDbSettings()
