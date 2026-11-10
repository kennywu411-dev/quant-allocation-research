"""试验登记表：每次试验追加一行，用于统计试验次数、防止事后挑选。"""
from datetime import datetime
from pathlib import Path

import subprocess

import pandas as pd

TRIALS_PATH = Path("research/trials.csv")


def log_trial(row: dict, path: Path = TRIALS_PATH) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    new = pd.DataFrame([{**row, "logged_at": datetime.now().isoformat(timespec="seconds")}])
    if path.exists():
        new = pd.concat([pd.read_csv(path), new], ignore_index=True)
    new.to_csv(path, index=False)


def new_run_id() -> str:
    """本次运行的编号：时间 + git 短 sha，用来区分重复运行、统计真实试验次数。"""
    try:
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        sha = "nogit"
    return f"{datetime.now():%Y%m%dT%H%M%S}_{sha or 'nogit'}"
