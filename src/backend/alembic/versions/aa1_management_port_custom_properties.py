"""Add custom_properties table for management ports

Revision ID: aa1_mgmt_port_custom_props
Revises: z8_fix_nulls
Create Date: 2026-06-10

Stores key/value custom properties scoped to a management port (e.g. Neo4j
secret_scope, secret_key, username, database) that the Neo4j graph panel reads
to authenticate against Databricks-managed secrets.
"""

from alembic import op
import sqlalchemy as sa

revision = 'aa1_mgmt_port_custom_props'
down_revision = 'z8_fix_nulls'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'data_product_management_port_custom_properties',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('management_port_id', sa.String(), nullable=False),
        sa.Column('property', sa.String(), nullable=False),
        sa.Column('value', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['management_port_id'], ['data_product_management_ports.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_mgmt_port_custom_props_port_id',
        'data_product_management_port_custom_properties',
        ['management_port_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_mgmt_port_custom_props_port_id', table_name='data_product_management_port_custom_properties')
    op.drop_table('data_product_management_port_custom_properties')
