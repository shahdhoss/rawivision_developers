import uvicorn

if __name__ == "__main__":
    print("🚀 Starting Developer Billing Server on port 8001...")
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
