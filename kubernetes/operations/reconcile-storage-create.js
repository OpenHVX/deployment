/* Run inside the connector container. Dry-run by default; never performs Ceph mutations.
 * Explicit operator recovery for a completed-but-uncertain storage.create.
 */
const assert = require('node:assert/strict');
const {createHash} = require('node:crypto');
const {MongoClient} = require('/app/node_modules/mongodb');
const {config} = require('/app/dist/config');
const {CephApi} = require('/app/dist/services/ceph-api');
const {CephController} = require('/app/dist/controllers/ceph.controller');
const {makeResult} = require('/app/dist/services/operations/protocol');
const {AmqpService} = require('/app/dist/services/amqp');
async function main() {
  const taskId = process.argv[2];
  const backendDatabase = process.argv[3];
  const apply = process.argv[4] === '--apply';
  assert(taskId && backendDatabase, 'Usage: node reconcile.js TASK_ID BACKEND_DATABASE [--apply]');
  const mongo = new MongoClient(process.env.MONGO_URL, {writeConcern:{w:'majority',j:true},readConcern:{level:'majority'}});
  let amqp;
  try {
    await mongo.connect();
    const task = await mongo.db(backendDatabase).collection('tasks').findOne({taskId});
    assert(task && task.action === 'storage.create' && task.contractVersion === 2);
    const id = JSON.stringify([config.broker.service.agentId, taskId]);
    const journal = mongo.db().collection('cephoperations');
    const entry = await journal.findOne({_id:id});
    assert(entry && entry.fingerprint === task.commandFingerprint);
    assert.equal(entry.command.tenantId, task.tenantId);
    assert.equal(entry.command.agentId, task.agentId);
    assert.equal(entry.command.action, task.action);
    assert(['unknown','applied'].includes(entry.result.outcome));
    assert(entry.result.sequence >= 2, 'Refusing to reconcile an execution that may still be in progress');
    const clean = value => value.trim().replace(/[^A-Za-z0-9._-]+/g,'-').replace(/-+/g,'-').replace(/^-+|-+$/g,'');
    const tenant = clean(task.tenantId), name = clean(task.data.name);
    const base = name.startsWith(tenant+'-') ? name : tenant+'-'+name;
    const image = base.slice(0,120)+'-'+createHash('sha256').update(taskId).digest('hex').slice(0,32);
    const pool = config.ceph.defaultPool;
    const iqn = 'iqn.2001-07.org.openhvx:'+image;
    const api = new CephApi({baseUrl:config.ceph.url,username:config.ceph.user,password:config.ceph.password,allowInsecureTls:false,acceptHeader:config.ceph.apiAccept});
    const ceph = new CephController(api,pool);
    const disk = await ceph.getDiskInfo(image,pool);
    assert(disk && disk.sizeBytes === task.data.sizeMB * 1024 * 1024, 'Image size does not match accepted command');
    const detail = await api.getImage(pool,image);
    const parent = detail.parent;
    assert(parent, 'Cannot prove catalog clone ancestry');
    assert.equal(parent.pool_name || parent.pool,'catalog');
    assert.equal(parent.image_name || parent.image,task.data.imageId);
    assert.equal(parent.snap_name || parent.snapshot,'base');
    const targets = await api.getTargets();
    const target = targets.find(x => x.target_iqn === iqn);
    assert(target && target.disks.length === 1);
    assert.equal(target.disks[0].pool,pool);assert.equal(target.disks[0].image,image);
    assert(target.portals.some(x => x.host === config.ceph.iscsi.gw.host && x.ip === config.ceph.iscsi.gw.ip));
    const evidence = {taskId,image,iqn,sizeBytes:disk.sizeBytes,parent,verifiedAt:new Date().toISOString()};
    console.log(JSON.stringify({apply,evidence}));
    if (!apply) return;
    const result = entry.result.outcome === 'applied' ? entry.result : makeResult({...entry.command,taskId,commandFingerprint:entry.fingerprint},'applied',entry.result.sequence+1,{disk:{id:image,refId:image,name:image,iqn,tenantId:task.tenantId}});
    if (entry.result.outcome !== 'applied') {
      const updated = await journal.updateOne({_id:id,fingerprint:entry.fingerprint,'result.outcome':'unknown','result.sequence':entry.result.sequence},{$set:{result,operatorReconciliation:evidence}});
      assert.equal(updated.modifiedCount,1,'Journal changed during verification; inspect before retrying');
    }
    // Persist before publishing. Rerunning after a lost confirmation republishes
    // the same eventId; backend inbox/transition guards make delivery idempotent.
    amqp = new AmqpService();await amqp.init();
    await amqp.confirm(config.broker.results.exchange,'task.storage.create',Buffer.from(JSON.stringify(result)),result.eventId);
    console.log('Verified result persisted and published; no storage effect repeated.');
  } finally {if(amqp)await amqp.close();await mongo.close();}
}
main().catch(error=>{console.error(error.message);process.exitCode=1;});
