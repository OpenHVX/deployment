// Synthetic console peers: verify public TLS routing and cross-broker forwarding.
const WebSocket = require('/app/node_modules/ws');
const jwt = require('/app/node_modules/jsonwebtoken');
const {randomBytes} = require('node:crypto');
const fs = require('node:fs');
const peers = JSON.parse(process.env.BROKER_PEERS);
const ids = Object.keys(peers).sort();
const ca = fs.readFileSync('/tmp/openhvx-ca.pem');
async function pair(agentBase, browserBase, publicTLS) {
  const tunnelId = randomBytes(11).toString('hex');
  const vmId = randomBytes(12).toString('hex');
  const identity = {tunnelId, vmId, tenantId:'lab-console-probe'};
  const agentTicket = jwt.sign({...identity,aud:'agent',agentId:'lab-probe',action:'console.serial.open'},process.env.JWT_AGENT_SECRET,{expiresIn:'2m'});
  const browserTicket = jwt.sign({...identity,aud:'browser',mode:'serial'},process.env.JWT_BROWSER_SECRET,{expiresIn:'2m'});
  const agent = new WebSocket(agentBase+'/ws/tunnel/'+tunnelId+'?ticket='+agentTicket,{ca});
  let browser;
  try {
    await new Promise((resolve,reject)=>{agent.once('open',resolve);agent.once('error',reject);});
    browser = new WebSocket(browserBase+'/api/v1/console/serial/ws?t='+browserTicket,{ca,origin:'https://192.168.50.20'});
    await new Promise((resolve,reject)=>{browser.once('open',resolve);browser.once('error',reject);});
    const received = new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>reject(new Error('Console forwarding timed out')),10000);
      browser.on('message',data=>{if(data.toString()==='openhvx-console-probe'){clearTimeout(timeout);resolve();}});
      browser.once('error',error=>{clearTimeout(timeout);reject(error);});
    });
    // The pairing callback may complete just after the upgrade response.
    const sender=setInterval(()=>agent.send('openhvx-console-probe'),200);
    try {await received;} finally {clearInterval(sender);}
    console.log(JSON.stringify({publicTLS,crossBroker:!publicTLS,forwarding:'passed'}));
  } finally {agent.terminate();if(browser)browser.terminate();}
}
const timeout=setTimeout(()=>{console.error('Console probe exceeded its deadline');process.exit(1);},30000);
(async()=>{
  await pair(peers[ids[0]],peers[ids[1]],false);
  await pair('wss://ws.192-168-50-20.sslip.io','wss://console.192-168-50-20.sslip.io',true);
})().then(()=>clearTimeout(timeout)).catch(error=>{clearTimeout(timeout);console.error(error.message);process.exitCode=1;});
