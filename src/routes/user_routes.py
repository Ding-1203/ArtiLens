from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from typing import List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.db import get_db_session
from models.user import User

from schemas.user_schemas import *

router = APIRouter(prefix="/users", tags=["users"])



# ===================== 路由函数 =====================

# 获取所有用户
@router.get("/", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db_session)):
    users = db.query(User).all()
    return [UserResponse.model_validate(user) for user in users]


# 创建用户
@router.post("/", response_model=UserResponse, status_code=201)
def create_user(user_data: UserCreate, db: Session = Depends(get_db_session)):
    user = User(username=user_data.username, email=user_data.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


# 获取指定用户
@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db_session)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse.model_validate(user)


# 更新用户信息
@router.put("/{user_id}", response_model=UserResponse)
def update_user(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db_session)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if user_data.username:
        user.username = user_data.username
    if user_data.email:
        user.email = user_data.email

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


# 删除用户
@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db_session)):
    user = db.query(User).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    db.delete(user)
    db.commit()
    return None


# 登录界面
@router.post("/login", response_model=UserResponse)
def login_user(user_data: UserCreate, db: Session = Depends(get_db_session)):
    user = db.query(User).filter(and_(User.email == user_data.email, User.username == user_data.username)).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return UserResponse.model_validate(user)


# 注册接口
@router.post("/register", response_model=UserResponse)
def register_user(user_data: UserCreate, db: Session = Depends(get_db_session)):
    # 检查 email 是否存在
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    # 创建新用户
    user = User(username=user_data.username, email=user_data.email)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)



