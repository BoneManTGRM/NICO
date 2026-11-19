"""Fake-only local rehearsal of authenticated two-pass replay. No database or network."""
import hashlib
from pathlib import Path
import os
import re
import stat
import subprocess

MAX_FRAME = 1048576
ENV = {"PATH":"/usr/bin:/bin","LC_ALL":"C"}


def _openssl(*args, data=None):
    r=subprocess.run(["/usr/bin/openssl",*args],input=data,stdout=subprocess.PIPE,
                     stderr=subprocess.DEVNULL,env=ENV,timeout=8,check=True)
    return r.stdout


def _read(fd, name, limit):
    h=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
    with os.fdopen(h,"rb") as f:
        s=os.fstat(f.fileno())
        if not stat.S_ISREG(s.st_mode) or not 0<s.st_size<=limit:
            raise ValueError("bounded regular fixture file required")
        b=f.read(limit+1)
        p=os.fstat(f.fileno())
        if len(b)!=s.st_size or p.st_size!=s.st_size or p.st_mtime_ns!=s.st_mtime_ns:
            raise ValueError("fixture changed")
        return b


def replay_fake(directory, *, run, certificate, recipient_key, signer_pub, sink_factory):
    if not re.fullmatch("[a-f0-9]{32}",run):
        raise ValueError("fixture run")
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        manifest=_read(fd,"manifest.complete",2048)
        sig=_read(fd,"manifest.sig",64)
        if len(sig)!=64:
            raise ValueError("signature size")
        # Keep both bounded input files open on the verified bytes in memory;
        # no second unverified read of the source path to verify its signature.
        import tempfile
        with tempfile.TemporaryDirectory(prefix="nico-fake-verify-") as d:
            p=Path(d)
            (p/"msg").write_bytes(manifest)
            (p/"sig").write_bytes(sig)
            _openssl("pkeyutl","-verify","-rawin","-pubin","-inkey",str(signer_pub),
                     "-in",str(p/"msg"),"-sigfile",str(p/"sig"))
        header, fingerprint, count, *lines=manifest.decode("ascii",errors="strict").splitlines()
        if header!="NICO-SYNTHETIC-FRAME-V1 "+run or not re.fullmatch("[1-8]",count) or len(lines)!=int(count):
            raise ValueError("signed fixture manifest")
        if fingerprint!=hashlib.sha256(_openssl("x509","-in",str(certificate),"-outform","DER")).hexdigest():
            raise ValueError("recipient fingerprint")
        entries=[]
        for i,line in enumerate(lines):
            row=line.split(" ")
            if len(row)!=3:
                raise ValueError("manifest row count")
            name,n,digest=row
            if name!=f"part-{i:04}.cms" or not re.fullmatch("[1-9][0-9]{0,6}",n) or not re.fullmatch("[a-f0-9]{64}",digest):
                raise ValueError("manifest row")
            if int(n)>MAX_FRAME+4096:
                raise ValueError("frame size bound")
            entries.append((name,int(n),digest))
        if {e for e in os.listdir(fd) if e.startswith("part-")}!={name for name,_,_ in entries}:
            raise ValueError("fixture frame set")

        def read_frames(sink=None):
            h=hashlib.sha256()
            total=0
            for i,(name,n,digest) in enumerate(entries):
                cipher=_read(fd,name,n)
                if len(cipher)!=n or hashlib.sha256(cipher).hexdigest()!=digest:
                    raise ValueError("ciphertext mismatch")
                # Authenticated decryption must exit successfully before a
                # single byte from this frame is given to the staged sink.
                plain=_openssl("cms","-decrypt","-binary","-inform","DER",
                               "-recip",str(certificate),"-inkey",str(recipient_key),data=cipher)
                if not 0<len(plain)<=MAX_FRAME or i<len(entries)-1 and len(plain)!=MAX_FRAME:
                    raise ValueError("plaintext frame bound")
                total+=len(plain)
                h.update(plain)
                if sink is not None:
                    sink.stage(plain)
            return total,h.hexdigest()

        expected=read_frames()
        sink=sink_factory()
        try:
            if read_frames(sink)!=expected:
                raise ValueError("replay digest mismatch")
            sink.commit()
        except BaseException:
            sink.rollback()
            raise
        return {"plaintext_bytes":expected[0],"plaintext_sha256":expected[1],
                "synthetic_only":True,"gate_eligible":False}
    finally:
        os.close(fd)
