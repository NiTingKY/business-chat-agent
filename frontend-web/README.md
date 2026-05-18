# Travel Agent Chat Web

Static local chat UI for the FastAPI travel agent backend.

## Run Locally

Start the backend first:

```powershell
cd D:\java\travel-agent-guide-main\project-python\backend-python
D:\miniconda\envs\stbp\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then start this frontend:

```powershell
cd D:\java\travel-agent-guide-main\project-python\frontend-web
D:\miniconda\envs\stbp\python.exe -m http.server 5173
```

Open:

```text
http://127.0.0.1:5173/
```

The UI calls:

```text
http://127.0.0.1:8000/api/v1/chat
```

## Test

```powershell
cd D:\java\travel-agent-guide-main\project-python\frontend-web
npm.cmd test
```
