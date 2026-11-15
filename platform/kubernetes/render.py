#!/usr/bin/env python3
"""Render the private lab manifest; never print secrets to stdout."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
NS = 'openhvx'

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--work',required=True,help='Private environment artifact directory')
    parser.add_argument('--ca',required=True,help='Trusted CA PEM file')
    args=parser.parse_args()
    WORK=Path(args.work).resolve()
    CA=Path(args.ca).resolve()
    secret = yaml.safe_load((WORK/'secrets.yml').read_text())
    tag = (WORK/'image-tag').read_text().strip()
    overrides_path=WORK/'image-overrides.json'
    overrides=json.loads(overrides_path.read_text()) if overrides_path.exists() else {}
    network_settings_path=WORK/'network-settings.json'
    network_settings=json.loads(network_settings_path.read_text()) if network_settings_path.exists() else {}
    if type(network_settings.get('pocEnabled', False)) is not bool:
        raise ValueError('network-settings.json pocEnabled must be boolean')
    objects = [{'apiVersion': 'v1', 'kind': 'Namespace', 'metadata': {'name': NS}}]
    def add(kind,name,spec=None,**rest):
        o={'apiVersion': 'apps/v1' if kind in ['Deployment','StatefulSet'] else 'v1', 'kind':kind,'metadata':{'name':name,'namespace':NS},**rest}
        if spec is not None:o['spec']=spec
        objects.append(o);return o
    def service(name,port,selector=None,headless=False,nodeport=None):
        spec={'selector':{'app':selector or name},'ports':[{'port':port,'targetPort':port}]}
        if headless:spec.update(clusterIP='None',publishNotReadyAddresses=True)
        if nodeport:spec.update(type='NodePort');spec['ports'][0]['nodePort']=nodeport
        return add('Service',name,spec)
    def envs(values):return [{'name':k,'value':str(v)} for k,v in values.items()]
    def envsecret(name,values):
        add('Secret',name,type='Opaque',stringData={k:str(v) for k,v in values.items()})
        return [{'secretRef':{'name':name}}]
    def spread(name):return {'podAntiAffinity':{'requiredDuringSchedulingIgnoredDuringExecution':[{'labelSelector':{'matchLabels':{'app':name}},'topologyKey':'kubernetes.io/hostname'}]}}
    def workload(name,image,port,values,replicas=3,stateful=False,pvc=None,command=None,args=None,extra=None):
        c={'name':name,'image':image,'imagePullPolicy':'IfNotPresent','ports':[{'containerPort':port}], 'envFrom':envsecret(name+'-env',values), 'resources':{'requests':{'cpu':'100m','memory':'128Mi'},'limits':{'memory':'768Mi'}}}
        if command:c['command']=command
        if args:c['args']=args
        if extra:c.update(extra)
        pod={'affinity':spread(name),'containers':[c],'terminationGracePeriodSeconds':45}
        spec={'replicas':replicas,'selector':{'matchLabels':{'app':name}},'template':{'metadata':{'labels':{'app':name},'annotations':{'openhvx.io/config-digest':hashlib.sha256(json.dumps(values,sort_keys=True).encode()).hexdigest()}},'spec':pod}}
        if stateful:spec.update(serviceName=name,podManagementPolicy='Parallel')
        else:spec['strategy']={'type':'Recreate'} if replicas == 1 else {'type':'RollingUpdate','rollingUpdate':{'maxUnavailable':1,'maxSurge':0}}
        if pvc:
            spec['volumeClaimTemplates']=[{'metadata':{'name':'data'},'spec':{'accessModes':['ReadWriteOnce'],'storageClassName':'local-path','resources':{'requests':{'storage':pvc}}}}]
        add('StatefulSet' if stateful else 'Deployment',name,spec)
        return pod,c
    hosts=','.join(f'mongo-{i}.mongo.{NS}.svc.cluster.local:27017' for i in range(3))
    def mongo(db):return f'mongodb://openhvx:{secret["mongo_password"]}@{hosts}/{db}?replicaSet=rs0&authSource=admin&w=majority'
    rmq=f'amqp://openhvx:{secret["rabbit_password"]}@rabbitmq:5672/'
    add('Secret','mongo-internal',stringData={'keyfile':secret['mongo_password']*3})
    p,c=workload('mongo','mongo:7.0.24',27017,{'MONGO_INITDB_ROOT_USERNAME':'openhvx','MONGO_INITDB_ROOT_PASSWORD':secret['mongo_password']},stateful=True,pvc='8Gi',args=['--replSet','rs0','--bind_ip_all','--keyFile','/keys/keyfile','--wiredTigerCacheSizeGB','0.5'])
    c.update(volumeMounts=[{'name':'data','mountPath':'/data/db'},{'name':'keys','mountPath':'/keys','readOnly':True}],resources={'requests':{'cpu':'200m','memory':'600Mi'},'limits':{'memory':'1500Mi'}},readinessProbe={'tcpSocket':{'port':27017},'initialDelaySeconds':10})
    p['volumes']=[{'name':'key-source','secret':{'secretName':'mongo-internal'}},{'name':'keys','emptyDir':{}}]
    p['initContainers']=[{'name':'keys','image':'mongo:7.0.24','command':['sh','-c','cp /source/keyfile /keys/keyfile && chmod 400 /keys/keyfile && chown 999:999 /keys/keyfile'],'volumeMounts':[{'name':'key-source','mountPath':'/source'},{'name':'keys','mountPath':'/keys'}]}]
    service('mongo',27017,headless=True)
    conf='''cluster_formation.peer_discovery_backend = classic_config
cluster_formation.classic_config.nodes.1 = rabbit@rabbitmq-0.rabbitmq.openhvx.svc.cluster.local
cluster_formation.classic_config.nodes.2 = rabbit@rabbitmq-1.rabbitmq.openhvx.svc.cluster.local
cluster_formation.classic_config.nodes.3 = rabbit@rabbitmq-2.rabbitmq.openhvx.svc.cluster.local
disk_free_limit.absolute = 200MB
vm_memory_high_watermark.absolute = 512MiB
listeners.ssl.default = 5671
ssl_options.cacertfile = /tls/ca.pem
ssl_options.certfile = /tls/tls.crt
ssl_options.keyfile = /tls/tls.key
ssl_options.verify = verify_none
ssl_options.fail_if_no_peer_cert = false
'''
    add('ConfigMap','rabbit-config',data={'rabbitmq.conf':conf})
    p,c=workload('rabbitmq','rabbitmq:4.1.0-management',5672,{'RABBITMQ_DEFAULT_USER':'openhvx','RABBITMQ_DEFAULT_PASS':secret['rabbit_password'],'RABBITMQ_ERLANG_COOKIE':secret['rabbit_password'],'RABBITMQ_USE_LONGNAME':'true'},stateful=True,pvc='4Gi',command=['sh','-c'],args=['export RABBITMQ_NODENAME="rabbit@${HOSTNAME}.rabbitmq.openhvx.svc.cluster.local"; exec docker-entrypoint.sh rabbitmq-server'])
    c.update(volumeMounts=[{'name':'data','mountPath':'/var/lib/rabbitmq'},{'name':'config','mountPath':'/etc/rabbitmq/conf.d/20-openhvx.conf','subPath':'rabbitmq.conf'}],readinessProbe={'exec':{'command':['rabbitmq-diagnostics','-q','ping']},'initialDelaySeconds':20,'periodSeconds':15,'timeoutSeconds':10},resources={'requests':{'cpu':'100m','memory':'400Mi'},'limits':{'memory':'1Gi'}})
    p['volumes']=[{'name':'config','configMap':{'name':'rabbit-config'}}]
    add('Secret','rabbit-tls',type='Opaque',stringData={'tls.crt':(WORK/'ingress.crt').read_text(),'tls.key':(WORK/'ingress.key').read_text(),'ca.pem':CA.read_text()})
    p['volumes'].append({'name':'tls','secret':{'secretName':'rabbit-tls'}})
    c['volumeMounts'].append({'name':'tls','mountPath':'/tls','readOnly':True})
    service('rabbitmq',5672,headless=True);service('rabbit-amqps',5671,selector='rabbitmq',nodeport=30671)
    shared={'NODE_ENV':'production','CORS_ORIGIN':'https://192.168.50.20','LOG_JSON':'1','LOG_LEVEL':'info'}
    auth={**shared,'PORT':4000,'MONGO_URL':mongo('hvwm_auth'),'JWT_TENANT_SECRET':secret['JWT_TENANT_SECRET'],'JWT_ADMIN_SECRET':secret['JWT_ADMIN_SECRET'],'REGISTER_ENABLED':'false' if (WORK/'bootstrap-complete').exists() else 'true','REGISTER_API_KEY':secret['REGISTER_API_KEY']}
    controller={**shared,'PORT':3000,'MONGO_URL':mongo('hvwm'),'RMQ_URL':rmq,'AMQP_QUEUE_TYPE':'quorum','INTERNAL_API_SECRET':secret['INTERNAL_API_SECRET'],'OUTBOX_ENCRYPTION_KEY':secret['OUTBOX_ENCRYPTION_KEY'],'JWT_AGENT_SECRET':secret['JWT_AGENT_SECRET'],'JWT_BROWSER_SECRET':secret['JWT_BROWSER_SECRET'],'PUBLIC_WS_BASE':'wss://console.192-168-50-20.sslip.io/api','BROKER_WS_BASE':'wss://ws.192-168-50-20.sslip.io','STORAGE_CONTROLLER_AGENT_ID':'storage-controller-1'}
    controller['NETWORK_POC_ENABLED']='true' if network_settings.get('pocEnabled',False) else 'false'
    gateway={**shared,'PORT':8080,'AUTH_URL':'http://auth:4000','CONTROLLER_URL':'http://controller:3000','BROKER_URL':'http://ws-broker:8081','INTERNAL_API_SECRET':secret['INTERNAL_API_SECRET'],'ENABLE_APIDOCS':'false'}
    peers=json.dumps({f'ws-broker-{i}':f'http://ws-broker-{i}.ws-broker.openhvx.svc.cluster.local:8081' for i in range(3)})
    ws={**shared,'PORT':8081,'MONGO_URL':mongo('hvwm'),'JWT_AGENT_SECRET':secret['JWT_AGENT_SECRET'],'JWT_BROWSER_SECRET':secret['JWT_BROWSER_SECRET'],'BROKER_PEERS':peers,'WS_ORIGINS':'https://192.168.50.20'}
    for name,port,values in [('auth',4000,auth),('controller',3000,controller),('api-gateway',8080,gateway),('ws-broker',8081,ws)]:
        p,c=workload(name,f'openhvx/{name}:{overrides.get(name, tag)}',port,values,stateful=name=='ws-broker')
        c.update(readinessProbe={'httpGet':{'path':'/readyz','port':port},'periodSeconds':10,'timeoutSeconds':5},livenessProbe={'httpGet':{'path':'/healthz','port':port},'initialDelaySeconds':30,'periodSeconds':20,'timeoutSeconds':5},startupProbe={'httpGet':{'path':'/healthz','port':port},'failureThreshold':60,'periodSeconds':5})
        if name=='ws-broker':c['env']=[{'name':'BROKER_ID','valueFrom':{'fieldRef':{'fieldPath':'metadata.name'}}}]
        service(name,port,headless=name=='ws-broker')
    if network_settings.get('pocEnabled',False):
        network={**shared,'PORT':3002,'MONGO_URL':mongo('openhvx-network'),'RMQ_URL':rmq,'AMQP_QUEUE_TYPE':'quorum'}
        network_tag=overrides.get('network-orchestrator',tag)
        workload('network-orchestrator',f'openhvx/network-orchestrator:{network_tag}',3002,network)
    connector={**shared,'PORT':3000,'STORAGE_CONTROLLER_AGENT_ID':'storage-controller-1','RMQ_URL':rmq,'AMQP_QUEUE_TYPE':'quorum','MONGO_URL':mongo('openhvx-ceph'),'CEPH_API_URL':'https://192.168.50.30:8443','CEPH_API_USER':'openhvx','CEPH_API_PASSWORD':secret['ceph_dashboard_password'],'CEPH_DEFAULT_POOL':'rbd','CEPH_GW_ISCSI_HOST':'openhvx-ceph-01','CEPH_GW_ISCSI_IP':'192.168.50.31','CEPH_INSECURE_TLS':'false','NODE_EXTRA_CA_CERTS':'/trust/ca.pem','INVENTORY_INTERVAL_MS':'60000'}
    p,c=workload('ceph-connector',f'openhvx/ceph-connector:{tag}',3000,connector,replicas=1)
    p['volumes']=[{'name':'trust','configMap':{'name':'lab-ca'}}];c['volumeMounts']=[{'name':'trust','mountPath':'/trust','readOnly':True}]
    c['readinessProbe']={'httpGet':{'path':'/readyz','port':3000},'periodSeconds':10}
    add('ConfigMap','lab-ca',data={'ca.pem':CA.read_text()})
    add('Secret','ingress-tls',type='kubernetes.io/tls',data={'tls.crt':base64.b64encode((WORK/'ingress.crt').read_bytes()).decode(),'tls.key':base64.b64encode((WORK/'ingress.key').read_bytes()).decode()})
    objects.append({'apiVersion':'networking.k8s.io/v1','kind':'Ingress','metadata':{'name':'openhvx','namespace':NS,'annotations':{'traefik.ingress.kubernetes.io/router.entrypoints':'websecure','traefik.ingress.kubernetes.io/router.tls':'true'}},'spec':{'ingressClassName':'traefik','tls':[{'secretName':'ingress-tls'}],'rules':[{'http':{'paths':[{'path':'/api','pathType':'Prefix','backend':{'service':{'name':'api-gateway','port':{'number':8080}}}},{'path':'/ws','pathType':'Prefix','backend':{'service':{'name':'ws-broker','port':{'number':8081}}}}]}}]}})
    objects.append({'apiVersion':'traefik.io/v1alpha1','kind':'TLSStore','metadata':{'name':'default','namespace':NS},'spec':{'defaultCertificate':{'secretName':'ingress-tls'}}})
    objects.append({'apiVersion':'helm.cattle.io/v1','kind':'HelmChartConfig','metadata':{'name':'traefik','namespace':'kube-system'},'spec':{'valuesContent':'deployment:\n  kind: DaemonSet\n  replicas: 3\ntopologySpreadConstraints:\n  - maxSkew: 1\n    topologyKey: kubernetes.io/hostname\n    whenUnsatisfiable: ScheduleAnyway\n    labelSelector:\n      matchLabels:\n        app.kubernetes.io/name: traefik\n'}})
    # Generated manifests contain credentials and must remain outside version control.
    path=WORK/'openhvx.yml'
    path.write_text(yaml.safe_dump_all(objects,sort_keys=False));path.chmod(0o600)
    print('Private Kubernetes manifest rendered.')
if __name__=='__main__':main()
