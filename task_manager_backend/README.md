# Task Manager Backend

This is the FastAPI backend for the Task Organizer application. It provides user authentication (JWT), robust task CRUD operations, supports filtering and search, and connects to a database.

## Key Features

- User registration and JWT authentication
- REST API endpoints for creating, editing, viewing, deleting tasks
- Filter tasks by status, priority, due date, completion
- Mark tasks as complete/incomplete
- All config (secrets, DB URLs) from environment variables

## Environment Variables

**Create a `.env` file in the root of this container with:**

```
DATABASE_URL=postgresql://user:password@host:port/dbname
JWT_SECRET_KEY=some-long-secret-key
```

## Running

1. Install requirements: 
   ```
   pip install -r requirements.txt
   ```
2. Run the app:
   ```
   uvicorn src.api.main:app --reload
   ```

## API Docs

Open [http://localhost:8000/docs](http://localhost:8000/docs) after running.
