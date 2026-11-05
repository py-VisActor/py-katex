"""Write current full-core acceptance documents from closed verified evidence."""
from pathlib import Path
import argparse
import json
from datetime import datetime, timezone, timedelta

from joint_candidate import current
from run_support import ROOT, file_identity, verify_run, write_json


def read(path):
    return json.loads(path.read_text('utf-8'))


def prepend(path, text):
    if path.exists():
        old = path.read_text('utf-8')
        if text not in old:
            path.write_text(text + '\n\n' + old, 'utf-8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['unit', 'visual', 'legacy', 'report', 'qa', 'audit-run']:
        p.add_argument('--' + name, required=True)
    p.add_argument('--manual-run', action='append', default=[])
    args = p.parse_args()
    report_dir = ROOT.parent / 'py-mermaid/reports' / args.report
    summary = read(report_dir / 'summary.json')
    assert summary['status'] == 'PASS_FULL_CORE_STATIC_LOCAL'
    assert current() == summary['source']
    runs = {'unit': args.unit, 'visual': args.visual, 'legacy': args.legacy,
            'report': args.report, 'htmlQa': args.qa}
    runs.update({'manual' + str(i + 1): value for i, value in enumerate(args.manual_run)})
    for name, value in runs.items():
        directory = ROOT / 'test-runs' / value
        manifest = read(directory / 'run.json')
        assert manifest['status'] == 'SUCCESS' and manifest['sourceUnchanged'], name
        assert verify_run(directory)['integrityStatus'] == 'PASS', name
    qa = read(ROOT / 'test-runs' / args.qa / 'artifacts/qa/report.json')
    assert qa['status'] == 'PASS' and len(qa['views']) == summary['views']
    html = file_identity(report_dir / 'index.html')
    assert qa['htmlSha256'] == html['sha256']
    url = 'http://127.0.0.1:8765/' + args.report + '/index.html'
    summary.update({
        'schema': 'py-katex-full-verification-summary/v1',
        'runs': {name: 'test-runs/' + value for name, value in runs.items()},
        'jointCandidate': 'test-runs/' + args.unit + '/artifacts/joint-candidate.json',
        'jointSourceSHA256': {name: value['sourceTreeSha256'] for name, value in summary['source'].items()},
        'report': {'url': url, 'path': 'py-mermaid/reports/' + args.report, 'html': html,
                   'qaStatus': 'PASS', 'qaViews': len(qa['views']), 'desktopAndMobile': True,
                   'externalRequests': 0, 'currentSourceMatches': True},
        'postDocumentationAudit': 'test-runs/' + args.audit_run,
        'historicalAlphaSummary': 'references/verification-summary.json',
        'firstFullFailure': 'test-runs/MATH-batch-20261105T155834Z-e542e4f2',
        'firstFixtureRecovery': 'test-runs/MATH-FULL-historical-input-recovery-20261105T164058Z-d5c1c74b',
        'manualRejectedCandidate': 'references/full-manual-rejected-candidate.json',
        'externalActions': {'commit': False, 'push': False, 'publish': False},
    })
    write_json(ROOT / 'references/full-verification-summary.json', summary)
    write_json(ROOT.parent / 'py-mermaid/references/math-full-verification-summary.json', summary)
    day = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
    doc = f'''# KaTeX 核心静态迁移验收

{day}：完成固定 KaTeX **0.18.11** 核心保留静态能力的本地迁移与 Mermaid 接入。版本仍为未发布的 `0.1.0a0`，版本号不表示本轮工作未验收。

## 本轮补齐

完整宏展开与作用域/持久状态、动态宏和回调、严格/信任/错误配置；AMS/CD、矩阵与数组、tag/自动编号、leqno/fleqn、尺寸限制与断行；字体轴、Unicode 回退、伸缩/重音/装饰、PMB；显式离线图片及 HTML 静态样式；真实墨迹边界、PNG/JPG/WebP/SVG/PDF 导出。Mermaid 节点、边、组标签通过独立 Python 模块绘制数学。

生产仅使用 Python 与公开 Canvas API，不依赖 Node、浏览器、JS 解释器或 DOM。20 个数学字体与源度量随包提供；其它 Unicode 字体可显式注入，系统回退不等于完整离线字库。

## 同候选验收

| 验证层 | 实际结果 |
| --- | --- |
| 新旧单元测试 | {summary['tests']['total']} 个方法全部通过，无跳过 |
| 核心注册与宏 | 312 函数 + 33 环境 = 345 注册入口；339 宏；684 个合法/错误语义上下文 |
| 固定上游功能语料 | {summary['coreCorpus']['sourceClauses']} 个来源测试条目中的 {summary['coreCorpus']['expressions']} 个功能输入全部通过 |
| 正向等价关系 | {summary['coreCorpus']['equivalencePairs']} 组全部通过 |
| 独立数学静态图 | {summary['standaloneCases']} 例 × CPU/auto/必需 GPU |
| Mermaid 数学集成 | {summary['integrationCases']} 例 × 三后端；合计 {summary['views']} 份结果 |
| 历史流程图 | F01.1–F01.4 共 297 正例 × 三后端；负例、源错误与范围类别均保留 |
| 实际静态导出 | PNG、JPG、WebP、SVG、PDF 五种 |
| HTML 报告 | {len(qa['views'])} 视图、5 种下载、桌面/手机宽度通过；无外部请求 |

注册分母来自真实锁定源码注册，不是旧静态扫描的 334。孤立 `\\]` 按源仅报错，其余内部入口通过真实消费上下文验证。功能语料检查接受/拒绝、诊断、决策回调及可见等价关系；**不声称执行或移植了原 Jest 全部私有树/HTML/MathML/snapshot 断言**。图像检查含实际像素、内容、字体轴、几何关系、资源和画布边界；跨 DOM/Canvas 像素不要求逐点一致。

## 可复核交付

[打开 HTML 对比报告]({url})，包含固定官方 A 与 Python B 的原始 PNG、源输入、三后端筛选、原图及五格式下载。人工复核记录见机器摘要的 manual run；报告不会改写 A 图。

- 单元/语料：`test-runs/{args.unit}`
- 三后端/导出：`test-runs/{args.visual}`
- 历史回归：`test-runs/{args.legacy}`
- 报告/浏览器 QA：`test-runs/{args.report}`、`test-runs/{args.qa}`
- 联合源码 SHA256：math `{summary['jointSourceSHA256']['math']}`；Mermaid `{summary['jointSourceSHA256']['mermaid']}`。

全部闭合 run 校验原始字节和源码未变；产品源码、验证输入、首轮全部失败与后续修复均保留。曾经自动全通过但人工发现字体轴、SVG 比例和样式框问题的候选被明确拒收，记录见 [人工拒收候选](../references/full-manual-rejected-candidate.json)。最初失败输入已按原日志 SHA256 重建，保存在新的恢复 run，未修改旧 run。最终文档审计入口为 `test-runs/{args.audit_run}`。机器摘要见 [full-verification-summary.json](../references/full-verification-summary.json)，复用步骤见 [FULL_RUNS_AND_REPORTS.md](FULL_RUNS_AND_REPORTS.md)。

## 明确范围与差异

核心静态目标已验收；HTML/MathML 输出后端、任意浏览器宿主 CSS 引擎、交互/无障碍 DOM 行为，以及独立 contrib 插件分别分类，未计作原生通过。`mhchem` 是独立扩展，未移植；auto-render/copy-tex/mathtex-script 的浏览器集成不在静态目标。静态样式通过有限的原生属性适配，不支持的可见属性明确诊断。

固定 Mermaid 的元数据反斜线损坏、MathML 组标题字体和边界空格差异在报告逐例说明；不把对损坏源的修正写成与异常画面等价。相同源的 fleqn/leqno 标号重叠也保留来源说明。字体栅格、留白和自然尺寸差异允许，遗漏内容与错误关系不得通过。

安装/构建验证按用户要求暂缓；本机 Windows 证据不能证明 Linux/no-loader 环境。源码与报告均未提交、推送或发布。历史 alpha 验收仍保留，但不能证明当前候选。
'''
    (ROOT / 'docs/FULL_STATIC_ACCEPTANCE.md').write_text(doc, 'utf-8')
    parent_doc = f'''# 完整数学核心静态能力接入验收

{day}：独立 py-katex 已完成固定 KaTeX 0.18.11 核心静态迁移并接入 Mermaid。详见 [完整验收](../../py-katex/docs/FULL_STATIC_ACCEPTANCE.md) 和 [机器摘要](../references/math-full-verification-summary.json)。

{summary['tests']['total']} 个测试方法、684 个注册/宏上下文、{summary['coreCorpus']['expressions']} 个上游功能输入及 {summary['coreCorpus']['equivalencePairs']} 组等价关系通过；{summary['standaloneCases']} 个公式和 {summary['integrationCases']} 个集成图三后端共 {summary['views']} 视图通过，297 个历史流程图三后端回归通过。五格式导出、人工看图与 HTML QA 已完成。

[查看报告]({url})。全部模块只做静态渲染，Dagre 完全剥离；任意宿主 CSS、HTML/MathML 输出后端及独立 contrib 扩展不在核心验收范围。安装验证继续暂缓，未提交推送发布。旧 alpha 及旧“数学延后”说明保留为历史。
'''
    (ROOT.parent / 'py-mermaid/docs/MATH_FULL_ACCEPTANCE.md').write_text(parent_doc, 'utf-8')
    for repo in [ROOT, ROOT.parent / 'py-mermaid']:
        state_file = repo / 'docs/execution-state.json'
        state = read(state_file)
        previous = repo / 'docs/changes/math-full-prior-execution-state.json'
        if not previous.exists():
            write_json(previous, state, exclusive=True)
        state.update({
            'phase': 'MATH-FULL-P5', 'currentScopeStatus': 'complete_local_core_static',
            'functionalStatus': 'PASS_FULL_CORE_STATIC_LOCAL', 'status': 'complete_local_core_static',
            'scope': 'MATH-FULL', 'activeLeases': [], 'remainingCoreStaticWork': [],
            'coreStaticScopeComplete': True, 'fullKaTeXCompatibility': False,
            'fullKaTeXCompatibilityMeaning': 'Entire browser output/contrib ecosystem is not claimed; retained core static scope is complete.',
            'installationValidation': 'deferred_by_user_not_executed',
            'externalActions': {'commit': False, 'push': False, 'publish': False},
            'jointSourceSHA256': summary['jointSourceSHA256'],
            'workerStatus': {name: 'verified_stopped_source' for name in ['root', 'parser_config', 'geometry_elk', 'canvas_labels']},
            'postDocumentationAudit': '../py-katex/test-runs/' + args.audit_run + '/run.json',
            'historicalExecutionState': 'docs/changes/math-full-prior-execution-state.json',
            'report': summary['report'], 'legacyTaskTablesHistorical': True,
            'fullStaticScope': ('references/' if repo == ROOT else '../py-katex/references/') + 'full-core-inventory.json',
            'remainingScope': ['Installation/build validation deferred by user.', 'Linux/no-loader not verified.', 'Arbitrary browser CSS, HTML/MathML outputs and independent contrib are separately scoped.'],
        })
        if repo == ROOT:
            state.update({'finalVerification': 'references/full-verification-summary.json', 'runs': summary['runs'],
                          'activePlan': 'docs/FULL_STATIC_MIGRATION.md', 'plan': 'docs/FULL_STATIC_MIGRATION.md'})
        else:
            state.update({'finalVerificationSummary': 'references/math-full-verification-summary.json',
                          'finalCandidateRuns': {name: '../py-katex/' + value for name, value in summary['runs'].items()},
                          'currentSourceIdentity': {'treeSha256': summary['jointSourceSHA256']['mermaid'],
                             'evidence': '../py-katex/' + summary['jointCandidate'], 'wheelSha256': None},
                          'mathSourceIdentity': summary['jointSourceSHA256']['math'],
                          'mathModule': {'repository': 'https://github.com/py-VisActor/py-katex', 'localPath': '../py-katex',
                             'version': '0.1.0a0', 'sourceKaTeX': '0.18.11', 'status': 'complete_local_core_static',
                             'acceptance': 'docs/MATH_FULL_ACCEPTANCE.md', 'coreStaticScopeComplete': True}})
        write_json(state_file, state)
    top = f'> {day} **固定 KaTeX 0.18.11 核心静态迁移已完成本地验收**：{summary["tests"]["total"]} 方法、684 上下文、{summary["coreCorpus"]["expressions"]} 功能输入/{summary["coreCorpus"]["equivalencePairs"]} 等价关系、{summary["cases"]} 案例三后端与 297 历史流程图三后端通过。当前入口为 [完整验收](FULL_STATIC_ACCEPTANCE.md)。安装验证暂缓，未提交推送发布；下方旧 alpha/未实现状态仅作历史。'
    for name in ['ACCEPTANCE.md', 'EXECUTION_PLAN.md', 'FULL_STATIC_MIGRATION.md', 'INTERFACES.md', 'RUNS_AND_REPORTS.md']:
        prepend(ROOT / 'docs' / name, top)
    prepend(ROOT / 'AGENTS.md', top.replace('(FULL_STATIC_ACCEPTANCE.md)', '(docs/FULL_STATIC_ACCEPTANCE.md)'))
    parent_top = top.replace('(FULL_STATIC_ACCEPTANCE.md)', '(MATH_FULL_ACCEPTANCE.md)')
    for name in ['MATH_ACCEPTANCE.md', 'EXECUTION_HANDOFF.md', 'NEW_SESSION.md', 'RELEASE_STATUS.md', 'TASKS.md']:
        prepend(ROOT.parent / 'py-mermaid/docs' / name, parent_top)
    prepend(ROOT.parent / 'py-mermaid/AGENTS.md', parent_top.replace('(MATH_FULL_ACCEPTANCE.md)', '(docs/MATH_FULL_ACCEPTANCE.md)'))
    for name in ['math-full-parser', 'math-full-layout', 'math-full-canvas', 'math-full-root']:
        for receipt in (ROOT / 'docs/changes').glob(name + '*.json'):
            if 'visual-qa' in receipt.name:
                continue
            value = read(receipt)
            value['finalVerification'] = {'status': summary['status'], 'summary': 'references/full-verification-summary.json',
                'jointSourceSHA256': summary['jointSourceSHA256'], 'runs': summary['runs']}
            write_json(receipt, value)
    inventory = read(ROOT / 'references/full-core-inventory.json')
    inventory['finalVerification'] = {'status': summary['status'], 'summary': 'references/full-verification-summary.json'}
    write_json(ROOT / 'references/full-core-inventory.json', inventory)
    assert current() == summary['source'], 'Documentation modified product source'
    print(json.dumps({'status': 'PASS', 'report': url, 'methods': summary['tests']['total'], 'views': summary['views']}))


if __name__ == '__main__':
    main()
