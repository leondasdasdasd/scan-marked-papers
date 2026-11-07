"""Virtual-clock checks execute the installed engine against local HTTP fixtures."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import paperflow
from test_workflow import TESTS

class WaitEfficiencyTests(unittest.TestCase):
    def test_only_known_updating_status_has_bounded_read_recovery(self):
        extra=r'''
(async()=>{
 const originalPerformance=global.performance,originalTimeout=global.setTimeout;
 let now=0;global.performance={now:()=>now};global.setTimeout=(fn,delay)=>{now+=delay;fn();};
 try{
  for(const mode of ['once','always','other503','deadline']){
   now=0;const w=world(),old=global.fetch;let reads=0;
   global.fetch=async(path,o)=>{
    if(path.endsWith('/analysis/status')){
     reads++;
     if(mode!=='once'||reads===1){w.trace.push([o.method,path]);return {ok:false,status:503,json:async()=>({detail:mode==='other503'?'Other unavailable reason':'分析状态正在更新，请稍后重试'})};}
     w.finish();w.tasks={analysis:{status:'paused'}};
    }
    return old(path,o);
   };
   const d=await main(input('run',{timeout:mode==='deadline'?1:30,interval:2,observe_analysis:true}));
   assert(w.trace.every(([method])=>method==='GET'));
   if(mode==='once'){assert(d.ok);assert.equal(d.result.outcome,'stopped_readonly');assert.equal(reads,2);assert.equal(now,2000);}
   else{assert(!d.ok);assert.equal(d.error.code,mode==='other503'?'api_failed':'analysis_status_updating');
    assert.equal(reads,mode==='always'?3:1);assert.equal(now,mode==='always'?4000:mode==='deadline'?1000:0);}
  }
  console.log(JSON.stringify({known503_read_recovery:true,exhausted_requests:3,unknown503_requests:1,writes:0}));
 }finally{global.performance=originalPerformance;global.setTimeout=originalTimeout;}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
'''
        js='const SOURCE='+json.dumps(paperflow.source())+';\n'+TESTS.split('(async()=>{let failed=0;')[0]+extra
        proc=subprocess.run(['node','-'],input=js,text=True,capture_output=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        print(proc.stdout,end='')

    def test_waiting_reuses_headers_backs_off_and_preserves_boundaries(self):
        extra=r'''
(async()=>{
 const originalPerformance=global.performance,originalTimeout=global.setTimeout;
 let now=0,delays=[];
 global.performance={now:()=>now};global.setTimeout=(fn,delay)=>{delays.push(delay);now+=delay;fn();};
 try{
  let w=world();w.a.status='generating';
  let d=await main(input('run',{timeout:60,interval:5,observe_analysis:true}));
  assert.equal(d.result.outcome,'waiting');assert.equal(now,60000);
  assert(w.trace.every(([method,path])=>method==='GET'&&(/task-control|imports\?|analysis\/status/.test(path))));
  assert(delays.length<12);assert(Math.max(...delays)<=15000);
  const stableStatusReads=w.trace.filter(([,p])=>p.endsWith('/analysis/status')).length;
  now=0;delays=[];w=world();w.a.status='generating';const old=global.fetch;let statuses=0;
  global.fetch=async(path,o)=>{if(path.endsWith('/analysis/status')&&++statuses===2){w.finish();w.tasks={analysis:{status:'stopped'}};}return old(path,o);};
  d=await main(input('run',{timeout:60,observe_analysis:true}));
  assert.equal(d.result.outcome,'stopped_readonly');assert(w.trace.every(([m])=>m==='GET'));
  now=0;delays=[];w=world();w.a.status='generating';const previous=global.fetch;statuses=0;
  global.fetch=async(path,o)=>{if(path.endsWith('/analysis/status')&&++statuses===2)w.finish();return previous(path,o);};
  w.checkPolicy=()=>({ready:false,status:'preparing',issues:[{code:'MEDIA_CHECK_PENDING',severity:'pending'}]});
  w.progressQueue=['running'];
  // Active media fixture remains running until this shared budget is consumed.
  const fetch2=global.fetch;global.fetch=async(path,o)=>path.endsWith('/lesson-practice/progress')?reply({preparation:{status:'running'}}):fetch2(path,o);
  d=await main(input('run',{timeout:3,interval:2}));
  assert.equal(d.result.outcome,'waiting');assert.equal(d.result.waiting_for,'media');assert.equal(now,3000);
  assert.equal(w.media,0);assert(!d.result.ready);
  console.log(JSON.stringify({stable_status_reads:stableStatusReads,legacy_fixed_interval_reads:13,guard_checks_preserved:true,shared_deadline_ms:now}));
 }finally{global.performance=originalPerformance;global.setTimeout=originalTimeout;}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
'''
        js='const SOURCE='+json.dumps(paperflow.source())+';\n'+TESTS.split('(async()=>{let failed=0;')[0]+extra
        proc=subprocess.run(['node','-'],input=js,text=True,capture_output=True,timeout=15)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        print(proc.stdout,end='')

if __name__=='__main__':unittest.main()
