"""Synthetic, fixed PostgreSQL Unix socket in a no-network CI container."""
import os
from pathlib import Path
import subprocess
import sys

from stream_replay import replay_fake

ROOT=Path("/tmp/nico-native-fixture")
ENV={"PATH":"/usr/lib/postgresql/18/bin:/usr/local/bin:/usr/bin:/bin","HOME":"/tmp",
     "PGHOST":str(ROOT/"socket"),"PGPORT":"6543","PGUSER":"postgres",
     "PGPASSFILE":"/dev/null","PGCONNECT_TIMEOUT":"5","PGREQUIREAUTH":"none"}
RUN="418a577fea014da581954380304aaaaa"

class Stage:
    def __init__(self, db):
        self.child=subprocess.Popen(
            ["/usr/local/bin/gosu","postgres","/usr/lib/postgresql/18/bin/pg_restore",
             "-w","--exit-on-error","--single-transaction","--no-owner","--no-acl","-d",db],
            stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=ENV)
    def stage(self, data):
        self.child.stdin.write(data)
    def commit(self):
        self.child.stdin.close()
        if self.child.wait(timeout=20):
            raise ValueError("synthetic pg_restore failure")
    def rollback(self):
        # Withhold EOF until the staged client is stopped. Its target stays
        # inaccessible and is discarded no matter what the child reported.
        if self.child.poll() is None:
            self.child.terminate()
            try:self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.child.kill()
                self.child.wait(timeout=3)
        try:self.child.stdin.close()
        except BrokenPipeError:pass

def main():
    if os.environ.get("NICO_CI_FIXTURE_MODE")!="github-synthetic-no-network" or os.environ.get("RAILWAY_SERVICE_ID"):
        return 2
    if sys.argv[1:] not in (["pass"],["mutate"]):
        return 2
    fault=sys.argv[1]=="mutate"
    loc=ROOT/"sealed"
    calls=[]
    def stage():
        if fault:
            p=sorted(loc.glob("part-*.cms"))[-1]
            old=p.read_bytes()
            p.write_bytes(old[:-1]+bytes([old[-1]^1]))
        sink=Stage("nico_fixture_failed" if fault else "nico_fixture_recovered")
        calls.append(sink)
        return sink
    try:
        proof=replay_fake(loc,run=RUN,certificate=ROOT/"recv.cert",recipient_key=ROOT/"recv.key",
                          signer_pub=ROOT/"sender.pub",sink_factory=stage)
    except Exception as exc:
        if fault and calls and type(exc) is ValueError and str(exc)=="ciphertext mismatch":
            print("SYNTHETIC_STREAM_CHANGED_ABORTED")
            return 0
        print("SYNTHETIC_STREAM_FAILED type="+type(exc).__name__)
        return 1
    if fault:return 1
    print("SYNTHETIC_STREAM_RESTORED plaintext_sha256="+proof["plaintext_sha256"]+
          " bytes="+str(proof["plaintext_bytes"])+" gate_eligible=false")
    return 0

if __name__=="__main__":raise SystemExit(main())
