from fastapi import FastAPI

from app.routers import appointments, practitioners

app = FastAPI(title="Docket — Healthcare Scheduler")

app.include_router(practitioners.router)
app.include_router(appointments.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
