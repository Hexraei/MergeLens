from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from app.database.db import Base

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)  # e.g. "owner/repo"
    git_url = Column(String, nullable=False)
    provider = Column(String, default="github")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    indexing_status = Column(String, default="pending")  # pending, indexing, completed, failed
    last_indexed_at = Column(DateTime, nullable=True)
    dependency_graph_json = Column(JSON, nullable=True)
    call_graph_json = Column(JSON, nullable=True)

    dependencies = relationship("Dependency", back_populates="repository", cascade="all, delete-orphan")
    reports = relationship("AnalysisReport", back_populates="repository", cascade="all, delete-orphan")
    symbols = relationship("Symbol", back_populates="repository", cascade="all, delete-orphan")
    api_usages = relationship("ApiUsage", back_populates="repository", cascade="all, delete-orphan")


class Dependency(Base):
    __tablename__ = "dependencies"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, index=True, nullable=False)  # e.g. "fastapi"
    version = Column(String, nullable=False)  # e.g. "0.110.0"
    file_path = Column(String, nullable=False)  # e.g. "requirements.txt" or "pyproject.toml"
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    repository = relationship("Repository", back_populates="dependencies")


class AnalysisReport(Base):
    __tablename__ = "analysis_reports"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    pr_number = Column(Integer, nullable=False)
    dependency_name = Column(String, nullable=False)
    from_version = Column(String, nullable=False)
    to_version = Column(String, nullable=False)
    priority_score = Column(Integer, default=0)  # 0 to 100
    risk_score = Column(String, default="low")  # low, medium, high, critical
    confidence_score = Column(Integer, default=0)  # 0 to 100
    recommendation = Column(String, nullable=False)  # e.g., "merge" or "hold"
    report_data = Column(JSON, nullable=False)  # complete details as JSON
    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="reports")


class Symbol(Base):
    __tablename__ = "symbols"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, index=True, nullable=False)
    type = Column(String, nullable=False)  # class, function, method
    file_path = Column(String, nullable=False)
    start_line = Column(Integer, nullable=False)
    end_line = Column(Integer, nullable=False)
    metadata_json = Column(JSON, nullable=True)  # stores docstrings, parameters, return type, superclasses, decorators
    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="symbols")


class ApiUsage(Base):
    __tablename__ = "api_usages"

    id = Column(Integer, primary_key=True, index=True)
    repository_id = Column(Integer, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False)
    package_name = Column(String, index=True, nullable=False)  # e.g., "requests"
    imported_symbol = Column(String, index=True, nullable=True)  # e.g., "get"
    file_path = Column(String, nullable=False)
    line_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    repository = relationship("Repository", back_populates="api_usages")


class ReleaseFact(Base):
    __tablename__ = "release_facts"

    id = Column(Integer, primary_key=True, index=True)
    package_name = Column(String, index=True, nullable=False)
    from_version = Column(String, nullable=False)
    to_version = Column(String, nullable=False)
    release_notes_raw = Column(String, nullable=True)
    breaking_apis_json = Column(JSON, nullable=True)
    behavior_changes_json = Column(JSON, nullable=True)
    security_fixes_json = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
