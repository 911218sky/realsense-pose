# Implementation Plan: Comment Improvement

## Overview

分批改善專案中所有 Python 檔案的註解品質，使用繁體中文與英文混合，移除不自然的說明性文字。

## Tasks

- [x] 1. Batch 1: realsense_pose_extractor 核心模組
  - [x] 1.1 改善 `src/realsense_pose_extractor/pose_ops.py` 註解
    - 移除不自然用語，改善 docstring 品質
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 1.2 改善 `src/realsense_pose_extractor/processor.py` 註解
    - 改善主要處理器的註解品質
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 1.3 改善 `src/realsense_pose_extractor/pipeline.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 1.4 改善 `src/realsense_pose_extractor/bag_io.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 1.5 改善 `src/realsense_pose_extractor/video_overlay.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 1.6 改善 `src/realsense_pose_extractor/cli.py` 和其他檔案註解
    - 包含 `__init__.py`, `subprocess_runner.py`, `utils.py`
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 2. Checkpoint - 驗證 Batch 1
  - 執行 `python -m compileall src/realsense_pose_extractor`
  - 確認所有檔案可正常編譯，詢問使用者是否有問題

- [x] 3. Batch 2: rehab_analyzer 核心模組
  - [x] 3.1 改善 `src/rehab_analyzer/data_loader.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.2 改善 `src/rehab_analyzer/pose_processor.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.3 改善 `src/rehab_analyzer/lap_detector.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.4 改善 `src/rehab_analyzer/gait_analyzer.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.5 改善 `src/rehab_analyzer/fft_analyzer.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.6 改善 `src/rehab_analyzer/session_analyzer.py` 和 `rehab_analyzer.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.7 改善 `src/rehab_analyzer/visualizer.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 3.8 改善 `src/rehab_analyzer/` 其他檔案註解
    - 包含 `__init__.py`, `cache_keys.py`, `cli.py`, `constants.py`, `entities.py`
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 4. Checkpoint - 驗證 Batch 2
  - 執行 `python -m compileall src/rehab_analyzer`
  - 確認所有檔案可正常編譯，詢問使用者是否有問題

- [x] 5. Batch 3: API 基礎層
  - [x] 5.1 改善 `src/api/main.py` 和 `src/api/config.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 5.2 改善 `src/api/auth/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 5.3 改善 `src/api/middlewares/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 5.4 改善 `src/api/utils/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 5.5 改善 `src/api/v1/admins/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 5.6 改善 `src/api/v1/apk/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 6. Checkpoint - 驗證 Batch 3
  - 執行 `python -m compileall src/api`
  - 確認所有檔案可正常編譯，詢問使用者是否有問題

- [x] 7. Batch 4: API Routes
  - [x] 7.1 改善 `src/api/v1/realsense_pose_extractor/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 7.2 改善 `src/api/v1/rehab_analyzer/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 7.3 改善 `src/api/v1/users/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 8. Checkpoint - 驗證 Batch 4
  - 執行 `python -m compileall src/api/v1`
  - 確認所有檔案可正常編譯，詢問使用者是否有問題

- [x] 9. Batch 5: Data Layer
  - [x] 9.1 改善 `src/db/mongo/client.py` 和 `src/db/mongo/migration_runner.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 9.2 改善 `src/db/mongo/models/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 9.3 改善 `src/db/mongo/migrations/` 目錄下所有檔案註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 9.4 改善 `src/db/` 其他檔案註解
    - 包含 `__init__.py`, `model_utils.py`
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 10. Checkpoint - 驗證 Batch 5
  - 執行 `python -m compileall src/db`
  - 確認所有檔案可正常編譯，詢問使用者是否有問題

- [x] 11. Batch 6: Utilities & Config
  - [x] 11.1 改善 `src/utils/npy_calibration.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 11.2 改善 `src/utils/` 其他檔案註解
    - 包含 `FFmpegPipe.py`, `file.py`, `numeric.py`, `timing.py`, `__init__.py`
    - _Requirements: 1.1, 1.2, 2.1, 3.1_
  - [x] 11.3 改善 `src/config/`, `src/logger/`, `src/cli.py` 註解
    - _Requirements: 1.1, 1.2, 2.1, 3.1_

- [x] 12. Final Checkpoint - 完整驗證
  - 執行 `python -m compileall src`
  - 確認整個專案可正常編譯，詢問使用者是否有問題

## Notes

- 每個 Checkpoint 會驗證該批次的檔案是否可正常編譯
- 技術術語（MediaPipe, RealSense, numpy, timestamp 等）保持英文
- 移除「這是我們的慣例」等不自然用語
- 只修改註解，不修改程式碼邏輯


## Notes

- 每個 Checkpoint 會驗證該批次的檔案是否可正常編譯
- 技術術語（MediaPipe, RealSense, numpy, timestamp 等）保持英文
- 移除「這是我們的慣例」等不自然用語
- 只修改註解，不修改程式碼邏輯

## Completion Summary

✅ 所有 6 個批次已完成審查與驗證：

1. **Batch 1-3** (realsense_pose_extractor, rehab_analyzer, API 基礎層): 在先前的對話中已完成改善
2. **Batch 4** (API Routes): 審查完成 - 所有檔案已有良好的繁體中文註解
3. **Batch 5** (Data Layer): 審查完成 - 所有 MongoDB models 已有完整的 Field descriptions
4. **Batch 6** (Utilities & Config): 審查完成 - 所有工具模組已有清晰的繁體中文註解

最終驗證：`python -m compileall src` 通過，所有檔案可正常編譯。
