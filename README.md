# 港 Harbor —— 桌面 + Web 双形态 AI 内容发布中枢

桌面程序启动入口。

## 形态对照

| | Web 形态 | 桌面形态 |
|---|---|---|
| 前端 | Vue 3 + Vite 浏览器 | Vue 3 + Tauri 系统 WebView |
| 后端 | FastAPI + uvicorn 手动启 | 由 Tauri 内嵌启动，对外不可见 |
| 访问 | http://localhost:8000 | 单 exe 双击即用 |

桌面形态基于 Tauri 2.0，复用 100% 前端代码与后端代码——不写两套业务逻辑。

## 启动桌面程序

```bash
cd web
npm install
npm run tauri dev
```

桌面启动时，Tauri 自动以 sidecar 模式启动 `backed/` Python 后端，前端自动连
接本地后端，不需要用户手动开命令行窗口。

## 桌面端构建

```bash
cd web
npm run tauri build
```

产物：`web/target/release/content-harbor.exe`（单文件双击即用）。

## Web 开发

```bash
cd web
npm run dev
# 另开一窗
cd backed
uv run python start.py
```

浏览器打开 http://localhost:5173。

## 架构一览

```
桌面版                            Web 版
┌──────────────┐                ┌──────────────┐
│  Tauri 壳    │                │  浏览器       │
│  ┌─────────┐ │                │  ┌─────────┐ │
│  │ Vue 3   │ │                │  │ Vue 3   │ │
│  │ (WebView)│ │                │  │ (DOM)   │ │
│  └────┬────┘ │                │  └────┬────┘ │
│       │HTTP  │                │       │HTTP  │
│  ┌────▼────┐ │                │  ┌────▼────┐ │
│  │ FastAPI │ │                │  │ FastAPI │ │
│  │ (sidecar)│ │                │  │ (uvicorn)│ │
│  └─────────┘ │                │  └─────────┘ │
└──────────────┘                └──────────────┘
```

## 文档

- [架构详解](docs/architecture/ARCHITECTURE.md)
- [审计报告](docs/audit/AUDIT.md)
