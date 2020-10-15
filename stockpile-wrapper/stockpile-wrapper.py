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
from elasticsearch_dsl import Search
import elasticsearch
import time
import subprocess
import sys
import os
import uuid
import base64
import json
import redis
import ssl
import hashlib
from transcribe.render import transcribe
from elasticsearch.helpers import parallel_bulk, BulkIndexError

def _connect_to_es(server, port, es_ssl):
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

    return es

def _index_result(es, my_uuid, my_node, my_pod, index_retries):
    index = "stockpile-results-raw"
    timestamp = int(time.time())

    stockpile_file = os.popen('grep stockpile_output_path group_vars/all.yml | awk \'{printf $2}\'').read()

    if os.path.exists(stockpile_file):
        _upload_to_es(stockpile_file, my_uuid, timestamp, es, my_node, my_pod, index_retries)
        _upload_to_es_bulk(stockpile_file, my_uuid, timestamp, es, index, my_node, my_pod)

def _upload_to_es(payload_file, my_uuid, timestamp, es, my_node, my_pod, index_retries):
    documents = {
            "total": 0,
            "existent": 0,
            "total": 0
    }

    def doc_stream():
        for scribed in transcribe(payload_file, 'stockpile'):
            doc = json.loads(scribed)
            es_index = "%s-metadata" % doc["module"]
            doc["uuid"] = my_uuid
            _id = hashlib.sha256(str(doc).encode()).hexdigest()
            # This information changes depending on the node and pod where stockpile-wrapper is executed
            # Don't include it in the _id calculation to avoid indexing several times documents not
            # specific to a node
            doc["node_name"] = my_node
            doc["pod_name"] = my_pod
            doc["timestamp"] = timestamp
            documents["total"] += 1
            yield {"_index": es_index,
                   "_source": doc,
                   "_id": _id,
                   "_op_type": "create"}

    failed_docs = []
    for r in range(index_retries):
        documents["failed"] = 0
        documents["existent"] = 0
        try:
            for ok, resp in parallel_bulk(es, doc_stream()):
                pass
        # Catch indexing exception
        except BulkIndexError as err:
            exception = err
            # An exception can refer to multiple documents
            for failed_doc in err.errors:
                # Document already exists in ES
                if failed_doc["create"]["status"] == 409:
                    documents["existent"] += 1
                    continue
                documents["failed"] += 1
                es_index = "%s-metadata" % failed_doc["create"]["data"]["module"]
                doc = {"_index": es_index,
                       "_source": failed_doc["create"]["data"],
                       "_id": failed_doc["create"]["_id"],
                       "_op_type": "create"}
                failed_docs.append(doc)
        except Exception as err:
            print("Unknown indexing error: %s" % err)
            return
        if not documents["failed"]:
            break
    if documents["total"] > documents["failed"] + documents["existent"]:
        print("%d documents successfully indexed" % (documents["total"] - documents["failed"] - documents["existent"]))
    if documents["failed"] > 0:
        print("%d documents couldn't be indexed" % documents["failed"])
        print("Indexing exception found %s" % exception)
    if documents["existent"] > 0:
        print("%d documents already exist in ES" % documents["existent"])


def _upload_to_es_bulk(payload_file, my_uuid, timestamp, es, index, my_node, my_pod):
    payload = open(payload_file, "rb").read()
    raw_stockpile = str(base64.urlsafe_b64encode(payload))
    try:
        _data = {"uuid": my_uuid,
                 "timestamp": timestamp,
                 "node_name": my_node,
                 "pod_name": my_pod,
                 "data": raw_stockpile}
        es.index(index=index, body=_data)
    except Exception as e:
        print("Indexing exception found %s" % e)


def _run_stockpile(tags, skip_tags):
    cmd = ["ansible-playbook", "-i", "hosts", "stockpile.yml", "--tags", tags, "--skip-tags", skip_tags]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    return process.returncode, stdout.decode("utf-8"), stderr.decode("utf-8")


def _check_index(es, my_uuid, my_node):
    # We are using metadata-cpuinfo as it is a basic index that should regularly be there without any extended permissions
    s = Search(using=es, index="cpuinfo-metadata").query("match", uuid=my_uuid).query("match", node_name=my_node)

    check_results = s.execute()
    if check_results['hits']['total']['value'] > 0:
        return True
    else:
        return False


def _mark_node(r, my_node, my_uuid, es, check_val):
    current_val = r.get(check_val)

    # If the metadata claims to exist check if it does. If it is unable to find data then run it again
    # If its running let it run
    # Else run the collection
    if current_val == "Metadata-Exists":
        if _check_index(es, my_uuid, my_node):
            return "exists"
        else:
            r.set(check_val, "Metadata-Running")
            return "run"
    elif current_val == "Metadata-Running":
        return "running"
    else:
        r.set(check_val, "Metadata-Running")
        return "run"


def main():
    parser = argparse.ArgumentParser(description="Stockpile Wrapper script",
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '-s', '--server',
        help='Provide elastic server information')
    parser.add_argument(
        '-p', '--port',
        type=int,
        default=9200,
        help='Provide elastic port information')
    parser.add_argument(
        '--sslskipverify',
        help='If es is setup with ssl, but can disable tls cert verification',
        default=False)
    parser.add_argument(
        '--index-retries',
        type=int,
        default=3,
        help='Number of retries for indexing')
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
        type=int,
        default=6379,
        help='Port for the redis server')
    parser.add_argument(
        '--force',
        help='Force metadata collection regardless of redis',
        action="store_true")
    parser.add_argument(
        '--tags',
        help='Comma separated tags to run stockpile with',
        default='all')
    parser.add_argument(
        '--skip-tags',
        help='Comma separated tags to skip in stockpile',
        default='None')
    args = parser.parse_args()
    my_uuid = args.uuid
    my_node = args.nodename
    my_pod = args.podname

    if args.server is not None and args.port is not None:
        es = _connect_to_es(args.server, args.port, args.sslskipverify)

    run = "run"
    if args.redisip is not None and args.redisport is not None and my_node is not None and my_uuid is not None:
        pool = redis.ConnectionPool(host=args.redisip, port=args.redisport, decode_responses=True)
        r = redis.Redis(connection_pool=pool, charset="utf-8")

        check_val = my_uuid + "-" + my_node
        run = _mark_node(r, my_node, my_uuid, es, check_val)

    if my_uuid is None:
        my_uuid = str(uuid.uuid4())
    if run == "run" or args.force:
        rc, stdout, stderr = _run_stockpile(args.tags, args.skip_tags)
        if rc != 0:
            print("Stockpile execution error: %s" % stderr)
            sys.exit(1)
    else:
        print("Metadata already collected on %s " % my_node)

    if my_node is None:
        my_node = "Null"
    if my_pod is None:
        my_pod = "Null"
    if args.server != "none":
        _index_result(es, my_uuid, my_node, my_pod, args.index_retries)
        if args.redisip is not None and args.redisport is not None and run == "run":
            r.set(check_val, "Metadata-Exists")
    if args.redisip is not None and args.redisport is not None and my_node is not None and my_uuid is not None:
        print("Closing Redis connection")
        r.client_setname(my_pod)
        clients = r.client_list()
        for x in range(len(clients)):
            if clients[x]["name"] == my_pod:
                my_id = clients[x]["id"]
                break
        r.client_kill_filter(_id=my_id,skipme=False)

    if es is not None:
        print("Attempting to close ES connection")
        es.close()
    print("uuid: %s" % my_uuid)


if __name__ == '__main__':
    sys.exit(main())
