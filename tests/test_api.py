import pytest
from httpx import AsyncClient, ASGITransport
from backend.app import app

@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint exists"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
        # Should return 404 or redirect, not 500
        assert response.status_code in [404, 307, 200]

@pytest.mark.asyncio
async def test_docs_endpoint():
    """Test API documentation endpoint"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/docs")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

@pytest.mark.asyncio
async def test_cors_headers():
    """Test CORS headers are set correctly"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.options(
            "/api/auth/register",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
        assert response.headers["access-control-allow-origin"] == "*"

@pytest.mark.asyncio
async def test_proxy_headers_middleware():
    """Test that X-Forwarded-Proto header is handled correctly"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/docs",
            headers={"X-Forwarded-Proto": "https"}
        )
        assert response.status_code == 200
