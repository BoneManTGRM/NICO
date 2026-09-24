from copy import deepcopy
import gzip,hashlib
from nico.assessment_cpp_configure_first_projection import _read_artifact,project_configure_first_record
from nico.assessment_worker_jobs import JobIdentity,_digest

def identity():
    return JobIdentity("c","p","r","scan","owner/repo","a"*40,"b"*64,"c"*40)

class Store:
    def __init__(self,raw,key):
        self.raw=raw; self.key=key
    def get(self,artifact_id,limit):
        compressed=gzip.compress(self.raw,mtime=0)
        return {"binding":{"run_id":"r","scan_id":"scan","customer_id":"c","project_id":"p",
            "repository":"owner/repo","commit_sha":"a"*40,"scanner_name":"cppcheck:"+self.key},
            "sha256":hashlib.sha256(self.raw).hexdigest(),"gzip_sha256":hashlib.sha256(compressed).hexdigest(),
            "compressed_bytes":len(compressed),"compressed":compressed}

def ref(raw,key):
    compressed=gzip.compress(raw,mtime=0)
    return {"artifact_id":"scanartifact_"+"d"*64,"key":key,"sha256":hashlib.sha256(raw).hexdigest(),
        "gzip_sha256":hashlib.sha256(compressed).hexdigest(),"retained_bytes":len(raw),
        "gzip_bytes":len(compressed),"storage_backend":"postgres"}

def test_artifact_read_rebinds_exact_job_and_hashes():
    raw=b'{"owned":true}'; key="project-static-evidence"
    assert _read_artifact(Store(raw,key),identity(),ref(raw,key),key)==raw

def test_projection_cannot_turn_incomplete_execution_into_success():
    record={"status":"failed","completed":False}
    receipt={"native":{"complete_execution":False}}
    assert project_configure_first_record(record,identity(),{},receipt,{"analysis":{"complete":False}})==record

def test_projection_preserves_full_canonical_finding_population():
    ident=identity(); finding={"rule_id":"owned","path":"src/a.cpp","line":1,"column":1,
        "context_id":"e"*64,"source_sha256":"f"*64,"classification":"review_required_candidate"}
    record={"status":"partial","completed":False,"verified_complete":False,"verified_for_this_report":False,
        "execution_observed_for_this_report":True,"returncode_valid":True,"findings":[],"finding_count":1,
        "reason":"pending","canonical_findings_projected":False,"cppcheck_source_coverage":{},
        "worker_provenance":{}}
    receipt={"configuration_sha256":"1"*64,"target_hashes":{"src/a.cpp":"f"*64},
        "native":{"complete_execution":True,"compilation_database_sha256":"2"*64,
            "artifacts":{"project-static-evidence":{"artifact_id":"scanartifact_"+"3"*64}}}}
    reconstruction={"analysis":{"complete":True,"required_contexts":["e"*64],"analyzed_contexts":["e"*64],
        "findings":[finding],"limitations":[],"native_evidence_sha256":"4"*64},
        "compiler":{"native_evidence_sha256":"5"*64}}
    out=project_configure_first_record(record,ident,{},receipt,reconstruction)
    assert out["completed"] and out["verified_complete"] and out["canonical_findings_projected"]
    assert out["finding_count"]==len(out["findings"])==1
    assert out["findings"][0]["commit_sha"]=="a"*40
