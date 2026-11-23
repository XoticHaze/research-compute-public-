#!/usr/bin/env node
// Derived factory source for a NEW isolated ordinary-deployments Cloudflare account.
// It never sends an API request or needs a token.
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {readFileSync,writeFileSync,mkdirSync,existsSync} from 'node:fs';
import {resolve,dirname,join} from 'node:path';
import {fileURLToPath} from 'node:url';

export const SOURCE_PINS=Object.freeze({
  'index.js':'a072b036cc39e3ea71fe2760ebae677d329ccf3a',
  'policy.js':'2f44fa6ac971c2bcaf56ec7a958d2aefeea66e24',
  'scratch_stage.js':'f2d58bd83f5edb763c0d9feda4778fad93fd8cca',
  'machine_oidc.js':'003b0369d76f2021ba7ff28aa8b8e71230410d38',
  'queue.js':'a37b1913e32d0aa602ca1efa6c224559a8af50f2',
  'ui.js':'166428c9333ab87b73adf8facdf228e90ea7743a'
});
export const PROTECTED_ACCOUNT_IDS=Object.freeze([
  'ce43cd7b917d98a4bb4866d30eed99c0', // SlenderIQ
  'b33595eb85f346b0d1bf201810b4499a'  // neutral
]);
export const FACTORY_NAME='cc-ordinary-worker-factory';
const PACKAGE=dirname(dirname(fileURLToPath(import.meta.url)));
const ROOT=resolve(PACKAGE,'../..');
const SOURCE=resolve(ROOT,'cloudflare/shared-worker-factory/src');
export const OUT=resolve(PACKAGE,'.generated');

export function validateAccount(value) {
  if(typeof value!=='string'|| !/^[a-f0-9]{32}$/.test(value) ||
     PROTECTED_ACCOUNT_IDS.includes(value))
    throw Error('ACCOUNT_NOT_ADMITTED_NEW_ORDINARY_ONLY');
  return value;
}
function pinnedRead(name) {
  if(!(name in SOURCE_PINS)) throw Error('SOURCE_NOT_ALLOWLISTED');
  const path=join(SOURCE,name);
  const sha=execFileSync('git',['hash-object',path],
    {cwd:ROOT,encoding:'utf8',timeout:10000}).trim();
  if(sha!==SOURCE_PINS[name]) throw Error('REVIEWED_MODULE_SHA_DRIFT_'+name);
  return readFileSync(path,'utf8');
}
function exactlyOnce(source,oldValue,newValue,label){
  const parts=source.split(oldValue);
  if(parts.length!==2) throw Error('PINNED_PATCH_DRIFT_'+label);
  return parts.join(newValue);
}
const OLD_TOKEN="async function token(binding) {\n"+
  "  if (!binding || typeof binding.get!=='function') throw Error('secret_binding_absent');\n"+
  "  const value=await binding.get();\n"+
  "  if (typeof value!=='string'||value.length<20) throw Error('secret_unavailable');\n"+
  "  return value;\n}";
const NEW_TOKEN="async function token(binding) {\n"+
  "  if (typeof binding==='string' && binding.length>=20) return binding;\n"+
  "  if (!binding || typeof binding.get!=='function') throw Error('secret_binding_absent');\n"+
  "  const value=await binding.get();\n"+
  "  if (typeof value!=='string'||value.length<20) throw Error('secret_unavailable');\n"+
  "  return value;\n}";
