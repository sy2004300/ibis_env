# AGENTS.md

## Immutable reference material

除非用户明确授权，禁止修改：

- `SPEC.md`
- `ACCEPTANCE_TESTS.md`
- `PROJECT_STATUS.md`
- `inputs/**`
- `golden/**`
- `templates/t2b/**`
- `tests/test_vectors.json`
- `tests/run_acceptance.py`

若实现与冻结材料冲突，不得修改标准答案来制造 PASS；请输出 `SPEC_CONFLICT` 并解释冲突。

## Implementation area

你可以自由创建并重构：

- `src/**`
- `pyproject.toml`
- 运行时 log/报告
- UI 代码
- `generated/**`

## Development loop

1. 阅读 MASTER_PROMPT / SPEC / ACCEPTANCE。
2. 从零实现，不依赖公司内网工具。
3. 执行 `python tests/run_acceptance.py`。
4. 失败时分析真实原因并修改实现。
5. 重复直到 Case 001 Golden PASS。
6. 不要伪造 PASS，不要跳过失败测试。

## User-facing language

Warning / Error / Summary 对用户使用中文；内部 error code 可用英文。
