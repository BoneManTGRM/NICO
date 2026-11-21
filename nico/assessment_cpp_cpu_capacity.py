"""Bounded compiler-collector CPU observations; never qualification evidence.

Observe only this collector thread. Visible ceilings do not prove delivered CPU
or expose host/hidden ancestor capacity. No command line entry point is provided.
"""
import os
import posixpath
import re
import stat
from fractions import Fraction

PROC_CGROUP='/proc/thread-self/cgroup'
PROC_MOUNTS='/proc/thread-self/mountinfo'
ROOT='/sys/fs/cgroup'
MAX_DEPTH=64
MAX_INTEGER=10**12


def _path(value):
    if not isinstance(value,str) or not value.startswith('/') or '\\' in value:
        raise ValueError('invalid_path')
    if len(value)>4096 or any(ord(c)<32 or ord(c)>126 for c in value):raise ValueError('invalid_path')
    if value!='/' and (value.endswith('/') or any(p in ('','.','..') for p in value[1:].split('/'))):raise ValueError('invalid_path')
    return value


def _mount_path(value):
    # Decode only mountinfo's documented octal escapes, then validate path bytes.
    value=re.sub(r'\\(040|011|012|134)',lambda m:chr(int(m[1],8)),value)
    return _path(value)


def _inside(path,root):return path==root or path.startswith(root.rstrip('/')+'/')


