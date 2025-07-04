from passlib.context import CryptContext
from datetime import datetime
from fastapi import HTTPException
from bson import ObjectId

from ...app.db import db
from ...app.schemas import User
from ..schemas.requests import UserCreateIn

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    
    @staticmethod
    def hash_password(password: str) -> str:
        return pwd_context.hash(password)
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)
    
    async def create_user(self, user_data: UserCreateIn) -> User:
        
        existing_user = await db.users.find_one({"email": user_data.email})
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El email ya está registrado"
            )
        
        user_doc = {
            "email": user_data.email,
            "name": user_data.name,
            "password_hash": self.hash_password(user_data.password),
            "role": user_data.role,
            "created_at": datetime.utcnow()
        }
        
        result = await db.users.insert_one(user_doc)
        
        created_user = await db.users.find_one({"_id": result.inserted_id})
        return User(**created_user)
    
    async def authenticate_user(self, email: str, password: str) -> User | None:
        user_doc = await db.users.find_one({"email": email})
        
        if not user_doc:
            return None
            
        if not self.verify_password(password, user_doc["password_hash"]):
            return None
            
        return User(**user_doc)

def auth_service() -> AuthService:
    return AuthService()
