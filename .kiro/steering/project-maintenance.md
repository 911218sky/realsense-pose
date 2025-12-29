---
alwaysApply: true
---

# 專案維護規範

適用範圍：`src/` 目錄下所有 Python 程式碼

## 專案概述

RealSense Pose — 使用 Intel RealSense 相機與 MediaPipe 的姿態估計與復健分析系統。

技術棧：FastAPI + MongoDB + Redis + Flutter Web UI

## 架構分層

```
src/
├── api/                    # 應用層：FastAPI 路由與中介層
│   ├── v1/                 # API 版本化路由
│   │   ├── rehab_analyzer/ # 復健分析 API endpoints
│   │   ├── realsense_pose_extractor/  # 姿態擷取 API
│   │   ├── users/          # 使用者管理
│   │   └── admins/         # 管理員認證
│   ├── auth/               # 認證模組（signed headers）
│   ├── middlewares/        # 中介層（payload decode）
│   └── utils/              # API 工具（cache, codec, env）
├── rehab_analyzer/         # 分析核心：步態/圈數/FFT 分析
│   ├── session_analyzer.py # Facade：RehabilitationSessionAnalyzer
│   ├── lap_detector.py     # 圈數偵測
│   ├── gait_analyzer.py    # 步態分析
│   ├── fft_analyzer.py     # 頻譜分析
│   ├── pose_processor.py   # 姿態前處理
│   ├── data_loader.py      # 資料載入
│   ├── entities.py         # 資料結構（dataclass）
│   └── visualizer.py       # 視覺化（lazy import）
├── realsense_pose_extractor/  # 姿態擷取核心
│   ├── processor.py        # Facade：PoseProcessor
│   ├── pipeline.py         # RealSense pipeline
│   ├── bag_io.py           # .bag 檔案 I/O
│   ├── pose_ops.py         # 姿態運算
│   └── video_overlay.py    # 影片疊加
├── db/                     # 資料層：MongoDB models
│   └── mongo/models/       # Beanie document models
├── config/                 # 設定載入（YAML）
├── logger/                 # 日誌設定
├── utils/                  # 共用工具
└── cli.py                  # CLI 入口
```

依賴方向：只能往下層流動，禁止循環依賴

```
API 路由 (api/v1/*)
    ↓
Facade (session_analyzer / processor)
    ↓
分析核心 (lap_detector / gait_analyzer / fft_analyzer)
    ↓
前處理 (pose_processor / data_loader)
    ↓
資料層 (db / config / utils)
```

## 核心原則

1. **可維護性優先** — 清楚的模組邊界、易定位、易測試、易替換
2. **對外相容** — 重構時維持既有 import 路徑與 API，避免破壞 API/CLI/Visualizer
3. **可讀性** — 複雜度分散到多個小檔案，避免長函式/長檔案

## 拆檔規則

| 規則 | 說明 |
|------|------|
| 單一職責 | 一檔一主題，如 `lap_detector.py` 只放圈數偵測 |
| 檔案上限 | 超過 400-600 行應拆成 2-4 個模組 |
| Facade 模式 | 保留舊入口做 re-export（如 `rehab_analyzer.py`），維持 `from xxx import Y` 不變 |
| 工具模組 | 通用工具放 `utils/` 或精確命名如 `cache_keys.py`，不堆同一檔 |

## 命名慣例

- 模組：`snake_case.py`
- 對外 API：在 `__init__.py` 用 `__all__` 管理 re-export
- 內部模組：用 `_xxx.py` 表示私有（已被外部引用的不改）
- Lazy import：重依賴（matplotlib/cv2）用 `__getattr__` 延遲載入

## 型別要求

- 對外資料結構用 `dataclass`（如 `entities.py`）或 Pydantic models（如 `api/v1/*/models.py`）
- 新增/修改的函式必須加 type hints
- 避免使用 `Any`

## 快取策略

- API 層用 `@redis_cache(expire=30)` 裝飾器
- 分析核心用 `cachetools.cachedmethod` + `TTLCache`
- cache key 統一用 `rehab_analyzer.cache_keys.method_key`
- 注意：`ndarray`/`list` 不可 hash，需轉換

## 修改後檢查

每次修改 `src/` 後執行：

```bash
python -m compileall src
```

若改動 API schema 或 CLI 行為，需做 smoke test 驗證。
