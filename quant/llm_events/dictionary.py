"""不用大模型的基线：关键词词典给公告标题打方向分。规则在看结果前固定，之后不按结果调整。
方向：命中利空词 → 利空（利空优先，例如“终止回购”“减持”）；否则命中利好词 → 利好；都没有 → 中性。
实质性：命中任一方向词且不是程序性文件。"""
import pandas as pd

POS = ["预增", "扭亏", "大幅增长", "同比增长", "回购", "增持", "中标", "重大合同", "签订", "战略合作", "获得",
       "股权激励", "员工持股", "分红", "派息", "权益分派", "利润分配", "获批", "批准", "注册", "突破"]
NEG = ["预减", "首亏", "续亏", "亏损", "下降", "减持", "立案", "处罚", "警示函", "监管函", "问询函", "诉讼",
       "仲裁", "冻结", "质押", "风险提示", "终止", "违规", "退市", "调查", "留置", "失效", "取消", "不确定性"]
PROCEDURAL = ["法律意见书", "核查意见", "决议公告", "议事规则", "工作细则", "管理制度", "管理办法", "述职报告",
              "独立意见", "提示性公告", "审计报告", "鉴证报告", "专项说明", "候选人声明", "章程"]


def score(title: str) -> dict:
    neg = any(w in title for w in NEG)
    pos = any(w in title for w in POS)
    proc = any(w in title for w in PROCEDURAL)
    direction = "利空" if neg else ("利好" if pos else "中性")
    material = (neg or pos) and not proc
    return {"direction": direction if material else "中性", "strength": 1 if material else 0, "material": material}


def label(ann: pd.DataFrame) -> pd.DataFrame:
    """与大模型标注同样的列（id, direction, strength, material；type 记为“词典”）。"""
    rows = [{"id": i, "type": "词典", **score(t)} for i, t in zip(ann.id, ann.title)]
    return pd.DataFrame(rows, columns=["id", "type", "direction", "strength", "material"])