def read_trusted(path,limit):
    """No arbitrary file reads: two fixed self-proc files or CPU-controller leaves.

    No-follow descriptor traversal below the fixed cgroup root rejects symlinks.
    /proc/thread-self is the kernel's trusted calling-thread selector, never input.
    """
    if path in (PROC_CGROUP,PROC_MOUNTS):
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    else:
        _path(path)
        if not _inside(path,ROOT) or posixpath.basename(path) not in ('cpu.max','cpu.cfs_quota_us','cpu.cfs_period_us'):
            raise ValueError('read_not_allowed')
        fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            parts=path.strip('/').split('/')
            for part in parts[:-1]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=child
            leaf=os.open(parts[-1],os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        finally:os.close(fd)
        fd=leaf
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise ValueError('read_not_regular')
        with os.fdopen(fd,'rb',closefd=False) as stream:raw=stream.read(limit+1)
        if len(raw)>limit:raise ValueError('read_bound')
        return raw
    finally:os.close(fd)


def _text(reader,path,limit):
    raw=reader(path,limit)
    if type(raw) is not bytes or len(raw)>limit:raise ValueError('read_bound')
    return raw.decode('ascii')


def _integer(raw,*,unlimited=False):
    if unlimited and raw in ('max','-1'):return None
    if not re.fullmatch(r'[0-9]{1,13}',raw):raise ValueError('quota_invalid')
    value=int(raw)
    if not 1<=value<=MAX_INTEGER:raise ValueError('quota_invalid')
    return value


def _mapping(cgroups,mountinfo):
    memberships={}
    if len(cgroups.splitlines())>128 or len(mountinfo.splitlines())>2048:raise ValueError('metadata_bound')
    for line in cgroups.splitlines():
        parts=line.split(':',2)
        if len(parts)!=3 or not re.fullmatch(r'[0-9]+',parts[0]):raise ValueError('membership_invalid')
        controllers=parts[1].split(',');version=2 if parts[0]=='0' and parts[1]=='' else 1 if 'cpu' in controllers else None
        if version is not None:
            if version in memberships:raise ValueError('membership_ambiguous')
            memberships[version]=_path(parts[2])
    matches=[]
    for line in mountinfo.splitlines():
        cols=line.split();sep=cols.index('-') if '-' in cols else -1
        if sep<6 or len(cols)<sep+4:raise ValueError('mount_invalid')
        fs=cols[sep+1];version=2 if fs=='cgroup2' else 1 if fs=='cgroup' and 'cpu' in cols[sep+3].split(',') else None
        if version is None or version not in memberships:continue
        root=_mount_path(cols[3]);mount=_mount_path(cols[4]);member=memberships[version]
        if not _inside(mount,ROOT):continue
        if not _inside(member,root):continue
        relative=member[len(root):] if root!='/' else member
        leaf=mount.rstrip('/')+'/'+relative.lstrip('/') if relative.strip('/') else mount
        _path(leaf)
        if not _inside(leaf,mount):raise ValueError('mount_escape')
        matches.append((version,root,mount,leaf))
    # Hybrid or aliased mounts need additional proof; never guess a hierarchy.
    if len(matches)!=1:raise ValueError('mapping_unavailable')
    return matches[0]


def observe(*,reader=read_trusted,affinity=lambda:os.sched_getaffinity(0),cpu_count=os.cpu_count,workers=4):
    if type(workers) is not int or not 1<=workers<=256:raise ValueError('configured_workers_invalid')
    result={'schema':'nico.cpp-compiler-cpu-capacity.v1','observation_scope':'collector_thread',
        'observation_consistency':'sequential_unverified',
        'configured_workers':workers,'affinity_count':None,'os_cpu_count':None,
        'cgroup_version':None,'visible_levels_read':0,'visible_ancestry_complete':False,
        'mount_root_hides_ancestors':None,'global_hierarchy_visibility':'unproven',
        'visible_quota_state':'unknown','visible_quota_numerator':None,'visible_quota_denominator':None,
        'visible_ceiling_numerator':None,'visible_ceiling_denominator':None,
        'effective_capacity_state':'unknown','delivered_cpu_measured':False,
        'qualification_credit':False,'errors':[]}
    errors=result['errors']
    try:
        allowed=affinity()
        if not isinstance(allowed,(set,frozenset)) or not 1<=len(allowed)<=1048576 or any(type(v) is not int or v<0 for v in allowed):raise ValueError()
        result['affinity_count']=len(allowed)
    except (OSError,ValueError,TypeError,AttributeError):errors.append('affinity_unavailable')
    try:
        value=cpu_count()
        if type(value) is not int or not 1<=value<=1048576:raise ValueError()
        result['os_cpu_count']=value
    except (OSError,ValueError,TypeError,AttributeError):errors.append('os_count_unavailable')
    quotas=[];unlimited=0;walk_failed=False
    try:
        version,root,mount,current=_mapping(_text(reader,PROC_CGROUP,8192),_text(reader,PROC_MOUNTS,131072))
        result['cgroup_version']=version;result['mount_root_hides_ancestors']=root!='/'
        for depth in range(MAX_DEPTH):
            try:
                if version==2:
                    fields=_text(reader,current+'/cpu.max',128).split()
                    if len(fields)!=2 or fields[0]=='-1':raise ValueError()
                    quota=_integer(fields[0],unlimited=True);period=_integer(fields[1])
                else:
                    q=_text(reader,current+'/cpu.cfs_quota_us',128).strip()
                    if q=='max':raise ValueError()
                    quota=_integer(q,unlimited=True);period=_integer(_text(reader,current+'/cpu.cfs_period_us',128).strip())
                result['visible_levels_read']+=1
                if quota is None:unlimited+=1
                else:quotas.append(Fraction(quota,period))
            except (OSError,ValueError,UnicodeError,TypeError):
                walk_failed=True
                if 'quota_unreadable_or_invalid' not in errors:errors.append('quota_unreadable_or_invalid')
            if current==mount:
                result['visible_ancestry_complete']=not walk_failed;break
            current=posixpath.dirname(current)
        else:errors.append('ancestor_depth_bound')
    except (OSError,ValueError,UnicodeError,TypeError):errors.append('cgroup_mapping_unavailable')
    ceiling=Fraction(result['affinity_count'],1) if result['affinity_count'] is not None else None
    if quotas:
        visible=min(quotas);result['visible_quota_state']='finite_observed_upper_bound'
        result['visible_quota_numerator']=visible.numerator;result['visible_quota_denominator']=visible.denominator
        ceiling=min(ceiling,visible) if ceiling is not None else visible
    elif result['visible_ancestry_complete'] and unlimited:
        result['visible_quota_state']='visible_unlimited_only'
    if ceiling is not None:
        result['visible_ceiling_numerator']=ceiling.numerator;result['visible_ceiling_denominator']=ceiling.denominator
    return result


ERRORS = frozenset({'affinity_unavailable','os_count_unavailable',
    'quota_unreadable_or_invalid','ancestor_depth_bound','cgroup_mapping_unavailable'})


def unavailable(state='unavailable'):
    return {'state':state,'effective_capacity_state':'unknown','qualification_credit':False}


def summarize(value):
    """Fresh fixed-vocabulary copy only; malformed observations convey no credit."""
    if value is None:return unavailable()
    if type(value) is not dict:return unavailable('invalid')
    if value in (unavailable(),unavailable('invalid')):return dict(value)
    fixed={'schema':'nico.cpp-compiler-cpu-capacity.v1','observation_scope':'collector_thread',
        'observation_consistency':'sequential_unverified','global_hierarchy_visibility':'unproven',
        'effective_capacity_state':'unknown','delivered_cpu_measured':False,'qualification_credit':False}
    numbers={'configured_workers':256,'affinity_count':1048576,'os_cpu_count':1048576,
        'visible_levels_read':MAX_DEPTH,'visible_quota_numerator':MAX_INTEGER,
        'visible_quota_denominator':MAX_INTEGER,'visible_ceiling_numerator':MAX_INTEGER,
        'visible_ceiling_denominator':MAX_INTEGER}
    nullable={'affinity_count','os_cpu_count','visible_quota_numerator','visible_quota_denominator',
        'visible_ceiling_numerator','visible_ceiling_denominator'}
    expected=set(fixed)|set(numbers)|{'cgroup_version','visible_ancestry_complete',
        'mount_root_hides_ancestors','visible_quota_state','errors'}
    if set(value)!=expected:return unavailable('invalid')
    if any(type(value[k]) is not type(v) or value[k]!=v for k,v in fixed.items()):return unavailable('invalid')
    for key,bound in numbers.items():
        n=value[key]
        if key in nullable and n is None:continue
        if type(n) is not int or not (0 if key=='visible_levels_read' else 1)<=n<=bound:return unavailable('invalid')
    if value['cgroup_version'] is not None and (type(value['cgroup_version']) is not int or value['cgroup_version'] not in (1,2)):return unavailable('invalid')
    if type(value['visible_ancestry_complete']) is not bool:return unavailable('invalid')
    if value['mount_root_hides_ancestors'] is not None and type(value['mount_root_hides_ancestors']) is not bool:return unavailable('invalid')
    errors=value['errors']
    if type(errors) is not list or len(errors)>len(ERRORS) or any(type(e) is not str or e not in ERRORS for e in errors) or len(set(errors))!=len(errors):return unavailable('invalid')
    state=value['visible_quota_state']
    if state not in ('unknown','finite_observed_upper_bound','visible_unlimited_only'):return unavailable('invalid')
    for prefix in ('visible_quota','visible_ceiling'):
        if (value[prefix+'_numerator'] is None)!=(value[prefix+'_denominator'] is None):return unavailable('invalid')
    if (state=='finite_observed_upper_bound')!=(value['visible_quota_numerator'] is not None):return unavailable('invalid')
    if state=='visible_unlimited_only' and not value['visible_ancestry_complete']:return unavailable('invalid')
    bounds=[]
    if value['affinity_count'] is not None:bounds.append(Fraction(value['affinity_count'],1))
    if value['visible_quota_numerator'] is not None:bounds.append(Fraction(value['visible_quota_numerator'],value['visible_quota_denominator']))
    ceiling=min(bounds) if bounds else None
    if (value['visible_ceiling_numerator'],value['visible_ceiling_denominator'])!=((ceiling.numerator,ceiling.denominator) if ceiling is not None else (None,None)):return unavailable('invalid')
    return {**value,'errors':list(errors)}


# Isolated interpreter in the analyst container has no repository imports.
import inspect
PROGRAM = ('import os, posixpath, re, stat\nfrom fractions import Fraction\n'
    + f'PROC_CGROUP={PROC_CGROUP!r}\nPROC_MOUNTS={PROC_MOUNTS!r}\nROOT={ROOT!r}\nMAX_DEPTH={MAX_DEPTH}\nMAX_INTEGER={MAX_INTEGER}\n'
    + '\n'.join(inspect.getsource(f) for f in (_path,_mount_path,_inside,read_trusted,_text,_integer,_mapping,observe)))
