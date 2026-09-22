from pathlib import Path

source = Path(__file__).with_name('b1_p01_crw_canonical_replay_harness_v1.py').read_text(encoding='utf-8')
old = "if hashlib.sha1(w.read_bytes()).hexdigest()!=WORKLOAD:raise RuntimeError('canonical workload mismatch')"
new = "raw=w.read_bytes(); git_blob=b'blob '+str(len(raw)).encode()+b'\\0'+raw\n    if hashlib.sha1(git_blob).hexdigest()!=WORKLOAD:raise RuntimeError('canonical workload mismatch')"
if old not in source:
    raise SystemExit('v1 workload identity check not found')
source = source.replace(old, new, 1)
exec(compile(source, 'b1_p01_crw_canonical_replay_harness_v2.py', 'exec'), {'__name__': '__main__', '__file__': __file__})
