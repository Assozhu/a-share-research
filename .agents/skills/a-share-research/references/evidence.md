# 证据、来源与数据结构

## 来源分级

等级是本 Skill 的研究约定，不是监管认证或保证真实性。

| 等级 | 文档性质 | 使用限制 |
|---|---|---|
| S | 交易所披露文件、监管原文、公司正式财报、审计报告、官方统计 | 核心事实优先；披露、审计及统计仍有范围限制，管理层预测不变成实际事实 |
| A | 公司官方新闻、IR材料、公司自述资料 | 可核验披露事实；经营预期仍为Opinion，记录利益关系 |
| B | 券商、行业与咨询报告 | 来源观点，不能直接升级为公司事实；底层数据追溯S/A原文 |
| C | 财经媒体 | 新闻入口、关注方向；核心事件追溯公告或正式发布者 |
| D | 雪球、股吧、微博、小红书等社交内容 | Signal或Opinion；仅情绪与问题线索，不做投资依据 |

“公司公告”重叠处理：交易所/指定披露渠道正式公告归S；官网新闻及非正式IR材料归A。同一正式财报在官网的可核验副本仍按文档性质归S。不能因文章托管在交易所域名就归S。

Fact须核验对应陈述，可信度high/medium/low说明原因。S事实也可因旧期、原文异常或口径冲突而降可信度。Opinion注明作者、机构、利益关系，Signal注明未核查内容。Reasoning保存在claims中，不能把模型推断写进事实库。

核心投资事实：一项直接相关、原文已读且无未决冲突的S来源，或至少两项独立S/A来源。普通事实：至少一项S/A原文。B/C引述若未找到底层合格源，只写归属清楚的Opinion/Signal。来源族按原始发布者、文档及其底层数据判断；公司IR复述公司公告不是独立佐证，全文与摘要不是双重验证。

披露“预计赚X”可核实为已披露预测，但value_basis=forecast，不能被当actual输入。公司未来需求、竞争力、客户认证表述记Opinion，独立验证后另建Fact。未知日期或期间null并写notes，不能从URL猜发布时间。更正、重述保留旧证据并标记superseded；截至研究截止日的版本才可引用，未来资料不能用于历史复盘。

## 研究目录

```text
research/<证券代码>/<截止日>-<唯一标识>/
  run.json
  research-plan.md
  search-log.json
  evidence.json
  claims.json
  scoring.json
  report.md
  research-memory.json
```

保存JSON UTF-8；ID在本次研究中唯一，后续复盘引用run_id及原ID。原始PDF可另存source/，只有实际下载才填local_path；工具读取而未下载时以URL和页码追溯。搜索结果ID不是交付链接。

### run.json

```json
{
  "schema_version": "1.0",
  "run_id": "由实际生成时间或序号构成的唯一标识",
  "company": "核实的名称",
  "ticker": "六位代码.SZ或.SH或.BJ",
  "market": "A-share",
  "currency": "CNY",
  "as_of": "YYYY-MM-DD",
  "timezone": "Asia/Shanghai",
  "horizon": "1–3个月",
  "mode": "中短期",
  "style": "平衡研究",
  "defaults_applied": ["horizon", "mode", "style"],
  "status": "planned",
  "gaps": []
}
```

status: planned/collecting/limited/complete。没有完成全量研究时用limited；run.json状态不是脚本能独立证实的事实。

### evidence.json：原子记录数组

```json
[
  {
    "id": "E001",
    "content": "一条实际读到的陈述",
    "type": "Fact",
    "source_title": "原始资料标题",
    "publisher": "发布者",
    "url": "https://原始文档地址",
    "published_at": null,
    "period": "明确的数据期间",
    "accessed_at": "YYYY-MM-DD",
    "tier": "S",
    "confidence": "high",
    "confidence_reason": "直接表格披露且已核对单位",
    "status": "verified",
    "access_method": "实际工具与读取方式",
    "access_result": "read",
    "locator": "页码、章节、表格行或接口字段",
    "source_family": "原始发布者与文档/数据族",
    "value": null,
    "unit": null,
    "value_basis": "reported",
    "notes": "发布日期未知的原因",
    "supersedes": [],
    "conflict_with": []
  }
]
```

status为verified/attributed/unverified/conflicted/superseded。Fact用verified；Opinion用attributed；Signal用unverified。access_result=read表示原文确实已读；失败不生成可用Fact，记搜索日志。value只存原子观测或原始预测，数值不得NaN/Infinity。value_basis为reported/forecast/not_applicable。单位示例CNY、CNY/share、percent、shares。实际已报告不等于已审计，审计状态在notes。

### claims.json：分析与计算记录数组

```json
[
  {
    "id": "C001",
    "category": "financial",
    "importance": "core",
    "evidence_ids": ["E001"],
    "logic": "可审查的依据与公司传导关系",
    "assumptions": ["明确、可检验的假设"],
    "conclusion": "条件性结论",
    "counter_evidence_ids": [],
    "falsification": "何种实际变化将推翻结论",
    "status": "supported",
    "calculation": null
  }
]
```

importance=core/ordinary；status=supported/hypothesis/insufficient。supported须满足证据门槛，且不能将Opinion/Signal当验证事实；未验证预测命题标hypothesis。证据可同时包含Opinion用于归属清楚的对照，但核心的事实基座须合格。calculation非null时记录inputs（名称、数值、单位、evidence_ids或明确assumption）、formula、output、unit、rounding、basis_date及basis（actual/forecast/scenario）。所有衍生量归Reasoning，既非已披露数字，也不新增伪造的原始来源。

### search-log.json

数组条目含searched_at、tool、query、scope（平台/域名）、window、outcome（read/failed/discovered/not_attempted）、urls、notes。社交平台条目另加platform、access_method、sample_count、coverage_gap。尚未检索的平台写not_attempted，不能写failed。

### scoring.json

完整格式及维度定义见 [评分规则](scoring.md)。研究记忆直接使用 [复盘模板](../assets/research-memory.json)。
