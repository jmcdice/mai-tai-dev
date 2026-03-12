"""System-wide settings stored in the database."""

from sqlalchemy import Column, String, Text
from app.db.base import Base


class SystemSetting(Base):
    """Key-value store for system settings that admins can toggle at runtime."""

    __tablename__ = "system_settings"

    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=False, default="")
