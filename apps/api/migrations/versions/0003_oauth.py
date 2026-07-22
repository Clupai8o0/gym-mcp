"""oauth — Authorization-Server tables (docs/02 §OAuth, docs/05).

Adds the four OAuth 2.1 AS tables deferred out of the ``0001_init`` baseline:
``oauth_clients`` (DCR-registered chat clients), ``oauth_authorization_codes``
(short-lived, single-use, PKCE-bound), ``oauth_access_tokens`` (opaque bearer, audience-
bound), and ``oauth_refresh_tokens`` (rotated, chain-revocable). Every credential column
holds only a hash. Generated from the models via ``alembic revision --autogenerate`` and
tidied for readability; ``alembic check`` is clean against ``app/models/oauth.py``.

Revision ID: 0003_oauth
Revises: 0002_seed_skills
Create Date: 2026-07-22 02:40:12.294394+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003_oauth"
down_revision: str | None = "0002_seed_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # oauth_clients first: the code/token tables FK to its unique client_id.
    op.create_table(
        "oauth_clients",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("client_secret_hash", sa.Text(), nullable=True),
        sa.Column("client_name", sa.Text(), nullable=True),
        sa.Column("redirect_uris", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column(
            "grant_types",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{authorization_code,refresh_token}'::text[]"),
            nullable=False,
        ),
        sa.Column("token_endpoint_auth_method", sa.Text(), server_default="none", nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("is_dynamic", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("oauth_clients_pkey")),
        sa.UniqueConstraint("client_id", name=op.f("oauth_clients_client_id_key")),
    )
    op.create_table(
        "oauth_authorization_codes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("code_challenge_method", sa.Text(), server_default="S256", nullable=False),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "code_challenge_method = 'S256'",
            name=op.f("oauth_authorization_codes_code_challenge_method_check"),
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("oauth_authorization_codes_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("oauth_authorization_codes_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("oauth_authorization_codes_pkey")),
        sa.UniqueConstraint("code_hash", name=op.f("oauth_authorization_codes_code_hash_key")),
    )
    op.create_table(
        "oauth_access_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("oauth_access_tokens_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("oauth_access_tokens_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("oauth_access_tokens_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("oauth_access_tokens_token_hash_key")),
    )
    op.create_index(
        op.f("oauth_access_tokens_user_id_idx"),
        "oauth_access_tokens",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("resource", sa.Text(), nullable=True),
        sa.Column(
            "chain_id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("rotated_from", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["client_id"],
            ["oauth_clients.client_id"],
            name=op.f("oauth_refresh_tokens_client_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rotated_from"],
            ["oauth_refresh_tokens.id"],
            name=op.f("oauth_refresh_tokens_rotated_from_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("oauth_refresh_tokens_user_id_fkey"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("oauth_refresh_tokens_pkey")),
        sa.UniqueConstraint("token_hash", name=op.f("oauth_refresh_tokens_token_hash_key")),
    )
    op.create_index(
        op.f("oauth_refresh_tokens_chain_id_idx"),
        "oauth_refresh_tokens",
        ["chain_id"],
        unique=False,
    )
    op.create_index(
        op.f("oauth_refresh_tokens_user_id_idx"),
        "oauth_refresh_tokens",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("oauth_refresh_tokens_user_id_idx"), table_name="oauth_refresh_tokens")
    op.drop_index(op.f("oauth_refresh_tokens_chain_id_idx"), table_name="oauth_refresh_tokens")
    op.drop_table("oauth_refresh_tokens")
    op.drop_index(op.f("oauth_access_tokens_user_id_idx"), table_name="oauth_access_tokens")
    op.drop_table("oauth_access_tokens")
    op.drop_table("oauth_authorization_codes")
    op.drop_table("oauth_clients")
