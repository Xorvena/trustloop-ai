"""product brand/model/type/availability/image fields

Revision ID: 0002
Revises: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("products") as b:
        b.add_column(sa.Column("brand", sa.String(80), nullable=False, server_default=""))
        b.add_column(sa.Column("model", sa.String(120), nullable=False, server_default=""))
        b.add_column(sa.Column("product_type", sa.String(40), nullable=False, server_default=""))
        b.add_column(sa.Column("availability", sa.String(20), nullable=False, server_default="in_stock"))
        b.add_column(sa.Column("image_url", sa.String(500), nullable=True))
        b.add_column(sa.Column("image_source", sa.String(40), nullable=True))
        b.create_index("ix_products_brand", ["brand"])
        b.create_index("ix_products_product_type", ["product_type"])


def downgrade() -> None:
    with op.batch_alter_table("products") as b:
        b.drop_index("ix_products_product_type")
        b.drop_index("ix_products_brand")
        for c in ("image_source", "image_url", "availability", "product_type", "model", "brand"):
            b.drop_column(c)
