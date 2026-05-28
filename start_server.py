import uvicorn
from novel_system.api import app

if __name__ == "__main__":
    print("Starting server on http://0.0.0.0:3000")
    uvicorn.run(app, host="0.0.0.0", port=3000)
