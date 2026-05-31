import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router
from .db import init_db


def create_app() -> FastAPI:
  init_db()
  app = FastAPI(title="FocusQuest API", version="0.1.0")
  app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
  )
  app.include_router(router)
  return app


app = create_app()

if __name__ == "__main__":
  import uvicorn
  port = int(os.getenv("PORT", 8000))
  uvicorn.run(app, host="0.0.0.0", port=port)
