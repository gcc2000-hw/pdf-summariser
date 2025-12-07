from fastapi import FastAPI
import uvicorn

app = FastAPI(
    title="PDF Summarizer Pro API",
    description="Advanced PDF summarization with entity extraction and multi-model support",
    version="1.0.0"
)
@app.get("/")
async def read_root():
    return {"Hello": "World"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)