# X-Amplicon Web UI Frontend

This directory contains the React + Vite + TypeScript frontend for the local X-Amplicon Web UI.

Development commands:

```powershell
npm.cmd install
npm.cmd run dev
npm.cmd run typecheck
npm.cmd run build
```

During development, Vite runs on `http://127.0.0.1:5173` and calls the FastAPI backend at `http://127.0.0.1:8765/api` unless `VITE_API_BASE_URL` is set.
