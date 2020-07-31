#!/usr/bin/env python3

import subprocess
import logging
import cherrypy
import atexit
import os
import sys

logging.basicConfig(filename='/tmp/dropcache.log', level=logging.DEBUG)
logger = logging.getLogger('dropcache')
logger.setLevel(logging.INFO)

# sanity check to make sure our k8s volume is actually
# hooked into the /proc filesystem

if not os.access('/proc_sys_vm/dirty_ratio', os.R_OK):
    logger.error('No access to /proc filesystem, exiting')
    sys.exit(1)

svcPortNum=9435
portnumstr = os.getenv('KCACHE_DROP_PORT_NUM')
if portnumstr != None:
    svcPortNum = int(portnumstr)

def flush_log():
    logging.shutdown()

atexit.register(flush_log)

class DropKernelCache(object):

    @cherrypy.expose
    def index(self):
        return "Hi there\n"

    @cherrypy.expose
    def DropKernelCache(self):
        logger.info('asked for cache drop')
        os.sync()
        logger.info('completed sync call')
        with open('/proc_sys_vm/drop_caches','a') as dcf:
            dcf.write('3\n')
        logger.info('completed cache drop')
        return 'SUCCESS'

if __name__ == '__main__':
    config = { 
        'global': {
            'server.socket_host': '0.0.0.0' ,
            'server.socket_port': svcPortNum,
        },
    }
    cherrypy.config.update(config)
    cherrypy.quickstart(DropKernelCache())
