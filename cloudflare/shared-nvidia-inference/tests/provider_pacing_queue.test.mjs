import test from "node:test";
import assert from "node:assert/strict";
import {NvidiaProviderPacingQueue,MIN_PROVIDER_SPACING_MS,RATE_LIMITED_SPACING_MS,
        DEFAULT_SOFT_RPM,parsedRetryAfterMs} from "../src/provider_pacing_queue.js";
const URL="https://integrate.api.nvidia.com/v1/chat/completions";
const POST={method:"POST",redirect:"manual"};

test("serialized request starts never exceed the operator's 3 per second",async()=>{
  let clock=0;
  const starts=[];
  const pacer=new NvidiaProviderPacingQueue({
    providerFetch:async()=>{starts.push(clock);return{status:200};},
    now:()=>clock,sleep:async delay=>{clock+=delay;},
  });
  await Promise.all(Array.from({length:10},()=>pacer.fetch(URL,POST)));
  assert.equal(starts.length,10);
  for(let i=1;i<starts.length;i++)
    assert(starts[i]-starts[i-1]>=MIN_PROVIDER_SPACING_MS);
  assert.deepEqual(starts.slice(0,3),[0,334,668]);
  assert(starts[3]>=1500&&starts[3]<=1502); // ceil on fractional token refill
  // A rolling one-second window contains at most three actual request starts.
  for(let i=0;i<starts.length;i++)assert(starts.filter(t=>t>=starts[i]&&t<starts[i]+1000).length<=3);
  assert.equal(MIN_PROVIDER_SPACING_MS,334);
});

test("default 40 RPM soft ceiling allows short bursts but never exceeds rolling minute",async()=>{
  let clock=0;const starts=[];
  const pacer=new NvidiaProviderPacingQueue({
    providerFetch:async()=>{starts.push(clock);return{status:200};},
    now:()=>clock,sleep:async ms=>{clock+=ms;}
  });
  assert.equal(DEFAULT_SOFT_RPM,40);
  assert.equal(pacer.softRpm,40);
  await Promise.all(Array.from({length:55},()=>pacer.fetch(URL,POST)));
  assert.equal(starts.length,55);
  assert.deepEqual(starts.slice(0,3),[0,334,668]);
  assert(starts[3]>=1500&&starts[3]<=1502); // ceil on fractional token refill
  for(let i=0;i<starts.length;i++){
    const count=starts.filter(t=>t>=starts[i]&&t<starts[i]+60000).length;
    assert(count<=40, "rolling minute must have <=40 starts");
  }
  for(let i=1;i<starts.length;i++)assert(starts[i]-starts[i-1]>=334);
});

test("soft RPM can be lowered or raised in reviewed constructor, independently of burst ceiling",async()=>{
  for(const softRpm of [10,20,60]){
    let clock=0;const starts=[];
    const pacer=new NvidiaProviderPacingQueue({
      softRpm,providerFetch:async()=>{starts.push(clock);return{status:200};},
      now:()=>clock,sleep:async ms=>{clock+=ms;}
    });
    await Promise.all(Array.from({length:softRpm+3},()=>pacer.fetch(URL,POST)));
    for(let i=0;i<starts.length;i++)
      assert(starts.filter(t=>t>=starts[i]&&t<starts[i]+60000).length<=softRpm);
  }
  for(const rpm of [0,-1,181,40.5,"40",null])
    assert.throws(()=>new NvidiaProviderPacingQueue({
      providerFetch:async()=>({status:200}),softRpm:rpm
    }),/invalid_private_provider_pacer/);
});