export function build(accountId,{outDir=OUT}={}){
  const account=validateAccount(accountId);
  const src={};
  for(const name of Object.keys(SOURCE_PINS)) src[name]=pinnedRead(name);
  src['index.js']=exactlyOnce(src['index.js'],
    "const ORDINARY_ACCOUNT = 'ce43cd7b917d98a4bb4866d30eed99c0';",
    "const ORDINARY_ACCOUNT = '"+account+"';",'worker_account_pin');
  src['index.js']=exactlyOnce(src['index.js'],OLD_TOKEN,NEW_TOKEN,'runtime_cloudflare_secret');
  src['index.js']=src['index.js'].replaceAll('ORIGINAL_SLENDERIQ_ORDINARY_ONLY','CC_ISOLATED_ORDINARY_ONLY');
  src['scratch_stage.js']=exactlyOnce(src['scratch_stage.js'],
    "const ACCOUNT='ce43cd7b917d98a4bb4866d30eed99c0';",
    "const ACCOUNT='"+account+"';",'scratch_account_pin');
  src['scratch_stage.js']=exactlyOnce(src['scratch_stage.js'],
    "if(!binding || typeof binding.get!=='function')\n    throw Error('cloudflare_credentials_not_bound');\n  const bearer=await binding.get();",
    "if(!binding || (typeof binding!=='string' && typeof binding.get!=='function'))\n    throw Error('cloudflare_credentials_not_bound');\n  const bearer=typeof binding==='string'?binding:await binding.get();",
    'scratch_secret_runtime');
  src['scratch_stage.js']=src['scratch_stage.js'].replaceAll(
    'ORIGINAL_SLENDERIQ_ORDINARY_ONLY','CC_ISOLATED_ORDINARY_ONLY');
  src['policy.js']=exactlyOnce(src['policy.js'],'const RESERVED = [',
    "const RESERVED = [\n  'cc-ordinary-worker-factory',",'protected_factory_name');
  src['queue.js']=exactlyOnce(src['queue.js'],
    "if (!env.FACTORY_QUEUE_GITHUB_TOKEN ||\n      typeof env.FACTORY_QUEUE_GITHUB_TOKEN.get!=='function')\n    throw Error('queue_binding_absent');\n  const value=await env.FACTORY_QUEUE_GITHUB_TOKEN.get();",
    "if (!env.FACTORY_QUEUE_GITHUB_TOKEN ||\n      (typeof env.FACTORY_QUEUE_GITHUB_TOKEN!=='string' &&\n       typeof env.FACTORY_QUEUE_GITHUB_TOKEN.get!=='function'))\n    throw Error('queue_binding_absent');\n  const value=typeof env.FACTORY_QUEUE_GITHUB_TOKEN==='string'?\n    env.FACTORY_QUEUE_GITHUB_TOKEN:await env.FACTORY_QUEUE_GITHUB_TOKEN.get();",
    'github_queue_secret_runtime');
  const config={
    '$schema':'node_modules/wrangler/config-schema.json',
    name:FACTORY_NAME,account_id:account,main:'src/index.js',
    compatibility_date:'2026-11-23',workers_dev:true,preview_urls:false,
    durable_objects:{bindings:[{name:'FACTORY_LEDGER',class_name:'FactoryLedger'}]},
    exports:{FactoryLedger:{type:'durable-object',state:'created',storage:'sqlite'}},
    vars:{
      FACTORY_ACCOUNT_ID:account,
      FACTORY_INSTALLATION_ROLE:'CC_ISOLATED_ORDINARY_ONLY',
// Access AUD and owner-email allowlist are Cloudflare Worker ENCRYPTED SECRETS,
      // configured only after Worker Access All traffic is installed. Never
      // emit them as blank vars: Wrangler would later overwrite their runtime
      // secrets during a code-only deploy.
      FACTORY_EXECUTOR_ENABLED:'0', FACTORY_CREATE_ENABLED:'0',
      FACTORY_INSPECT_ENABLED:'0', FACTORY_SCOPED_TOKEN_ENABLED:'0',
      FACTORY_STAGE_VERSION_ENABLED:'0',
      FACTORY_MACHINE_READONLY_ENABLED:'0', FACTORY_MACHINE_INSPECT_ENABLED:'0',
      FACTORY_PROPOSAL_ONLY:'1'
    }
  };
  if(existsSync(join(outDir,'wrangler.jsonc'))) {
    const prior=JSON.parse(readFileSync(join(outDir,'wrangler.jsonc'),'utf8'));
    if(prior.account_id!==account)
      throw Error('GENERATED_ACCOUNT_MISMATCH_REFUSE_OVERWRITE');
  }
  mkdirSync(join(outDir,'src'),{recursive:true});
  const sha=x=>createHash('sha256').update(x).digest('hex');
  for(const [name,value] of Object.entries(src))
    writeFileSync(join(outDir,'src',name),value);
  const cfg=JSON.stringify(config,null,2)+'\n';
  writeFileSync(join(outDir,'wrangler.jsonc'),cfg);
  const manifest={
    schema:'commandcenter.cloudflare.isolated_ordinary_factory_manifest.v1',
    factory_name:FACTORY_NAME,account_id:account,
    role:'CC_ISOLATED_ORDINARY_ONLY',
    status:'SOURCE_PREPARED_MUTATION_FLAGS_ZERO',
    source_sha256:Object.fromEntries(Object.entries(src).map(([name,s])=>[name,sha(s)])),
    wrangler_sha256:sha(cfg),source_blob_pins:SOURCE_PINS,
    cloudflare_mutations:0,credentials_in_output:false
  };
  writeFileSync(join(outDir,'manifest.json'),JSON.stringify(manifest,null,2)+'\n');
  return manifest;
}
if(process.argv[1] && resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const argv=process.argv.slice(2);
  if(argv.length!==2||argv[0]!=='--account-id'){
    console.error('Usage: node scripts/prepare.mjs --account-id NEW_ORDINARY_ACCOUNT_ID');
    process.exit(2);
  }
  try{
    const out=build(argv[1]);
    console.log('ISOLATED_ORDINARY_FACTORY_PREPARED=1');
    console.log('ACCOUNT_ID='+out.account_id);
    console.log('FACTORY_MUTATION_FLAGS=ALL_ZERO');
    console.log('ACCOUNT_SECRET_EXPORTED=0');
  }catch(e){console.error('FACTORY_PREPARE_REJECTED='+e.message);process.exit(1);}
}
