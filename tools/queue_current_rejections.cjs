/* Queue only current explicitly rejected/revise image versions for replacement.
 * This local admin tool never reads private notes into the public render queue.
 */
const base='/Users/markuswallgren/.npm-global/lib/node_modules/firebase-tools/lib/';
const auth=require(base+'auth');const {Client}=require(base+'apiv2');
const project='wallgrnstudios-e8cb1',collection='bildstod26RenderQueue';
auth.setActiveAccount({},auth.getProjectDefaultAccount('/Volumes/ExternalSSD/MyApps/Hemsidor/Wallgrn Studios'));
const firestore=new Client({urlPrefix:'https://firestore.googleapis.com',apiVersion:'v1',auth:true});
const string=value=>({stringValue:value}),integer=value=>({integerValue:String(value)});
const fields=request=>({concept_id:string(request.concept_id),source_sha256:string(request.source_sha256),prompt_en:string(request.prompt_en),public_approved:{booleanValue:true},schema_version:integer(1),revision:integer(1),createdAt:{timestampValue:new Date().toISOString()}});
const getValue=field=>field&&(field.stringValue??field.integerValue??field.booleanValue??field.timestampValue);
async function documents(name){let token,rows=[];do{const result=(await firestore.get('projects/'+project+'/databases/(default)/documents/'+name,{queryParams:{pageSize:300,...(token?{pageToken:token}:{})}})).body;rows.push(...(result.documents||[]));token=result.nextPageToken;}while(token);return rows;}
async function main(){
 const [snapshot,symbols,reviews,queue]=await Promise.all([
  fetch('https://wallgrn.com/admin/bildstod-26/candidate-snapshot.json').then(r=>r.json()),
  fetch('https://raw.githubusercontent.com/wallgrnstudios/bildstod-26-generator/main/catalog/pilot/symbols.json').then(r=>r.json()),
  documents('bildstod26Reviews'),documents(collection)]);
 const candidates=new Map(snapshot.candidates.map(c=>[c.concept_id,c])),briefs=new Map(symbols.map(s=>[s.id,s]));
 const queued=new Set(queue.map(d=>d.name.rsplit?d.name.rsplit('/',1)[1]:d.name.split('/').at(-1)));
 const requests=[];
 for(const doc of reviews){const review=Object.fromEntries(Object.entries(doc.fields).map(([k,v])=>[k,getValue(v)])),candidate=candidates.get(review.concept_id),brief=briefs.get(review.concept_id);
  if(!candidate||!brief||!['reject','revise'].includes(review.decision)||review.sha256!==candidate.sha256)continue;
  const prompt=brief.visual_prompt_en.trim(),id=review.concept_id+'_'+review.sha256;
  if(prompt.length<10||prompt.length>700)throw Error('Invalid current prompt: '+review.concept_id);
  if(!queued.has(id))requests.push({concept_id:review.concept_id,label_sv:candidate.label_sv,source_sha256:review.sha256,prompt_en:prompt});
 }
 requests.sort((a,b)=>a.concept_id.localeCompare(b.concept_id));
 if(!process.argv.includes('--apply')){console.log(JSON.stringify({count:requests.length,requests},null,2));return;}
 for(const request of requests){const id=request.concept_id+'_'+request.source_sha256;await firestore.patch('projects/'+project+'/databases/(default)/documents/'+collection+'/'+id,{fields:fields(request)});}
 console.log(JSON.stringify({queued:requests.length,ids:requests.map(r=>r.concept_id)}));
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
