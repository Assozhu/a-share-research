"""Offline evidence, claim and scoring checks. Python 3 standard library only.

Does not verify URLs, original content, source independence or research coverage.
"""
import argparse
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse


WEIGHTS = {"industry": 20, "business": 20, "finance": 20,
           "valuation": 15, "catalyst": 15}


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def day(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("日期必须为YYYY-MM-DD")
    return date.fromisoformat(value)


def required_text(item, fields, label, errors):
    for key in fields:
        if not isinstance(item.get(key), str) or not item[key].strip():
            errors.append(f"{label}: 缺少非空字段 {key}")


def usable(item):
    return (item.get("type") == "Fact" and item.get("status") == "verified"
            and item.get("tier") in {"S", "A"}
            and item.get("confidence") in {"high", "medium"}
            and item.get("access_result") == "read"
            and not item.get("conflict_with"))


def refs(value, evidence, label, errors):
    if not isinstance(value, list) or any(not isinstance(v, str) for v in value):
        errors.append(f"{label}: evidence_ids应为字符串数组")
        return []
    if len(set(value)) != len(value):
        errors.append(f"{label}: 重复引用ID")
    for eid in value:
        if eid not in evidence:
            errors.append(f"{label}: 未知证据 {eid}")
    return [evidence[eid] for eid in value if eid in evidence]


def validate(run, records, claims, as_of=None):
    errors = []
    if not isinstance(run, dict):
        return ["run.json应为对象"]
    required_text(run, ["schema_version", "run_id", "company", "ticker", "market",
                        "currency", "as_of", "timezone", "horizon", "mode", "style"], "run", errors)
    try:
        cutoff = day(run.get("as_of"))
        if as_of and cutoff != day(as_of):
            errors.append("指定研究日与run.as_of不一致")
    except ValueError:
        return errors + ["run: 无效研究日期"]
    if run.get("status") not in {"planned", "collecting", "limited", "complete"}:
        errors.append("run: 无效状态")
    if not isinstance(run.get("gaps"), list):
        errors.append("run: gaps应为数组")
    if not isinstance(records, list) or not isinstance(claims, list):
        return errors + ["evidence.json与claims.json必须为数组"]
    evidence = {}
    for i, item in enumerate(records):
        if not isinstance(item, dict):
            errors.append(f"evidence[{i}]应为对象")
            continue
        eid = item.get("id")
        label = str(eid or f"evidence[{i}]")
        required_text(item, ["id", "content", "source_title", "publisher", "url", "accessed_at",
                            "confidence_reason", "access_method", "locator", "source_family"], label, errors)
        if isinstance(eid, str):
            if eid in evidence:
                errors.append(f"{label}: 重复ID")
            evidence[eid] = item
        try:
            parsed = urlparse(item.get("url", ""))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                errors.append(f"{label}: 原始链接无效")
        except (TypeError, ValueError):
            errors.append(f"{label}: 原始链接无效")
        for key in ["published_at", "period", "value", "unit", "value_basis", "notes",
                    "supersedes", "conflict_with"]:
            if key not in item:
                errors.append(f"{label}: 缺少字段 {key}")
        if item.get("period") is None and not item.get("notes"):
            errors.append(f"{label}: 数据期间未知须解释")
        elif item.get("period") is not None and not isinstance(item["period"], str):
            errors.append(f"{label}: period应为字符串或null")
        if item.get("type") not in {"Fact", "Opinion", "Signal"}:
            errors.append(f"{label}: 类型须为Fact/Opinion/Signal")
        if item.get("tier") not in {"S", "A", "B", "C", "D"}:
            errors.append(f"{label}: 无效来源等级")
        if item.get("confidence") not in {"high", "medium", "low"}:
            errors.append(f"{label}: 无效可信度")
        if item.get("status") not in {"verified", "attributed", "unverified", "conflicted", "superseded"}:
            errors.append(f"{label}: 无效证据状态")
        if item.get("access_result") != "read":
            errors.append(f"{label}: 未读原文应存入搜索日志")
        if item.get("type") == "Fact" and item.get("status") == "verified" and item.get("tier") not in {"S", "A"}:
            errors.append(f"{label}: 已验证事实须有S/A原始来源")
        if item.get("type") == "Opinion" and item.get("status") not in {"attributed", "conflicted", "superseded"}:
            errors.append(f"{label}: 观点不能标记verified")
        if item.get("type") == "Signal" and item.get("status") not in {"unverified", "conflicted", "superseded"}:
            errors.append(f"{label}: 线索不能标记verified")
        if item.get("value_basis") not in {"reported", "forecast", "not_applicable"}:
            errors.append(f"{label}: 无效value_basis")
        if item.get("value") is not None and (not finite(item["value"]) or not item.get("unit")):
            errors.append(f"{label}: 数值须有限并有单位")
        try:
            accessed = day(item.get("accessed_at"))
            published = day(item["published_at"]) if item.get("published_at") else None
            if published and (published > cutoff or published > accessed):
                errors.append(f"{label}: 使用了研究日之后或访问日之后的披露")
            if published is None and not item.get("notes"):
                errors.append(f"{label}: 发布日期未知须解释")
        except (ValueError, TypeError):
            errors.append(f"{label}: 无效日期")
    for eid, item in evidence.items():
        refs(item.get("supersedes", []), evidence, eid + ".supersedes", errors)
        refs(item.get("conflict_with", []), evidence, eid + ".conflict_with", errors)
        if item.get("status") == "verified" and item.get("conflict_with"):
            errors.append(f"{eid}: 未决冲突不能标verified")
    claim_ids = set()
    for i, claim in enumerate(claims):
        if not isinstance(claim, dict):
            errors.append(f"claim[{i}]应为对象")
            continue
        label = str(claim.get("id") or f"claim[{i}]")
        required_text(claim, ["id", "category", "logic", "conclusion", "falsification"], label, errors)
        if isinstance(claim.get("id"), str):
            if claim["id"] in claim_ids:
                errors.append(f"{label}: 重复Claim ID")
            claim_ids.add(claim["id"])
        if claim.get("importance") not in {"core", "ordinary"}:
            errors.append(f"{label}: 无效重要程度")
        if claim.get("status") not in {"supported", "hypothesis", "insufficient"}:
            errors.append(f"{label}: 无效结论状态")
        if not isinstance(claim.get("assumptions"), list):
            errors.append(f"{label}: assumptions应为数组")
        if "calculation" not in claim:
            errors.append(f"{label}: 缺少calculation字段")
        selected = refs(claim.get("evidence_ids"), evidence, label, errors)
        refs(claim.get("counter_evidence_ids"), evidence, label + ".counter", errors)
        facts = [e for e in selected if usable(e)]
        if claim.get("status") == "supported":
            enough = bool(facts)
            if claim.get("importance") == "core":
                enough = (any(e["tier"] == "S" for e in facts)
                          or len({e["source_family"] for e in facts}) >= 2)
            if not enough:
                errors.append(f"{label}: 支持结论未满足核心/普通事实门槛")
            if any(e.get("tier") == "D" for e in selected):
                errors.append(f"{label}: 社交来源不得作为投资依据")
        calculation = claim.get("calculation")
        if calculation is not None:
            if not isinstance(calculation, dict):
                errors.append(f"{label}: calculation应为对象或null")
                continue
            required_text(calculation, ["formula", "unit", "rounding", "basis_date"], label + ".calculation", errors)
            if calculation.get("basis") not in {"actual", "forecast", "scenario"}:
                errors.append(f"{label}: calculation.basis须为actual/forecast/scenario")
            if not finite(calculation.get("output")):
                errors.append(f"{label}: 计算结果须为有限数字")
            try:
                if day(calculation.get("basis_date")) > cutoff:
                    errors.append(f"{label}: 计算时点晚于研究日")
            except (ValueError, TypeError):
                errors.append(f"{label}: 计算时点无效")
            inputs = calculation.get("inputs")
            if not isinstance(inputs, list) or not inputs:
                errors.append(f"{label}: 缺少计算输入")
                continue
            for inp in inputs:
                if not isinstance(inp, dict):
                    errors.append(f"{label}: 输入须为对象")
                    continue
                required_text(inp, ["name", "unit"], label + ".input", errors)
                if not finite(inp.get("value")):
                    errors.append(f"{label}: 输入须为有限数值")
                linked = refs(inp.get("evidence_ids", []), evidence, label + ".input", errors)
                if not linked and not inp.get("assumption"):
                    errors.append(f"{label}: 输入无证据或明确假设")
                if calculation.get("basis") == "actual" and (inp.get("assumption") or any(
                        not usable(e) or e.get("value_basis") == "forecast" for e in linked)):
                    errors.append(f"{label}: 实际计算不得使用预测、假设或未核实数据")
                if any(e.get("tier") == "D" for e in linked):
                    errors.append(f"{label}: 社交数据不得用于估值输入")
    return errors


def score(config, evidence):
    if not isinstance(config, dict) or not isinstance(config.get("dimensions"), dict):
        raise ValueError("评分配置须有dimensions对象")
    if set(config["dimensions"]) != set(WEIGHTS):
        raise ValueError("评分维度必须恰为五项，不能偷偷改变权重")
    def support(ids):
        errors = []
        found = refs(ids, evidence, "score", errors)
        if errors or not found or any(not usable(e) or e.get("value_basis") == "forecast" for e in found):
            raise ValueError("评分项缺少可用的实际S/A事实证据")
    dimensions = {}
    for name in WEIGHTS:
        metrics = config["dimensions"][name].get("metrics")
        if not isinstance(metrics, list) or len(metrics) != 3:
            raise ValueError(f"{name}: 必须有3项指标（可为缺失）")
        values = []
        for metric in metrics:
            if metric.get("observed") is None:
                if not metric.get("notes"):
                    raise ValueError("缺失指标须说明原因")
                values.append(None)
                continue
            support(metric.get("evidence_ids"))
            rule = metric.get("rule", {})
            if not rule.get("basis"):
                raise ValueError("评分规则须说明依据")
            observed = metric["observed"]
            if rule.get("kind") == "numeric":
                cuts = rule.get("thresholds")
                if (not finite(observed) or not isinstance(cuts, list) or len(cuts) != 4
                        or not all(finite(v) for v in cuts)
                        or any(a >= b for a, b in zip(cuts, cuts[1:]))
                        or rule.get("direction") not in {"higher", "lower"}):
                    raise ValueError("数值分档需要有限观测和4个递增阈值")
                result = sum(observed >= cut for cut in cuts) * 25
                values.append(result if rule["direction"] == "higher" else 100 - result)
            elif rule.get("kind") == "disclosure":
                bands = rule.get("bands")
                if (not isinstance(bands, list) or len(bands) != 5
                        or any(not isinstance(v, str) for v in bands)
                        or len(set(bands)) != 5 or observed not in bands):
                    raise ValueError("披露分档须有5个不同状态，观测须匹配")
                values.append(bands.index(observed) * 25)
            else:
                raise ValueError("未知评分规则")
        dimensions[name] = None if None in values else sum(values) / 3
    if not isinstance(config.get("risks"), list):
        raise ValueError("risks须为数组")
    reviewed = config.get("risk_review_complete")
    if not isinstance(reviewed, bool):
        raise ValueError("risk_review_complete须为布尔值")
    risk = None
    if reviewed:
        risk = 0
        names = set()
        for item in config["risks"]:
            if not item.get("name") or item["name"] in names:
                raise ValueError("风险项名称须唯一且非空")
            names.add(item["name"])
            support(item.get("evidence_ids"))
            if (not isinstance(item.get("triggered"), bool)
                    or not finite(item.get("deduction"))
                    or item["deduction"] not in {0, 5, 10, 20}
                    or not item.get("rule")):
                raise ValueError("风险项须有触发规则和合法扣分")
            if item["triggered"]:
                risk += item["deduction"]
        risk = min(20, risk)
    q = [dimensions[n] for n in ["industry", "business", "finance"]]
    quality = None if None in q else sum(q) / 3
    gross = None if any(v is None for v in dimensions.values()) else sum(
        dimensions[n] * weight for n, weight in WEIGHTS.items()) / 90
    return {"dimensions": dimensions, "company_quality": quality,
            "opportunity_gross": gross, "risk_deduction": risk,
            "opportunity_net": None if gross is None or risk is None else max(0, gross - risk),
            "weight_coverage_percent": sum(WEIGHTS[n] for n in WEIGHTS if dimensions[n] is not None) / 90 * 100,
            "note": "规则评分，非收益预测；证据真实性、匹配与覆盖须人工核验"}


def load(path):
    def reject(value):
        raise ValueError(f"非法JSON常量: {value}")
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=reject)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["validate", "score"])
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--as-of")
    args = parser.parse_args()
    try:
        run = load(args.run_dir / "run.json")
        records = load(args.run_dir / "evidence.json")
        claims = load(args.run_dir / "claims.json")
        errors = validate(run, records, claims, args.as_of)
        if errors:
            print(json.dumps({"valid": False, "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        if args.command == "score":
            result = score(load(args.run_dir / "scoring.json"), {e["id"]: e for e in records})
        else:
            result = {"valid": True, "evidence_count": len(records), "claim_count": len(claims),
                      "scope": "结构及引用约束通过；原文真实性与研究完整性未由脚本验证"}
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
