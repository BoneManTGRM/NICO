import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from nico import assessment_cpp_cpu_capacity as c

MOUNT='36 25 0:32 {root} /sys/fs/cgroup rw,nosuid,nodev,noexec,relatime - cgroup2 cgroup rw\n'
def fixture(*,member='/parent/leaf',root='/',values=None,version=2):
    data={c.PROC_CGROUP:('0::'+member+'\n').encode(),c.PROC_MOUNTS:MOUNT.format(root=root).encode()}
    if version==1:
        data[c.PROC_CGROUP]=('2:cpu,cpuacct:'+member+'\n').encode()
        data[c.PROC_MOUNTS]=MOUNT.format(root=root).replace('cgroup2 cgroup rw','cgroup cgroup rw,cpu,cpuacct').encode()
    data.update(values or {})
    calls=[]
    def reader(path,limit):
        calls.append((path,limit))
        if path not in data:raise OSError('PRIVATE path and host detail')
        return data[path]
    return reader,calls

def v2(**kwargs):
    values={'/sys/fs/cgroup/parent/leaf/cpu.max':b'400000 100000', '/sys/fs/cgroup/parent/cpu.max':b'150000 100000','/sys/fs/cgroup/cpu.max':b'max 100000'}
    values.update(kwargs.pop('values',{}));return fixture(values=values,**kwargs)
