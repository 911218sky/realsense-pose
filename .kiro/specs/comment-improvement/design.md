# Design Document: Comment Improvement

## Overview

本設計文件描述如何系統性地改善 RealSense Pose 專案中所有 Python 原始碼的註解品質。由於註解品質是主觀的，本任務主要依賴人工審查，但會建立明確的分批策略和風格指南來確保一致性。

## Architecture

### 處理流程

```
┌─────────────────┐
│  識別目標檔案   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  分批規劃       │
│  (按模組分組)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  逐批處理       │
│  - 讀取檔案     │
│  - 改善註解     │
│  - 驗證語法     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  人工審查       │
└─────────────────┘
```

### 檔案分批策略

根據專案結構，將 Python 檔案分為 6 個批次：

**Batch 1: Core - realsense_pose_extractor (8 files)**
- `src/realsense_pose_extractor/__init__.py`
- `src/realsense_pose_extractor/bag_io.py`
- `src/realsense_pose_extractor/cli.py`
- `src/realsense_pose_extractor/pipeline.py`
- `src/realsense_pose_extractor/pose_ops.py`
- `src/realsense_pose_extractor/processor.py`
- `src/realsense_pose_extractor/subprocess_runner.py`
- `src/realsense_pose_extractor/video_overlay.py`

**Batch 2: Core - rehab_analyzer (13 files)**
- `src/rehab_analyzer/__init__.py`
- `src/rehab_analyzer/cache_keys.py`
- `src/rehab_analyzer/cli.py`
- `src/rehab_analyzer/constants.py`
- `src/rehab_analyzer/data_loader.py`
- `src/rehab_analyzer/entities.py`
- `src/rehab_analyzer/fft_analyzer.py`
- `src/rehab_analyzer/gait_analyzer.py`
- `src/rehab_analyzer/lap_detector.py`
- `src/rehab_analyzer/pose_processor.py`
- `src/rehab_analyzer/rehab_analyzer.py`
- `src/rehab_analyzer/session_analyzer.py`
- `src/rehab_analyzer/visualizer.py`

**Batch 3: API Layer (18 files)**
- `src/api/main.py`
- `src/api/config.py`
- `src/api/auth_headers.py`
- `src/api/auth/__init__.py`
- `src/api/auth/signed_headers.py`
- `src/api/middlewares/__init__.py`
- `src/api/middlewares/payload_decode.py`
- `src/api/utils/array_codec.py`
- `src/api/utils/bag_path_resolver.py`
- `src/api/utils/cache.py`
- `src/api/utils/env.py`
- `src/api/utils/precompressed_staticfiles.py`
- `src/api/v1/__init__.py`
- `src/api/v1/admins/*.py` (5 files)
- `src/api/v1/apk/*.py` (2 files)

**Batch 4: API Routes (8 files)**
- `src/api/v1/realsense_pose_extractor/bags.py`
- `src/api/v1/realsense_pose_extractor/extract_utils.py`
- `src/api/v1/realsense_pose_extractor/models.py`
- `src/api/v1/realsense_pose_extractor/realsense_pose_extractor.py`
- `src/api/v1/realsense_pose_extractor/utils.py`
- `src/api/v1/rehab_analyzer/models.py`
- `src/api/v1/rehab_analyzer/rehab_analyzer.py`
- `src/api/v1/rehab_analyzer/utils.py`
- `src/api/v1/users/models.py`
- `src/api/v1/users/users.py`

**Batch 5: Data Layer (12 files)**
- `src/db/__init__.py`
- `src/db/mongo/__init__.py`
- `src/db/mongo/client.py`
- `src/db/mongo/migration_runner.py`
- `src/db/mongo/model_utils.py`
- `src/db/mongo/migrations/*.py` (4 files)
- `src/db/mongo/models/*.py` (6 files)

**Batch 6: Utilities & Config (9 files)**
- `src/cli.py`
- `src/config/__init__.py`
- `src/logger/__init__.py`
- `src/utils/__init__.py`
- `src/utils/FFmpegPipe.py`
- `src/utils/file.py`
- `src/utils/npy_calibration.py`
- `src/utils/numeric.py`
- `src/utils/timing.py`

## Components and Interfaces

### 註解風格指南

#### 語言使用規則

1. **繁體中文為主**：一般描述使用繁體中文
2. **英文技術術語**：保留以下術語為英文
   - 函式庫名稱：MediaPipe, RealSense, numpy, scipy, OpenCV
   - 資料結構：array, frame, pipeline, buffer, cache
   - 技術概念：timestamp, intrinsics, depth, RGB, BGR
   - 演算法：FFT, SVD, MAD, median, percentile

#### 需移除的不自然用語

| 不自然用語 | 改善方式 |
|-----------|---------|
| 「（這是我們的慣例）」 | 直接刪除或融入句子 |
| 「注意：這裡...」 | 改為直述句 |
| 「用於...」開頭 | 改為動詞開頭 |
| 「用來...」開頭 | 改為動詞開頭 |
| 「會...」過度使用 | 改用其他動詞 |
| 「（避免...）」括號說明 | 融入主句 |

#### Docstring 格式

```python
def function_name(param1: Type1, param2: Type2) -> ReturnType:
    """
    簡潔描述函式功能（一行）
    
    Args:
        param1: 參數說明
        param2: 參數說明
        
    Returns:
        回傳值說明
    """
```

#### Inline Comment 原則

- 解釋「為什麼」而非「做什麼」
- 保持簡潔（建議 60 字元內）
- 避免重複程式碼已表達的內容

## Data Models

本任務不涉及資料模型變更，僅修改註解文字。

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

由於註解改善主要是主觀的文字品質任務，大部分需求無法自動化測試。以下是可驗證的屬性：

### Property 1: Code Preservation
*For any* Python file processed, the executable code (excluding comments and docstrings) SHALL remain identical before and after processing.
**Validates: Requirements 6.1, 6.2**

### Property 2: Syntax Validity
*For any* Python file processed, the file SHALL remain syntactically valid Python code after comment modifications.
**Validates: Requirements 6.1**

### Property 3: Technical Term Preservation
*For any* comment containing technical terms (MediaPipe, RealSense, numpy, timestamp, frame, pipeline, intrinsics, depth), those terms SHALL remain in English after processing.
**Validates: Requirements 2.2, 2.4**

## Error Handling

- 若檔案無法解析，跳過該檔案並記錄錯誤
- 若修改後語法錯誤，回滾該檔案的變更
- 每批次完成後執行 `python -m compileall` 驗證

## Testing Strategy

### 驗證方式

1. **語法驗證**：每批次完成後執行 `python -m compileall src`
2. **人工審查**：每批次完成後由使用者審查變更
3. **功能測試**：確保 API 和 CLI 仍可正常運作

### 驗證檢查清單

- [ ] 所有檔案可正常編譯
- [ ] 不自然用語已移除
- [ ] 技術術語保持英文
- [ ] 註解語意未改變
- [ ] 程式碼功能未受影響
