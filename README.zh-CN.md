# JSON Diff

比较保存下来的 API 响应和 JSON 文件：过滤易变字段、输出机器可读的差异，并生成离线 HTML 报告。

[English / 完整文档](README.md) · [示例文件](examples) · [贡献指南](CONTRIBUTING.md)

## 快速使用

需要 Python 3.8 或更新版本。请从**本仓库源码**安装；我们没有验证软件包仓库中同名 `json-diff` 包属于这个项目。

```bash
git clone https://github.com/Master-626/json-diff.git
cd json-diff
python -m pip install .

json-diff compare examples/expected.json examples/actual.json \
  --ignore-path /meta/request_id \
  --ignore-path /meta/generated_at
```

示例会找出两处差异并返回退出码 `1`：

- `users[0].role` 从 `"reader"` 变成 `"admin"`。
- `users[1]` 新增了一个用户对象。

将命令里的 `examples/actual.json` 换成 `examples/equivalent.json`，结果应为无差异，退出码 `0`。

## 常用命令

```bash
# JSON 输出；相等时也输出合法 JSON：[]。
json-diff compare expected.json actual.json --json-output > diff.json

# 全局忽略同名字段，包括新增和删除。
json-diff compare expected.json actual.json --ignore generated_at

# 只忽略指定位置。* 匹配一层键名或数组下标，必须加引号。
json-diff compare expected.json actual.json --ignore-path '/users/*/last_seen'

# 从标准输入读取其中一个文件。
cat actual.json | json-diff compare expected.json -

# 生成报告；保存后若有差异则返回 1。
json-diff report expected.json actual.json -o report.html --fail-on-diff
```

`compare` 的退出码：`0` 表示相等，`1` 表示有差异，`2` 表示输入或用法错误。报错写入 stderr。`report` 默认在成功保存后返回 `0`；添加 `--fail-on-diff` 才会对差异返回 `1`。

JSON 输出中的 `pointer` 是 RFC 6901 JSON Pointer，可准确区分含点号、斜杠等字符的键名。根节点的 pointer 是空字符串。忽略路径中的 `/` 和 `~` 分别编码为 `~1` 和 `~0`。

## 使用边界

- 数组按下标比较，新增和删除尾部元素会单独报告；不支持按 ID 对齐或最小编辑距离。
- 类型严格：`true`、`1`、`1.0` 互不相同。小数使用 Python 二进制浮点数，不适合要求精确十进制的财务比较。
- 拒绝重复键、非法 JSON、非有限数和浮点数溢出。输入文件使用 UTF-8，可带 UTF-8 BOM。
- 忽略一个容器会跳过其子树；整个容器新增、删除或类型改变时，会报告完整容器，子字段的忽略规则不会取消父节点变化。
- 忽略规则不是脱敏工具。报告可能包含敏感数据，分享或上传 CI 附件前请检查。
- 报告中的文件名、键和值会转义，不包含脚本或外部资源；禁止覆盖输入文件。
- 工具只读取本地文件或标准输入，不发送网络请求；不提供 schema 校验、补丁应用或 API 兼容性判定。数据有差异不一定意味着接口不兼容。
- 全部数据保存在内存中，不是流式处理器；输入文件最多允许 200 层嵌套容器。完整规则、限制和 Python API 见[英文文档](README.md)。

开发验证：

```bash
python -m pip install -e '.[dev]'
python -m pytest --cov=json_diff --cov-report=term-missing
ruff check .
ruff format --check .
python -m build
```

[MIT 许可证](LICENSE)。
