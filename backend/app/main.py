from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import health as health_router

app = FastAPI(title="learningProject API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router.router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
