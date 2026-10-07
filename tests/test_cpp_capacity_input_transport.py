"""Owned byte-only transport controls; never call a provider or native tool."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest.mock import patch
import zipfile

PATH = Path(__file__).parents[1] / 'scripts/cpp_private_diagnostic_inputs.py'
SPEC = importlib.util.spec_from_file_location('owned_capacity_transport', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Controls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.scratch = Path(self.temp.name).resolve() / 'scratch'
        self.scratch.mkdir(mode=0o700)
        (self.scratch / 'host').mkdir(mode=0o700)
        self.run = {'id': MODULE.CAPACITY_INPUT_RUN, 'path': MODULE.CAPACITY_INPUT_WORKFLOW,
            'head_branch': MODULE.IMAGE_BRANCH, 'event': 'push', 'status': 'completed', 'conclusion': 'success',
            'run_attempt': 1, 'head_sha': MODULE.CAPACITY_INPUT_HEAD,
            'repository': {'id':1282576027}, 'head_repository': {'id':1282576027}}
        self.bodies = {key:('owned-' + key + '\n').encode() for key in ('environment','primary','fallback')}
        self.members = {key:{'path':'artifacts/owned-' + key + '.json', 'bytes':len(raw),
            'sha256':MODULE.sha(raw)} for key,raw in self.bodies.items()}
        self.make_zip()
        self.artifact = {'id':11501588664, 'name':MODULE.CAPACITY_INPUT_ARTIFACT['name'],
            'expired':False, 'expires_at':'2040-01-01T00:00:00Z', 'size_in_bytes':len(self.zip_bytes),
            'digest':'sha256:' + MODULE.sha(self.zip_bytes), 'workflow_run':{'id':self.run['id'],
                'head_sha':self.run['head_sha'], 'head_branch':self.run['head_branch'],
                'repository_id':1282576027, 'head_repository_id':1282576027},
            'archive_download_url':MODULE.API + '/repos/' + MODULE.REPOSITORY + '/actions/artifacts/11501588664/zip'}
        self.expected = dict(MODULE.CAPACITY_INPUT_ARTIFACT, bytes=len(self.zip_bytes),sha256=MODULE.sha(self.zip_bytes))
        self.records = {'status':'PRIVATE_RETAINED_INPUTS_PREPARED','actual_observed_scratch_peak_bytes':0}
        MODULE.write_private(self.scratch / 'host/preparation.json',self.records)
        self.calls = []
        def read(path):
            self.calls.append(('GET',path))
            if path.endswith('/attempts/1'):
                return copy.deepcopy(self.run)
            return {'total_count':1,'artifacts':[copy.deepcopy(self.artifact)]}
        def download(artifact,path,maximum):
            self.calls.append(('download',artifact['id']))
            path.write_bytes(self.zip_bytes)
            path.chmod(0o600)
            return {'bytes':len(self.zip_bytes),'sha256':MODULE.sha(self.zip_bytes),
                    'provider_raw_zip_verified':True,'wall_ms':0.1}
        self.client = types.SimpleNamespace(json=read,download=download)
        for name,value in [('CAPACITY_INPUT_ARTIFACT',self.expected),('CAPACITY_INPUT_MEMBERS',self.members)]:
            p=patch.object(MODULE,name,value);p.start();self.addCleanup(p.stop)

    def make_zip(self,extra=None):
        buffer=io.BytesIO()
        with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for key,row in self.members.items():
                archive.writestr(row['path'],self.bodies[key])
            if extra:
                archive.writestr(extra,b'')
        self.zip_bytes=buffer.getvalue()

    def execute(self):
        return MODULE.prepare_capacity_inputs(self.client,self.scratch,self.records,4096)

    def reject(self,code):
        with self.assertRaisesRegex(MODULE.PreparationError,'^' + code + '$'):
            self.execute()

    def test_whole_verified_three_members_are_retained_privately_and_source_scope_is_explicit(self):
        result=self.execute()
        for key,raw in self.bodies.items():
            p=self.scratch / 'host/capacity-sample' / (key + '.json')
            self.assertEqual(p.read_bytes(),raw)
            self.assertEqual(p.stat().st_mode & 0o077,0)
        self.assertFalse(result['workflow_head_is_executed_worker_source_claimed'])
        self.assertFalse(result['native_execution'])
        self.assertEqual(result['preflight']['additional_bound_bytes'],len(self.zip_bytes) + sum(len(x) for x in self.bodies.values()) + MODULE.MAX_META)
        self.assertEqual(json.loads((self.scratch / 'host/preparation.json').read_bytes())['capacity_sample'],result)
        self.assertEqual(MODULE.MAX_SCRATCH,6 * 1024**3)

    def test_wrong_workflow_head_or_branch_or_conclusion_rejects_before_download(self):
        for key,value in [('head_sha','0' * 40),('head_branch','main'),('conclusion','failure')]:
            original=self.run[key];self.run[key]=value
            self.reject('capacity_exact_run_binding');self.run[key]=original
        self.assertFalse(any(row[0]=='download' for row in self.calls))

    def test_foreign_repository_run_rejects(self):
        self.run['repository']['id']=42
        self.reject('capacity_exact_run_binding')

    def test_same_name_wrong_artifact_id_or_digest_rejects(self):
        self.artifact['id']=11501588665
        self.artifact['archive_download_url']=self.artifact['archive_download_url'].replace('11501588664','11501588665')
        self.reject('capacity_exact_artifact_binding')
        self.artifact['id']=11501588664
        self.artifact['archive_download_url']=self.artifact['archive_download_url'].replace('11501588665','11501588664')
        self.artifact['digest']='sha256:' + '0' * 64
        self.reject('capacity_exact_artifact_binding')

    def test_expired_artifact_rejects(self):
        self.artifact['expires_at']='2000-01-01T00:00:00Z'
        self.reject('artifact_expired')

    def test_provider_artifact_source_mismatch_rejects(self):
        self.artifact['workflow_run']['head_sha']='0' * 40
        self.reject('artifact_run_binding')

    def test_client_cannot_bypass_whole_archive_anchor(self):
        self.zip_bytes=bytes([self.zip_bytes[0]^1]) + self.zip_bytes[1:]
        self.reject('capacity_whole_archive_anchor')

    def test_exact_member_hash_and_population_are_required(self):
        self.members['primary']['sha256']='0' * 64
        self.reject('capacity_exact_decoded_members')

    def test_additional_zip_member_is_rejected(self):
        self.make_zip(extra='artifacts/extra.json')
        self.expected.update(bytes=len(self.zip_bytes),sha256=MODULE.sha(self.zip_bytes))
        self.artifact.update(size_in_bytes=len(self.zip_bytes),digest='sha256:' + MODULE.sha(self.zip_bytes))
        self.reject('decoded_member_population')

    def test_unprepared_or_public_or_duplicate_destination_rejects(self):
        self.records['status']='UNPROVEN';self.reject('capacity_existing_preparation_required')
        self.records['status']='PRIVATE_RETAINED_INPUTS_PREPARED'
        self.scratch.chmod(0o755);self.reject('capacity_private_scratch');self.scratch.chmod(0o700)
        (self.scratch / 'host/capacity-sample').mkdir(mode=0o700)
        self.reject('capacity_new_input_paths')

    def test_existing_transient_and_free_disk_guards_are_preserved(self):
        with patch.object(MODULE,'MAX_SCRATCH',1):
            self.reject('transient_scratch_guard')
        with patch.object(MODULE.shutil,'disk_usage',return_value=types.SimpleNamespace(free=1)):
            self.reject('host_free_disk_guard')

    def test_existing_preparation_fields_and_private_mode_survive_atomic_update(self):
        self.records['source']={'commit':'a' * 40,'tree':'b' * 40}
        path=self.scratch / 'host/preparation.json'
        path.unlink();MODULE.write_private(path,self.records)
        original=copy.deepcopy(self.records)
        self.execute()
        actual=json.loads(path.read_bytes())
        self.assertEqual(actual['source'],original['source'])
        self.assertEqual(actual['status'],original['status'])
        self.assertEqual(path.stat().st_mode & 0o077,0)
        self.assertFalse((self.scratch / 'host/capacity-preparation.json.tmp').exists())

    def test_corrupt_or_public_original_preparation_is_rejected_before_download(self):
        path=self.scratch / 'host/preparation.json'
        path.write_bytes(b'{}')
        self.reject('capacity_original_preparation_bytes')
        path.chmod(0o755)
        self.reject('capacity_original_private_preparation')
        self.assertEqual(self.calls,[])


if __name__ == '__main__':
    unittest.main()
