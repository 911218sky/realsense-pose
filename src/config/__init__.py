from pathlib import Path
import yaml
from typing import Any, Dict, Union

def deep_update(orig: Dict[Any, Any], new: Dict[Any, Any]) -> None:
    """
    遞迴地將 new 字典中的鍵值更新到 orig 字典中。
    """
    for key, val in new.items():
        if (
            key in orig
            and isinstance(orig[key], dict)
            and isinstance(val, dict)
        ):
            deep_update(orig[key], val)
        else:
            orig[key] = val

# 配置檔路徑映射 (目前程式錄下的 configs 目錄)
config_dir = Path.cwd() / "configs"

CONFIG_FILES: Dict[str, Path] = {
    # 姿態擷取
    "pose": config_dir / "default_pose.yaml",
    # 分析器
    "analyzer": config_dir / "default_analyzer.yaml",
}

def load_config_file(path: Path) -> Dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))

def load_config(
    *,
    path: Union[str, Path, None] = None,
    mode: str = "pose",
) -> Dict[str, Any]:
    """
    載入指定模式的設定，合併預設設定與可選的使用者覆寫設定。

    參數:
        path: 使用者提供的 YAML 檔案路徑，用於覆寫預設設定。
        mode: 設定模式，可選值為 'pose' 或 'analyzer'。

    回傳:
        包含合併後設定的字典。

    例外:
        ValueError: 當 mode 無效或 YAML 解析錯誤時。
        FileNotFoundError: 當預設或覆寫檔案未找到時。
    """
    # 驗證模式
    if mode not in CONFIG_FILES:
        valid = ', '.join(CONFIG_FILES.keys())
        raise ValueError(f"無效的模式 '{mode}'。可選模式有：{valid}。")

    # 載入預設設定
    default_path = CONFIG_FILES[mode]
    if not default_path.exists():
        raise FileNotFoundError(f"找不到預設設定檔：{default_path}")

    try:
        defaults = yaml.safe_load(default_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"解析預設 YAML 時發生錯誤（{default_path}）：{e}")

    # 合併使用者覆寫設定（若有提供）
    if path:
        user_path = Path(path)
        if user_path.exists():
            try:
                overrides = yaml.safe_load(user_path.read_text(encoding="utf-8")) or {}
                deep_update(defaults, overrides)
            except yaml.YAMLError as e:
                raise ValueError(f"解析覆寫 YAML 時發生錯誤（{user_path}）：{e}")
        else:
            raise FileNotFoundError(f"找不到覆寫設定檔：({user_path})")

    return defaults