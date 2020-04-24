#!/usr/bin/env python
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import argparse
from datetime import datetime
from elasticsearch_dsl import Search 
import elasticsearch
import time
import subprocess
import sys
import shutil
import os
import uuid
import base64
import json
import redis
from transcribe.render import transcribe

def _index_result(server,port,my_uuid,my_node,my_pod,es_ssl):
    index = "stockpile-results-raw"
    _es_connection_string = str(server) + ':' + str(port)
    if es_ssl == "true":
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
        es = elasticsearch.Elasticsearch([_es_connection_string], send_get_body_as='POST',
                                                 ssl_context=ssl_ctx, use_ssl=True)
    else:
        es = elasticsearch.Elasticsearch([_es_connection_string], send_get_body_as='POST')
    indexed=True
    timestamp = int(time.time())
    
    stockpile_file = os.popen('grep stockpile_output_path group_vars/all.yml | awk \'{printf $2}\'').read()

    if os.path.exists(stockpile_file):
        _upload_to_es(stockpile_file,my_uuid,timestamp,es,index,my_node,my_pod)
        _upload_to_es_bulk(stockpile_file,my_uuid,timestamp,es,index,my_node,my_pod)

def _upload_to_es(payload_file,my_uuid,timestamp,es,index,my_node,my_pod):
    payload = open(payload_file, "rb").read()
    for scribed in transcribe(payload_file,'stockpile'):
        try:
            scribe_module = json.loads(scribed)['module']
            _data = { "uuid": my_uuid,
                            "timestamp": timestamp, 
                            "node_name": my_node, 
                            "pod_name": my_pod, }
            _data.update(json.loads(scribed))
            es.index(index=scribe_module+"-metadata", body=_data)
        except Exception as e:
            print(repr(e) + "occurred for the json document:")
            print(str(scribed))
            indexed=False

def _upload_to_es_bulk(payload_file,my_uuid,timestamp,es,index,my_node,my_pod):
    payload = open(payload_file, "rb").read()
    raw_stockpile = str(base64.urlsafe_b64encode(payload))
    try:
        _data = { "uuid": my_uuid,
                        "timestamp": timestamp,
                        "node_name": my_node, 
                        "pod_name": my_pod, 
                        "data": raw_stockpile }
        es.index(index=index, body=_data)
    except Exception as e:
        print(repr(e) + "occurred for the json document:")
        indexed=False

def _run_stockpile():
    cmd = ["/usr/bin/ansible-playbook", "-i", "hosts", "stockpile.yml", "-e", "ansible_python_interpreter=/opt/app-root/bin/python"]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout,stderr = process.communicate()
    return process.returncode

def _check_index(server,port,my_uuid,my_node):
    _es_connection_string = str(server) + ':' + str(port)
    es = elasticsearch.Elasticsearch([_es_connection_string],send_get_body_as='POST')

    # We are using metadata-cpuinfo as it is a basic index that should regularly be there without any extended permissions
    s = Search(using=es, index="cpuinfo-metadata").query("match", uuid=my_uuid).query("match",node_name=my_node)

    check_results = s.execute()

    if check_results['hits']['total']['value'] > 0:
        return True
    else:
        return False

def _mark_node(r,my_node,my_uuid,server,port,check_val):
    current_val = r.get(check_val)

    # If the metadata claims to exist check if it does. If it is unable to find data then run it again
    # If its running let it run
    # Else run the collection
    if current_val == "Metadata-Exists":
        if _check_index(server,port,my_uuid,my_node):
            return "exists"
        else:
            r.set(check_val,"Metadata-Running")
            return "run"
    elif current_val == "Metadata-Running":
        return "running"
    else:
        r.set(check_val,"Metadata-Running")
        return "run"
    

def main():
    parser = argparse.ArgumentParser(description="Stockpile Wrapper script")
    parser.add_argument(
        '-s', '--server',
        help='Provide elastic server information')
    parser.add_argument(
        '-p', '--port', 
        help='Provide elastic port information')
    parser.add_argument(
        '--sslskipverify', 
        help='if es is setup with ssl, but can disable tls cert verification',
        default=False)
    parser.add_argument(
        '-u', '--uuid', 
        help='UUID to provide to elastic')
    parser.add_argument(
        '-n', '--nodename', 
        help='Node Name to provide to elastic')
    parser.add_argument(
        '-N', '--podname',
        help='Pod Name to provide to elastic')
    parser.add_argument(
        '--redisip',
        help='IP address for redis server')
    parser.add_argument(
        '--redisport',
        help='Port for the redis server')
    parser.add_argument(
        '--force',
        help='Force metadata collection regardless of redis',
        action="store_true")
    args = parser.parse_args()
    my_uuid = args.uuid
    my_node = args.nodename
    my_pod = args.podname

    run = "run"
    if args.redisip is not None and args.redisport is not None and my_node is not None and my_uuid is not None:
       r = redis.StrictRedis(host=args.redisip, port=args.redisport, charset="utf-8", decode_responses=True)
       check_val = my_uuid + "-" + my_node
       run = _mark_node(r,my_node,my_uuid,args.server,args.port,check_val)
    
    if my_uuid is None:
        my_uuid = str(uuid.uuid4())
    if run == "run" or args.force:
        _run_stockpile()
    else:
        print("Metadata already collected on ",my_node)
    
    if my_node is None:
        my_node = "Null"
    if my_pod is None:
        my_pod = "Null"
    if args.server is not "none":
        _index_result(args.server,args.port,my_uuid,my_node,my_pod,args.sslskipverify)
        if args.redisip is not None and args.redisport is not None and run == "run":
            r.set(check_val,"Metadata-Exists")
    print("uuid: ",my_uuid)

if __name__ == '__main__':
    sys.exit(main())
