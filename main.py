from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.api import router as api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create tables
    from database import Base, engine, SessionLocal

    Base.metadata.create_all(bind=engine)
    # Seed universal metrics and sync built-in metadata by name so existing dev DBs
    # pick up product-defined universal criteria changes on restart.
    from services.ontology import UNIVERSAL_DIMENSIONS
    from models import Metric

    db = SessionLocal()
    try:
        existing_by_name = {m.name: m for m in db.query(Metric).all()}
        for dim in UNIVERSAL_DIMENSIONS:
            for m in dim["metrics"]:
                metric = existing_by_name.get(m["name"])
                if metric:
                    metric.category = dim["name"]
                    metric.description = m["description"]
                    metric.higher_is_better = m["higher_is_better"]
                else:
                    metric = Metric(
                        name=m["name"],
                        category=dim["name"],
                        description=m["description"],
                        higher_is_better=m["higher_is_better"],
                    )
                    db.add(metric)
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="Optium", lifespan=lifespan)

cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
    if origin.strip() and origin.strip() != "*"
]

# CORS — allow explicit origins only; Docker production is same-origin via nginx
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=bool(cors_origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
