from fastapi import FastAPI

app = FastAPI(title="learningProject API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
