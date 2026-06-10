"""Merge aa1_mgmt_port_custom_props and f1_merge_aa9_e2 heads

Revision ID: aa2_merge_heads
Revises: aa1_mgmt_port_custom_props, f1_merge_aa9_e2
Create Date: 2026-06-10
"""

from alembic import op

revision = 'aa2_merge_heads'
down_revision = ('aa1_mgmt_port_custom_props', 'f1_merge_aa9_e2')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
