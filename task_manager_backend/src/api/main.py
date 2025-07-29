import os
from typing import List, Optional
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, status, Depends, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Enum, create_engine
from sqlalchemy.orm import sessionmaker, relationship, Session, declarative_base
from jose import JWTError, jwt
from passlib.context import CryptContext
from dotenv import load_dotenv
from pydantic import BaseModel, Field

import enum

# --- Load environment variables ---
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_ALGORITHM = "HS256"

if not (DATABASE_URL and JWT_SECRET_KEY):
    raise RuntimeError("Environment variables DATABASE_URL and JWT_SECRET_KEY must be set.")

# --- Database Setup ---
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Models ---
class TaskStatus(str, enum.Enum):
    todo = "todo"
    in_progress = "in_progress"
    completed = "completed"

class TaskPriority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    tasks = relationship("Task", back_populates="owner")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)
    status = Column(Enum(TaskStatus), default=TaskStatus.todo)
    priority = Column(Enum(TaskPriority), default=TaskPriority.medium)
    due_date = Column(DateTime, nullable=True)
    completed = Column(Boolean, default=False)
    owner_id = Column(Integer, ForeignKey("users.id"))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner = relationship("User", back_populates="tasks")

# --- Pydantic Schemas ---
class UserCreate(BaseModel):
    username: str = Field(..., description="Unique username for the user.")
    password: str = Field(..., description="Password for the user.")

class UserResponse(BaseModel):
    id: int
    username: str
    created_at: datetime

    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TaskBase(BaseModel):
    title: str = Field(..., description="Title of the task")
    description: Optional[str] = Field(None, description="Details about the task")
    status: Optional[TaskStatus] = Field(TaskStatus.todo, description="Current status")
    priority: Optional[TaskPriority] = Field(TaskPriority.medium, description="Task priority")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")
    completed: bool = Field(False, description="Completion status")

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    status: Optional[TaskStatus]
    priority: Optional[TaskPriority]
    due_date: Optional[datetime]
    completed: Optional[bool]

class TaskInDB(TaskBase):
    id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


# --- Auth Setup ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def create_db_and_tables():
    Base.metadata.create_all(bind=engine)

# Helper Functions
def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=12)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_user(db: Session, username: str):
    return db.query(User).filter(User.username == username).first()

def get_user_by_id(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def authenticate_user(db: Session, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    cred_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise cred_exception
    except JWTError:
        raise cred_exception
    user = get_user(db, username=username)
    if user is None:
        raise cred_exception
    return user

# --- FastAPI App ---
app = FastAPI(
    title="Task Organizer API",
    description="API backend for managing tasks and user authentication.",
    version="1.0.0",
    openapi_tags=[
        {"name": "users", "description": "Operations related to user authentication & registration"},
        {"name": "tasks", "description": "Task CRUD and management endpoints"}
    ]
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- ROUTES ---

# PUBLIC_INTERFACE
@app.on_event("startup")
def on_startup():
    """Initialize DB tables at app startup."""
    create_db_and_tables()

# PUBLIC_INTERFACE
@app.get("/", tags=["users"])
def health_check():
    """
    Health Check Endpoint

    Returns:
        dict: {"message": "Healthy"}
    """
    return {"message": "Healthy"}

# User Authentication and Registration
# PUBLIC_INTERFACE
@app.post("/auth/signup", response_model=UserResponse, status_code=201, tags=["users"], summary="User registration")
def signup(user: UserCreate, db: Session = Depends(get_db)):
    """
    Sign up a new user.

    Args:
        user (UserCreate): User credentials.

    Returns:
        UserResponse: Details of the newly created user.
    """
    db_user = get_user(db, user.username)
    if db_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    hashed_pw = get_password_hash(user.password)
    new_user = User(username=user.username, hashed_password=hashed_pw)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# PUBLIC_INTERFACE
@app.post("/auth/token", response_model=Token, tags=["users"], summary="User login & access token")
def login_for_access_token(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):
    """
    User login endpoint. Returns access token.

    Args:
        form_data (OAuth2PasswordRequestForm): Form input.
    Returns:
        Token: JWT access token.
    """
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect username or password"
        )
    access_token = create_access_token(data={"sub": user.username})
    return {"access_token": access_token, "token_type": "bearer"}

# Task Management Endpoints
# PUBLIC_INTERFACE
@app.post("/tasks/", response_model=TaskInDB, status_code=201, tags=["tasks"], summary="Create a new task")
def create_task(task: TaskCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Create a new task for the authenticated user.
    """
    new_task = Task(
        **task.dict(),
        owner_id=user.id
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    return new_task

# PUBLIC_INTERFACE
@app.get("/tasks/", response_model=List[TaskInDB], tags=["tasks"], summary="List tasks with filters")
def list_tasks(
    status: Optional[TaskStatus] = None,
    priority: Optional[TaskPriority] = None,
    completed: Optional[bool] = None,
    due_before: Optional[datetime] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Get all tasks for the authenticated user, with optional filters.
    """
    query = db.query(Task).filter(Task.owner_id == user.id)
    if status:
        query = query.filter(Task.status == status)
    if priority:
        query = query.filter(Task.priority == priority)
    if completed is not None:
        query = query.filter(Task.completed == completed)
    if due_before:
        query = query.filter(Task.due_date <= due_before)
    return query.order_by(Task.due_date, Task.created_at).all()

# PUBLIC_INTERFACE
@app.get("/tasks/{task_id}", response_model=TaskInDB, tags=["tasks"], summary="Get single task by ID")
def get_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Get a task by its ID (authenticated user only).
    """
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task

# PUBLIC_INTERFACE
@app.put("/tasks/{task_id}", response_model=TaskInDB, tags=["tasks"], summary="Edit a task")
def update_task(task_id: int, task_update: TaskUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Update an existing task for the authenticated user.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    for key, value in task_update.dict(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task

# PUBLIC_INTERFACE
@app.delete("/tasks/{task_id}", status_code=204, tags=["tasks"], summary="Delete a task")
def delete_task(task_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """
    Delete a task by ID.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    db.delete(task)
    db.commit()
    return

# PUBLIC_INTERFACE
@app.patch("/tasks/{task_id}/complete", response_model=TaskInDB, tags=["tasks"], summary="Mark task complete/incomplete")
def mark_task_complete(
    task_id: int,
    completed: bool = Body(..., embed=True, description="Set True for complete, False for incomplete"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
):
    """
    Mark a task as complete or incomplete (toggle).
    """
    task = db.query(Task).filter(Task.id == task_id, Task.owner_id == user.id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.completed = completed
    db.commit()
    db.refresh(task)
    return task
