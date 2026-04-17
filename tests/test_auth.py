import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app

@pytest.mark.asyncio
async def test_register_user_success():
    """Test successful user registration"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "test@example.com",
                "name": "Test User",
                "password": "Test123",
                "role": "student"
            }
        )
        assert response.status_code == 201
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert data["role"] == "student"
        assert "id" in data
        assert "created_at" in data

@pytest.mark.asyncio
async def test_register_user_invalid_email():
    """Test user registration with invalid email"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "invalid-email",
                "name": "Test User",
                "password": "Test123",
                "role": "student"
            }
        )
        assert response.status_code == 422

@pytest.mark.asyncio
async def test_register_user_short_password():
    """Test user registration with short password"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/auth/register",
            json={
                "email": "test2@example.com",
                "name": "Test User",
                "password": "12345",
                "role": "student"
            }
        )
        assert response.status_code == 422

@pytest.mark.asyncio
async def test_hash_password():
    """Test password hashing"""
    from backend.api.services.auth_service import AuthService
    
    password = "TestPassword123"
    hashed = AuthService.hash_password(password)
    
    # Hash should not be the same as password
    assert hashed != password
    
    # Should start with bcrypt identifier
    assert hashed.startswith("$2b$")
    
    # Verify password works
    assert AuthService.verify_password(password, hashed)
    
    # Wrong password should fail
    assert not AuthService.verify_password("WrongPassword", hashed)

@pytest.mark.asyncio
async def test_hash_password_long():
    """Test password hashing with long password (near 72 byte limit)"""
    from backend.api.services.auth_service import AuthService
    
    # 72 character password (72 bytes in ASCII)
    password = "a" * 72
    hashed = AuthService.hash_password(password)
    
    assert hashed.startswith("$2b$")
    assert AuthService.verify_password(password, hashed)
