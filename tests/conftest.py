import os
import pytest

# Force SQLite test database URL before any import occurs
os.environ["DATABASE_URL"] = "sqlite:///./test.db"

from app.database.db import Base, engine

@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    # Create tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after test session completes
    Base.metadata.drop_all(bind=engine)
    # Clean up the test database file
    try:
        if os.path.exists("./test.db"):
            os.remove("./test.db")
    except Exception as e:
        print(f"Error removing test database file: {e}")
