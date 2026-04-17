import pytest
from datetime import date
from pydantic import ValidationError
from backend.api.schemas.requests import UserCreateIn, ProjectConfigCreateIn
from backend.api.schemas.responses import ReleasePlanningOut, DashboardStatsOut, ProjectStatsOut

def test_user_create_in_valid():
    """Test valid user creation schema"""
    user = UserCreateIn(
        email="test@example.com",
        name="Test User",
        password="Test123",
        role="student"
    )
    assert user.email == "test@example.com"
    assert user.name == "Test User"
    assert user.password == "Test123"
    assert user.role == "student"

def test_user_create_in_invalid_email():
    """Test user creation with invalid email"""
    with pytest.raises(ValidationError):
        UserCreateIn(
            email="not-an-email",
            name="Test User",
            password="Test123",
            role="student"
        )

def test_user_create_in_short_password():
    """Test user creation with short password"""
    with pytest.raises(ValidationError):
        UserCreateIn(
            email="test@example.com",
            name="Test User",
            password="12345",  # Less than 6 characters
            role="student"
        )

def test_user_create_in_long_password():
    """Test user creation with very long password"""
    with pytest.raises(ValidationError):
        UserCreateIn(
            email="test@example.com",
            name="Test User",
            password="a" * 73,  # More than 72 characters
            role="student"
        )

def test_user_create_in_invalid_role():
    """Test user creation with invalid role"""
    with pytest.raises(ValidationError):
        UserCreateIn(
            email="test@example.com",
            name="Test User",
            password="Test123",
            role="invalid_role"
        )

def test_project_config_create_in_valid():
    """Test valid project config creation schema"""
    config = ProjectConfigCreateIn(
        project_id="123456",
        num_devs=5,
        team_velocity=30,
        sprint_duration=2,
        prioritization_metric="businessValue",
        release_target_date=date(2025, 12, 31)
    )
    assert config.project_id == "123456"
    assert config.num_devs == 5
    assert config.team_velocity == 30
    assert config.sprint_duration == 2

def test_dashboard_stats_out():
    """Test dashboard stats response schema"""
    stats = DashboardStatsOut(
        total_projects=10,
        projects_growth=2,
        total_active_stories=50,
        pending_refinement=15,
        planned_releases=3,
        next_release_date=date(2025, 12, 31),
        ai_analysis_count=5,
        ai_analysis_period="7d"
    )
    assert stats.total_projects == 10
    assert stats.projects_growth == 2
    assert stats.total_active_stories == 50

def test_project_stats_out():
    """Test project stats response schema"""
    stats = ProjectStatsOut(
        total_stories=100,
        in_development=20,
        completed=50,
        pending=30,
        releases_count=2,
        total_story_points=500,
        completed_story_points=250,
        progress_percentage=50.0
    )
    assert stats.total_stories == 100
    assert stats.progress_percentage == 50.0
    assert stats.releases_count == 2

def test_release_planning_out():
    """Test release planning response schema"""
    planning = ReleasePlanningOut(
        project_id="123",
        num_releases=2,
        releases=[
            {
                "release_number": 1,
                "release_title": "MVP Release",
                "release_description": "Core features",
                "sprints": []
            },
            {
                "release_number": 2,
                "release_title": "Enhancement Release",
                "release_description": "Additional features",
                "sprints": []
            }
        ],
        project_analysis={
            "total_story_points": 500,
            "team_capacity": 30
        },
        overall_risks=[
            {"risk": "Timeline risk", "severity": "high"}
        ],
        overall_recommendations=["Increase team velocity"]
    )
    assert planning.num_releases == 2
    assert len(planning.releases) == 2
    assert planning.releases[0]["release_title"] == "MVP Release"
