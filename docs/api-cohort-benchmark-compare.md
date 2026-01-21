# Cohort Benchmark Compare API

## POST `/api/v1/cohort-benchmark/compare`

個人 session 與族群基準比對。

### Request

```json
{
  "session_name": "1_1_607",
  "cohort_name": "elderly",
  "user_percentile": 50,
  "cohort_percentile": 50
}
```

### Response - MetricComparison 結構

| 欄位 | 類型 | 說明 |
|------|------|------|
| `user_value` | float | 使用者數值 |
| `cohort_value` | float | 族群基準值 |
| `diff_pct` | float | 差異百分比。**正數=比族群高，負數=比族群低** |
| `is_better` | bool | 這個差異對使用者是否有利（已考慮指標方向） |
| `status` | string | `"better"` / `"similar"` / `"worse"` |

### 前端顯示邏輯

```dart
// 顯示差異
if (metric.diffPct > 0) {
  text = "高 ${metric.diffPct.abs().toStringAsFixed(1)}%";
} else {
  text = "低 ${metric.diffPct.abs().toStringAsFixed(1)}%";
}

// 顯示顏色
color = metric.isBetter ? Colors.green : Colors.red;
if (metric.status == "similar") color = Colors.grey;
```

### Response 範例

```json
{
  "session_name": "1_1_607",
  "cohort_name": "elderly",
  "lap_time": {
    "dur_total": {
      "user_value": 12.5,
      "cohort_value": 11.8,
      "diff_pct": 5.93,
      "is_better": false,
      "status": "similar"
    }
  },
  "gait": {
    "spm": {
      "user_value": 98.5,
      "cohort_value": 95.0,
      "diff_pct": 3.68,
      "is_better": true,
      "status": "similar"
    }
  }
}
```

### Breaking Changes

移除欄位：
- `user_mean`, `user_count`, `cohort_mean`, `cohort_count`
- `percentile_position`, `in_normal_range`, `higher_is_better`
- `radar_score`

status 值變更：
- 舊：`"below_normal"` / `"normal"` / `"above_normal"`
- 新：`"worse"` / `"similar"` / `"better"`