def observe(reader,**kwargs):return c.observe(reader=reader,affinity=lambda:{1,3,5,7,9,11},cpu_count=lambda:64,**kwargs)
class Tests(unittest.TestCase):
 def test_observation_is_explicitly_sequential_not_atomic(self):
    r,_=v2();out=observe(r);self.assertEqual(out['observation_consistency'],'sequential_unverified');self.assertEqual(out['effective_capacity_state'],'unknown')
 def test_legitimate_v2_root_without_cpu_max_remains_incomplete(self):
    r,_=fixture(values={'/sys/fs/cgroup/parent/leaf/cpu.max':b'400000 100000','/sys/fs/cgroup/parent/cpu.max':b'200000 100000'})
    out=observe(r);self.assertEqual(out['visible_quota_numerator'],2);self.assertEqual(out['visible_levels_read'],2);self.assertFalse(out['visible_ancestry_complete']);self.assertEqual(out['effective_capacity_state'],'unknown');self.assertFalse(out['qualification_credit'])
 def test_tighter_ancestor_is_visible_fraction_not_delivered_capacity(self):
    r,calls=v2();out=observe(r);self.assertEqual((out['visible_quota_numerator'],out['visible_quota_denominator']),(3,2));self.assertEqual(out['visible_levels_read'],3);self.assertTrue(out['visible_ancestry_complete']);self.assertEqual(out['effective_capacity_state'],'unknown');self.assertFalse(out['delivered_cpu_measured'])
 def test_affinity_limits_ceiling_not_host_count(self):
    r,_=v2();out=c.observe(reader=r,affinity=lambda:{17},cpu_count=lambda:128);self.assertEqual(out['visible_ceiling_numerator'],1);self.assertEqual(out['os_cpu_count'],128)
 def test_unreadable_ancestor_retains_observed_upper_bound(self):
    r,_=fixture(values={'/sys/fs/cgroup/parent/leaf/cpu.max':b'400000 100000'});out=observe(r);self.assertEqual(out['visible_quota_numerator'],4);self.assertFalse(out['visible_ancestry_complete']);self.assertIn('quota_unreadable_or_invalid',out['errors'])
 def test_hidden_mount_root(self):
    r,_=fixture(member='/hidden/leaf',root='/hidden',values={'/sys/fs/cgroup/leaf/cpu.max':b'400000 100000','/sys/fs/cgroup/cpu.max':b'200000 100000'});out=observe(r);self.assertTrue(out['mount_root_hides_ancestors']);self.assertTrue(out['visible_ancestry_complete']);self.assertEqual(out['effective_capacity_state'],'unknown')
 def test_namespace_relative_mapping_is_not_guessed(self):
    r,calls=fixture(member='/',root='/hidden');out=observe(r);self.assertIsNone(out['cgroup_version']);self.assertEqual(len(calls),2)
 def test_v1_ancestors_and_unlimited(self):
    values={}
    for p,q in (('/parent/leaf','400000'),('/parent','125000'),('','-1')):
      values['/sys/fs/cgroup'+p+'/cpu.cfs_quota_us']=q.encode();values['/sys/fs/cgroup'+p+'/cpu.cfs_period_us']=b'100000'
    r,_=fixture(version=1,values=values);out=observe(r);self.assertEqual(out['cgroup_version'],1);self.assertEqual((out['visible_quota_numerator'],out['visible_quota_denominator']),(5,4))
 def test_all_visible_unlimited_is_still_unknown_effective(self):
    values={p:b'max 100000' for p in ('/sys/fs/cgroup/parent/leaf/cpu.max','/sys/fs/cgroup/parent/cpu.max','/sys/fs/cgroup/cpu.max')};r,_=fixture(values=values);out=observe(r);self.assertEqual(out['visible_quota_state'],'visible_unlimited_only');self.assertEqual(out['visible_ceiling_numerator'],6);self.assertEqual(out['effective_capacity_state'],'unknown')
 def test_invalid_quota_values(self):
    for raw in (b'-1 100000',b'-2 100000',b'0 100000',b'1 0',b'max -1',b'1.5 100000',b'1000000000001 1',b'9'*100+b' 1',b'1 2 3',b'\xff'):
      r,_=fixture(member='/',values={'/sys/fs/cgroup/cpu.max':raw});out=observe(r);self.assertEqual(out['visible_quota_state'],'unknown');self.assertIn('quota_unreadable_or_invalid',out['errors'])
 def test_v1_rejects_max(self):
    r,_=fixture(version=1,member='/',values={'/sys/fs/cgroup/cpu.cfs_quota_us':b'max','/sys/fs/cgroup/cpu.cfs_period_us':b'100000'});self.assertEqual(observe(r)['visible_quota_state'],'unknown')
 def test_metadata_path_traversal(self):
    for member in ('/a/../private','/a//private','/a/.','/../../etc','relative','/secret\npath'):
      r,calls=fixture(member=member);out=observe(r);self.assertIsNone(out['cgroup_version']);self.assertEqual(len(calls),2)
 def test_mount_cannot_redirect_to_arbitrary_files(self):
    r,calls=fixture();original=r
    def reader(path,limit):
      raw=original(path,limit);return raw.replace(b'/sys/fs/cgroup',b'/private') if path==c.PROC_MOUNTS else raw
    out=observe(reader);self.assertIsNone(out['cgroup_version']);self.assertEqual(len(calls),2)
 def test_depth_bound(self):
    member='/'+'/'.join(['x']*70);r,calls=fixture(member=member)
    def reader(path,limit):return r(path,limit) if path.startswith('/proc/') else b'100000 100000'
    out=observe(reader);self.assertEqual(out['visible_levels_read'],64);self.assertFalse(out['visible_ancestry_complete']);self.assertIn('ancestor_depth_bound',out['errors'])
 def test_metadata_bounds(self):
    out=observe(lambda p,n:b'x'*(n+1));self.assertEqual(out['cgroup_version'],None)
 def test_affinity_unavailable_never_uses_cpu_count_as_ceiling(self):
    r,_=fixture()
    out=c.observe(reader=r,affinity=lambda:None,cpu_count=lambda:128);self.assertIsNone(out['visible_ceiling_numerator']);self.assertEqual(out['os_cpu_count'],128)
 def test_booleans_are_not_counts(self):
    r,_=fixture();out=c.observe(reader=r,affinity=lambda:{True},cpu_count=lambda:True);self.assertIsNone(out['affinity_count']);self.assertIsNone(out['os_cpu_count'])
 def test_output_contains_no_paths_raw_data_or_details(self):
    r,_=fixture(member='/PRIVATE_SECRET');out=observe(r);raw=json.dumps(out);self.assertNotIn('PRIVATE',raw);self.assertNotIn('/proc',raw);self.assertNotIn('/sys',raw);self.assertFalse(out['qualification_credit']);self.assertEqual(out['observation_scope'],'collector_thread');self.assertLess(len(raw),2048)
 def test_configured_workers_are_not_measured_capacity(self):
    r,_=v2();out=observe(r,workers=4);self.assertEqual(out['configured_workers'],4);self.assertEqual(out['visible_ceiling_numerator'],3)
 def test_invalid_worker_input(self):
    for value in (True,0,-1,257,'4'):
      with self.assertRaises(ValueError):observe(lambda p,n:b'',workers=value)
 def test_ambiguous_mounts(self):
    r,_=v2()
    def reader(p,n):
      raw=r(p,n);return raw+raw if p==c.PROC_MOUNTS else raw
    self.assertIsNone(observe(reader)['cgroup_version'])
 def test_reader_rejects_arbitrary_path_before_open(self):
    with patch.object(c.os,'open',side_effect=AssertionError('must not open')):
      with self.assertRaises(ValueError):c.read_trusted('/etc/passwd',128)
 def test_reader_symlink_leaf_and_parent_denied_owned_only(self):
    with tempfile.TemporaryDirectory() as tmp:
      root=Path(tmp)/'cgroup';root.mkdir();secret=Path(tmp)/'owned';secret.write_text('100000 100000')
      (root/'cpu.max').symlink_to(secret)
      with patch.object(c,'ROOT',str(root)):
       with self.assertRaises(OSError):c.read_trusted(str(root/'cpu.max'),128)
      (root/'sub').symlink_to(tmp,target_is_directory=True)
      with patch.object(c,'ROOT',str(root)):
       with self.assertRaises(OSError):c.read_trusted(str(root/'sub'/'cpu.max'),128)
 def test_reader_bounded_owned_regular_file(self):
    with tempfile.TemporaryDirectory() as tmp:
      root=Path(tmp)/'cgroup';root.mkdir();(root/'cpu.max').write_bytes(b'x'*129)
      with patch.object(c,'ROOT',str(root)):
       with self.assertRaises(ValueError):c.read_trusted(str(root/'cpu.max'),128)
if __name__=='__main__':unittest.main()
