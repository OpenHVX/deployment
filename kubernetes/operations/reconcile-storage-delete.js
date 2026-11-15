/* Explicitly finish an uncertain storage.delete. Dry-run by default.
 * --apply may delete only the accepted operation's unreferenced disk and target.
 * It refuses targets with active sessions and never disconnects initiators.
 */
const assert = require('node:assert/strict');
const {MongoClient} = require('/app/node_modules/mongodb');
const {config} = require('/app/dist/config');
const {CephApi} = require('/app/dist/services/ceph-api');
const {CephController} = require('/app/dist/controllers/ceph.controller');
const {makeResult} = require('/app/dist/services/operations/protocol');
const {AmqpService} = require('/app/dist/services/amqp');
async function main() {
  const [taskId, backendDatabase, flag] = process.argv.slice(2);
  const apply = flag === '--apply';
  assert(taskId && backendDatabase, 'Usage: node reconcile.js TASK_ID BACKEND_DATABASE [--apply]');
  const mongo = new MongoClient(process.env.MONGO_URL,{writeConcern:{w:'majority',j:true},readConcern:{level:'majority'}});
  let amqp;
  try {
    await mongo.connect();
    const db = mongo.db(backendDatabase);
    const task = await db.collection('tasks').findOne({taskId});
    assert(task && task.action === 'storage.delete' && task.contractVersion === 2);
    const journal = mongo.db().collection('cephoperations');
    const id = JSON.stringify([config.broker.service.agentId,taskId]);
    const entry = await journal.findOne({_id:id});
    assert(entry && entry.fingerprint === task.commandFingerprint);
    assert.equal(entry.command.tenantId,task.tenantId);assert.equal(entry.command.agentId,task.agentId);assert.equal(entry.command.action,task.action);
    assert(['unknown','applied'].includes(entry.result.outcome) && entry.result.sequence >= 2);
    const image = task.data.refId;
    assert(image && image === task.data.target.refId);
    assert(image.startsWith(task.tenantId+'-') && !image.includes('/'));
    const pool = config.ceph.defaultPool;
    const link = await db.collection('tenantresources').findOne({kind:'storage',tenantId:task.tenantId,agentId:task.agentId,refId:image});
    if (entry.result.outcome === 'unknown') assert(link && !link.attachedVmRefId && !link.attachedVmAgentId,'Disk must remain owned by this tenant and unattached');
    const api = new CephApi({baseUrl:config.ceph.url,username:config.ceph.user,password:config.ceph.password,allowInsecureTls:false,acceptHeader:config.ceph.apiAccept});
    const ceph = new CephController(api,pool);
    const targets = await api.getTargets();assert(Array.isArray(targets));
    const matches = targets.filter(x=>x.disks.some(d=>d.pool===pool && d.image===image));
    for (const target of matches) {
      assert(target.disks.length===1 && Number.isInteger(target.info?.num_sessions) && target.info.num_sessions===0,'Target is shared, active, or session state cannot be proved');
    }
    const exists = await ceph.diskExists(image,pool);
    const evidence = {taskId,image,pool,targets:matches.map(x=>x.target_iqn),diskPresent:exists,verifiedAt:new Date().toISOString()};
    console.log(JSON.stringify({apply,evidence}));
    if (!apply) return;
    if (entry.result.outcome === 'unknown') {
      for (const target of matches) {await ceph.deleteIscsiTarget(target.target_iqn);await ceph.waitForTargetAbsent(target.target_iqn,180000);}
      if (exists) {await ceph.deleteDisk(image,pool);await ceph.waitForDiskAbsent(pool,image,undefined,180000);}
    }
    const result = entry.result.outcome === 'applied' ? entry.result : makeResult({...entry.command,taskId,commandFingerprint:entry.fingerprint},'applied',entry.result.sequence+1,{refId:image,targetDeleted:true,deletedDisks:[{pool,image}]});
    if (entry.result.outcome === 'unknown') {
      const updated=await journal.updateOne({_id:id,fingerprint:entry.fingerprint,'result.outcome':'unknown','result.sequence':entry.result.sequence},{$set:{result,operatorReconciliation:evidence}});
      assert.equal(updated.modifiedCount,1,'Journal changed; inspect before retrying');
    }
    amqp=new AmqpService();await amqp.init();
    await amqp.confirm(config.broker.results.exchange,'task.storage.delete',Buffer.from(JSON.stringify(result)),result.eventId);
    console.log('Verified deletion result persisted and published.');
  } finally {if(amqp)await amqp.close();await mongo.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
