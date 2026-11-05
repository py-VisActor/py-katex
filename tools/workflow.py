"""Reusable record/batch/verify commands; shared py-mermaid evidence format."""
from __future__ import annotations
import argparse,json,shutil,sys
from pathlib import Path
from run_support import ROOT,Run,verify_run

def resolve(path):return (ROOT/Path(path)).resolve()

def expand(value,run,python):
    for name,replacement in (("{repo}",str(ROOT)),("{run}",str(run.path)),("{runid}",run.id),("{python}",python)):
        value=value.replace(name,replacement)
    return value

def execute_steps(run: Run, steps: list[dict], python: str, *, keep_going: bool = False) -> int:
    first_failure = 0
    for step in steps:
        if not isinstance(step.get("argv"), list) or not all(isinstance(v, str) for v in step["argv"]):
            raise ValueError("Every step requires an argv string array")
        env = {k: expand(v, run, python) for k, v in step.get("env", {}).items()}
        result = run.command(step["name"], [expand(v, run, python) for v in step["argv"]],
                             cwd=Path(expand(step.get("cwd", "{repo}"), run, python)), env=env,
                             timeout=step.get("timeoutSeconds"))
        if result["exitCode"] != 0:
            first_failure = first_failure or result["exitCode"]
            if not keep_going:
                break
    return first_failure



def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    record=sub.add_parser('record');record.add_argument('--name',default='command');record.add_argument('--cwd',default='.');record.add_argument('--timeout',type=float,default=600);record.add_argument('--input',action='append',default=[]);record.add_argument('argv',nargs=argparse.REMAINDER)
    batch=sub.add_parser('batch');batch.add_argument('--plan',required=True);batch.add_argument('--keep-going',action='store_true')
    verify=sub.add_parser('verify');verify.add_argument('--run',type=Path,required=True)
    for command in (record,batch):
        command.add_argument('--scope',default='MATH');command.add_argument('--runs-dir',default='test-runs');command.add_argument('--python',default=sys.executable)
    args=p.parse_args(argv)
    if args.action=='verify':
        result=verify_run(args.run);print(json.dumps(result,indent=2));return 0 if result['integrityStatus']=='PASS' else 1
    plan=None
    if args.action=='batch':
        plan=json.loads(resolve(args.plan).read_text('utf-8'))
        if plan.get('schema')!='py-mermaid-command-plan/v1' or not plan.get('steps'):raise ValueError('Invalid command plan')
    run=Run(args.scope,args.action,runs_dir=resolve(args.runs_dir))
    with run:
        if plan:
            run.input(resolve(args.plan));shutil.copyfile(resolve(args.plan),run.path/'artifacts/plan.json')
            for path in plan.get('inputs',[]):run.input(Path(expand(path,run,args.python)))
            code=execute_steps(run,plan['steps'],args.python,keep_going=args.keep_going)
        else:
            for path in args.input:run.input(resolve(path))
            command=args.argv[1:] if args.argv[:1]==['--'] else args.argv
            code=run.command(args.name,command,cwd=resolve(args.cwd),timeout=args.timeout)['exitCode']
    print(json.dumps({'runId':run.id,'status':run.data['status'],'run':str(run.path)}))
    return code if 0<=code<=255 else 1

if __name__=='__main__':raise SystemExit(main())
