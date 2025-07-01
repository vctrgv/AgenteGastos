# run_async.py
import asyncio
import uvicorn

async def main():
    config = uvicorn.Config("app:app", host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
