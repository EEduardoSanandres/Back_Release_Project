from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from ..services.auth_service import AuthService, auth_service
from ..schemas.requests import UserCreateIn
from ...app.schemas import User

router = APIRouter(
    prefix="/auth",
    tags=["Auth"]
)

class UserResponse(BaseModel):
    id: str = Field(..., description="ID del usuario")
    email: str = Field(..., description="Email del usuario")
    name: str = Field(..., description="Nombre del usuario")
    role: str = Field(..., description="Rol del usuario")
    created_at: str = Field(..., description="Fecha de creación en formato ISO")
    
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
    email: str = Field(..., description="Email del usuario", example="user@example.com")
    password: str = Field(..., description="Contraseña del usuario", example="Password123")

class LoginResponse(BaseModel):
    message: str = Field(..., description="Mensaje de éxito", example="Login exitoso")
    user: UserResponse = Field(..., description="Datos del usuario autenticado")

@router.post(
    "/register", 
    response_model=UserResponse, 
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo usuario",
    description="Crea una nueva cuenta de usuario en el sistema. Valida que el email no esté en uso y hashea la contraseña.",
    responses={
        400: {"description": "Datos de registro inválidos o email ya registrado"},
        500: {"description": "Error interno del servidor al crear el usuario"}
    }
)
async def register_user(
    user_data: UserCreateIn,
    auth_svc: AuthService = Depends(auth_service)
):
    import logging
    logging.info(f"Registering user: {user_data.email} | Password length: {len(user_data.password)}")
    
    try:
        user = await auth_svc.create_user(user_data)
        return UserResponse.from_user(user)
    except HTTPException:
        raise
    except ValueError as e:
        # Errores de validación de bcrypt
        error_msg = str(e)
        logging.error(f"ValueError: {error_msg}")
        if "72 bytes" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Password issue: length={len(user_data.password)}, bytes={len(user_data.password.encode('utf-8'))}, error={error_msg}"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Error de validación: {error_msg}"
        )
    except Exception as e:
        logging.error(f"Error creando usuario: {type(e).__name__}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error: {type(e).__name__}: {str(e)}"
        )

@router.post(
    "/login", 
    response_model=LoginResponse,
    summary="Iniciar sesión",
    description="Autentica a un usuario mediante email y contraseña. Retorna los datos del usuario si las credenciales son válidas.",
    responses={
        401: {"description": "Credenciales inválidas (email o contraseña incorrectos)"}
    }
)
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
