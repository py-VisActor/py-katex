"""The shared run protocol preserves failures and detects changed evidence."""
from pathlib import Path
import json,sys,tempfile,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from run_support import Run,verify_run


class EvidenceContracts(unittest.TestCase):
    def test_failed_command_is_not_functional_success_and_remains_verifiable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with Run('control','failure',root=root) as run:
                result=run.command('intentional-nonzero',[sys.executable,'-c','import sys;print("preserved");sys.exit(7)'],cwd=root)
                self.assertEqual(result['exitCode'],7)
            data=json.loads((run.path/'run.json').read_text('utf-8'))
            self.assertEqual(data['status'],'FAILED')
            self.assertEqual(data['functionalStatus'],'NOT_EVALUATED')
            self.assertEqual(verify_run(run.path)['integrityStatus'],'PASS')

    def test_modified_output_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with Run('control','success',root=root) as run:
                run.command('literal',[sys.executable,'-c','print("original")'],cwd=root)
            path=run.path/'commands/001-literal/stdout.log';path.write_text('altered',encoding='utf-8')
            self.assertEqual(verify_run(run.path)['integrityStatus'],'FAIL')


if __name__=='__main__':unittest.main()
