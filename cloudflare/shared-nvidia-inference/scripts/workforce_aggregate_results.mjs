// Source-version-aware offline scoreboard for independently executed,
// synthetic-only NVIDIA workforce campaign artifacts. No provider requests.
// Never accepts model responses, private inputs, tool execution or promotion.
import fs from "node:fs";
import path from "node:path";
import {pathToFileURL} from "node:url";
import {resultsFromCampaign} from "./workforce_campaign_cli.mjs";
import {evaluateWorkforceReadiness} from "../src/workforce_role_selector.js";
const SHA=/^[a-f0-9]{40}$/;
const RUN=/^github-[0-9]{6,20}$/;
const MAX_CAMPAIGNS=512;

export function aggregateWorkforceCampaigns({sourceSha,campaigns}){
 if(typeof sourceSha!=="string"||!SHA.test(sourceSha)||
    !Array.isArray(campaigns)||campaigns.length<1||
    campaigns.length>MAX_CAMPAIGNS)throw Error("invalid_aggregate_selection");
 const runIds=new Set(),modelCases=new Set(),receipts=[];
 let held=0, providerCalls=0;
 for(const c of campaigns){
  if(!c||c.source_sha!==sourceSha||!RUN.test(c.run_id))
   throw Error("source_or_execution_identity_mismatch");
  if(runIds.has(c.run_id))throw Error("duplicate_execution_run");
  // Reuse the existing strict checkpoint and metadata-only receipt validator.
  // This must run BEFORE examining or exporting any campaign observations.
  resultsFromCampaign(c);
  runIds.add(c.run_id);
  held+=c.attempt_history.length;
  providerCalls+=c.provider_http_calls;
  for(const r of c.observations){
   if(r.model===null)continue;
   // Catalog indices may change. Identity is the observed model ID, not index.
   const identity=r.model+"|"+r.case_id;
   if(modelCases.has(identity))throw Error("duplicate_model_case_cross_run");
   modelCases.add(identity);
   receipts.push(r);
  }
 }
 const readiness=evaluateWorkforceReadiness({receipts});
 return {schema:"commandcenter.workforce_multi_run_scorecard.v1",
  source_sha:sourceSha,run_ids:[...runIds].sort(),campaign_count:campaigns.length,
  unique_scored_or_review_cases:receipts.length,held_attempts:held,
  provider_http_calls:providerCalls,readiness,
  mixed_source_versions:false,raw_model_responses_exported:false,
  private_input_used:false,production_admitted:false};
}
function main(){
 const args=process.argv.slice(2);
 if(args.length<3||args[0]!=="--source"||!SHA.test(args[1])||
    args.length-2>MAX_CAMPAIGNS)throw Error("usage_source_sha_and_campaign_json_paths_required");
 const campaigns=args.slice(2).map(p=>{
  const st=fs.statSync(p);
  if(!st.isFile()||st.size>10_000_000)throw Error("unbounded_or_nonfile_campaign");
  return JSON.parse(fs.readFileSync(p,"utf8"));
 });
 process.stdout.write(JSON.stringify(aggregateWorkforceCampaigns({
  sourceSha:args[1],campaigns
 }),null,2)+"\n");
}
if(process.argv[1]&&import.meta.url===pathToFileURL(path.resolve(process.argv[1])).href){
 try{main();}catch{process.stderr.write("WORKFORCE_AGGREGATE_VALIDATION_FAILED\n");process.exitCode=1;}
}
