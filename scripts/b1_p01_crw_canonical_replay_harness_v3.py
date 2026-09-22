from pathlib import Path

source = Path(__file__).with_name('b1_p01_crw_canonical_replay_harness_v1.py').read_text(encoding='utf-8')
old_identity = "if hashlib.sha1(w.read_bytes()).hexdigest()!=WORKLOAD:raise RuntimeError('canonical workload mismatch')"
new_identity = "raw=w.read_bytes(); git_blob=b'blob '+str(len(raw)).encode()+b'\\0'+raw\n    if hashlib.sha1(git_blob).hexdigest()!=WORKLOAD:raise RuntimeError('canonical workload mismatch')"
if old_identity not in source:
    raise SystemExit('v1 workload identity check not found')
source = source.replace(old_identity, new_identity, 1)
old_wait = "for _ in range(300):"
new_wait = "for _ in range(1440):"
if old_wait not in source:
    raise SystemExit('v1 rendezvous wait loop not found')
source = source.replace(old_wait, new_wait, 1)
exec(compile(source, 'b1_p01_crw_canonical_replay_harness_v3.py', 'exec'), {'__name__': '__main__', '__file__': __file__})
