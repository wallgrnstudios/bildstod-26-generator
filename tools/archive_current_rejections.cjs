/* Archive current rejected candidates and cancel their public rework requests.
 * The script preserves the audit record; it never marks an image approved.
 */
const base='/Users/markuswallgren/.npm-global/lib/node_modules/firebase-tools/lib/';
const auth=require(base+'auth');const {Client}=require(base+'apiv2');
const project='wallgrnstudios-e8cb1',root=`projects/${project}/databases/(default)/documents`,profile='symbol-white-0.13-arm512';
auth.setActiveAccount({},auth.getProjectDefaultAccount('/Volumes/ExternalSSD/MyApps/Hemsidor/Wallgrn Studios'));
const firestore=new Client({urlPrefix:'https://firestore.googleapis.com',apiVersion:'v1',auth:true});
const stringValue=value=>({stringValue:value}),integerValue=value=>({integerValue:String(value)}),boolValue=value=>({booleanValue:value});
async function documents(collection){let token,rows=[];do{const r=(await firestore.get(`${root}/${collection}`,{queryParams:{pageSize:300,...(token?{pageToken:token}:{})}})).body;rows.push(...(r.documents||[]));token=r.nextPageToken;}while(token);return rows;}
async function current(){const source='https://raw.githubusercontent.com/wallgrnstudios/bildstod-26-generator';const rows=await Promise.all(Array.from({length:8},async(_,worker)=>{const r=await fetch(`${source}/generated-flux-worker-${worker}/data/${profile}/candidates.json?refresh=${Date.now()}`);if(!r.ok)throw Error(`Worker ${worker} unavailable`);const d=await r.json();return d.candidates.filter(x=>x.status==='pending_review').map(x=>[x.concept_id,x.sha256]);}));return new Map(rows.flat());}
async function main(){const [active,reviews,queue]=await Promise.all([current(),documents('bildstod26Reviews'),documents('bildstod26RenderQueue')]);const targets=reviews.filter(d=>d.fields.decision?.stringValue==='reject');if(!process.argv.includes('--apply')){console.log(JSON.stringify({archive:targets.length,concepts:[...new Set(targets.map(x=>x.fields.concept_id.stringValue))]},null,2));return;}
 const targetIds=new Set(targets.map(d=>d.name.rsplit?d.name.rsplit('/',1)[1]:d.name.split('/').at(-1))),writes=[];
 for(const doc of targets){const f={...doc.fields};delete f.updatedAt;f.decision=stringValue('archived');f.checks={mapValue:{fields:{meaning:boolValue(false),detail:boolValue(false),no_extra_meaning:boolValue(false),small_size:boolValue(false)}}};f.review_method=stringValue('bulk_archive_unsupported');f.reviewed_at=stringValue(new Date().toISOString());f.editRevision=integerValue(Number(f.editRevision.integerValue)+1);writes.push({update:{name:doc.name,fields:f},updateTransforms:[{fieldPath:'updatedAt',setToServerValue:'REQUEST_TIME'}]});}
 for(const doc of queue){const id=doc.name.split('/').at(-1);if(!targetIds.has(id)||doc.fields.cancelled?.booleanValue===true)continue;const f={...doc.fields};delete f.updatedAt;f.cancelled=boolValue(true);f.revision=integerValue(Number(f.revision.integerValue)+1);writes.push({update:{name:doc.name,fields:f},updateTransforms:[{fieldPath:'updatedAt',setToServerValue:'REQUEST_TIME'}]});}
 for(let i=0;i<writes.length;i+=400)await firestore.post(`${root}:commit`,{writes:writes.slice(i,i+400)});console.log(JSON.stringify({archived:targets.length,cancelled:writes.length-targets.length}));
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
