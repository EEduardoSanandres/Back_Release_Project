from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..services.auth_service import AuthService, auth_service
from ..schemas.requests import UserCreateIn
from ...app.schemas import User

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"]
)

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    role: str
    created_at: str
    
    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        return cls(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
            created_at=user.created_at.isoformat()
        )

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    message: str
    user: UserResponse

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_data: UserCreateIn,
    auth_svc: AuthService = Depends(auth_service)
):
    try:
        user = await auth_svc.create_user(user_data)
        return UserResponse.from_user(user)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creando usuario: {str(e)}"
        )

@router.post("/login", response_model=LoginResponse)
async def login_user(
    login_data: LoginRequest,
    auth_svc: AuthService = Depends(auth_service)
):
    user = await auth_svc.authenticate_user(login_data.email, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email o contraseña incorrectos"
        )
    
    return LoginResponse(
        message="Login exitoso",
        user=UserResponse.from_user(user)
    )

__all__ = ["router"]
