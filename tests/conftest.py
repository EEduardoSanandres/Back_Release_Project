import pytest
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from backend.app.db import db

# Use a test database
TEST_DB_NAME = "tdp_prototype_test"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
async def cleanup_database():
    """Clean up test database before and after each test"""
    # Setup: clean before test
    test_collections = ["users", "projects", "user_stories", "dependencies", "project_configs"]
    
    for collection_name in test_collections:
        try:
            await db[collection_name].delete_many({"email": {"$regex": "test"}})
            await db[collection_name].delete_many({"code": {"$regex": "TEST"}})
        except:
            pass
    
    yield
    
    # Teardown: clean after test
    for collection_name in test_collections:
        try:
            await db[collection_name].delete_many({"email": {"$regex": "test"}})
            await db[collection_name].delete_many({"code": {"$regex": "TEST"}})
        except:
            pass