test("catalog GET and completion POST use the SAME pacing queue",async()=>{
 let clock=0;
 const starts=[];
 const pacer=new NvidiaProviderPacingQueue({
  providerFetch:async(url)=>{starts.push({url,clock});return{status:200};},
  now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 await pacer.fetch("https://integrate.api.nvidia.com/v1/models",
                   {method:"GET",redirect:"manual"});
 await pacer.fetch(URL,POST);
 assert.deepEqual(starts.map(x=>x.clock),[0,334]);
});

test("429 opens local cooldown without wasting additional NVIDIA requests",async()=>{
 let clock=1000,calls=0;
 const pacer=new NvidiaProviderPacingQueue({
  providerFetch:async()=>{calls++;return calls===1
    ?{status:429,headers:{get:k=>k==="Retry-After"?"90":null}}
    :{status:200};},
  now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 const denied=await pacer.fetch(URL,POST);
 assert.equal(denied.status,429);
 const localHold=await pacer.fetch(URL,POST);
 assert.equal(localHold.status,429);
 assert.equal(calls,1); // no request when the provider's cooldown is active
 assert.equal(localHold.headers.get("Retry-After"),"90");
 clock+=90000;
 const accepted=await pacer.fetch(URL,POST);
 assert.equal(accepted.status,200);assert.equal(calls,2);
});

test("429 without Retry-After remains held for at least 60 seconds",async()=>{
 let clock=2000,calls=0;
 const pacer=new NvidiaProviderPacingQueue({
  providerFetch:async()=>{calls++;return{status:429,headers:{get:()=>null}};},
  now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 await pacer.fetch(URL,POST);
 clock+=30000;
 assert.equal((await pacer.fetch(URL,POST)).status,429);
 assert.equal(calls,1);
});

test("real 429 downshifts this Worker isolate to no more than 40/minute",async()=>{
 let clock=0,calls=0;
 const times=[];
 const pacer=new NvidiaProviderPacingQueue({
  providerFetch:async()=>{
   times.push(clock);calls++;
   if(calls===1)return{status:429,headers:{get:()=>null}};
   return{status:200};
  },
  now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 await pacer.fetch(URL,POST);
 assert.equal(pacer.rateLimitObserved,true);
 assert.equal(pacer.effectiveSpacingMs,RATE_LIMITED_SPACING_MS);
 clock+=60000; // cooldown elapsed, not a repeated abusive request.
 await Promise.all(Array.from({length:5},()=>pacer.fetch(URL,POST)));
 assert.equal(calls,6);
 for(let i=2;i<times.length;i++)assert(times[i]-times[i-1]>=1500);
 assert.equal(RATE_LIMITED_SPACING_MS,1500);
});

test("3-RPS initial ceiling is independent from the unverified NVIDIA account RPM",async()=>{
 let clock=0;
 const starts=[];
 const pacer=new NvidiaProviderPacingQueue({
  providerFetch:async()=>{starts.push(clock);return{status:200};},
  now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 await Promise.all(Array.from({length:10},()=>pacer.fetch(URL,POST)));
 assert.equal(starts.length,10);
 assert(starts.every((x,i)=>i===0||x-starts[i-1]>=334));
 assert.equal(pacer.rateLimitObserved,false);
 assert.equal(pacer.effectiveSpacingMs,334);
});

test("provider header parsing supports bounded seconds and HTTP date",()=>{
 assert.equal(parsedRetryAfterMs("12",0),12000);
 assert.equal(parsedRetryAfterMs("Sun, 01 Nov 2026 21:00:20 GMT",
     Date.parse("Sun, 01 Nov 2026 21:00:00 GMT")),20000);
 assert.equal(parsedRetryAfterMs("Bearer fake",0),null);
 assert.equal(parsedRetryAfterMs("999999",0),4*60*60*1000);
});

test("unapproved hosts, methods, redirects and relaxed spacing fail closed",async()=>{
 const pacer=new NvidiaProviderPacingQueue({providerFetch:async()=>({status:200})});
 await assert.rejects(()=>pacer.fetch("https://not-nvidia.example/v1/models",
    {method:"GET",redirect:"manual"}),/destination_or_method/);
 await assert.rejects(()=>pacer.fetch(URL,{method:"GET",redirect:"manual"}),/destination_or_method/);
 await assert.rejects(()=>pacer.fetch(URL,{method:"POST",redirect:"follow"}),/destination_or_method/);
 assert.throws(()=>new NvidiaProviderPacingQueue({
     providerFetch:async()=>({status:200}),minSpacingMs:250}),/invalid_private_provider_pacer/);
});

test("network failure still consumes spacing and does not break queue",async()=>{
 let clock=0,calls=0;
 const pacer=new NvidiaProviderPacingQueue({
   providerFetch:async()=>{calls++;if(calls===1)throw Error("synthetic transport");return{status:200};},
   now:()=>clock,sleep:async ms=>{clock+=ms;}
 });
 await assert.rejects(()=>pacer.fetch(URL,POST),/synthetic transport/);
 const next=await pacer.fetch(URL,POST);
 assert.equal(next.status,200);assert.equal(clock,334);
});
