#!/usr/bin/env python3

import subprocess
import logging
import cherrypy
import atexit
import os
import sys

notok=1  # process exit status

def flush_log():
    logging.shutdown()

atexit.register(flush_log)


# web server to respond to /DropKernelCache URL

class DropKernelCache(object):

    @cherrypy.expose
    def index(self):
        return "Hi there\n"

    @cherrypy.expose
    def DropKernelCache(self):
        cherrypy.log('asked for cache drop')
        # can't drop dirty pages
        os.sync()
        cherrypy.log('completed sync call')
        with open('/proc_sys_vm/drop_caches','a') as dcf:
            dcf.write('3\n')
        cherrypy.log('completed cache drop')
        return 'SUCCESS'

# sanity check to make sure our k8s volume is actually
# hooked into the /proc filesystem

if not os.access('/proc_sys_vm/dirty_ratio', os.R_OK):
    cherrypy.log('ERROR: No access to /proc filesystem, exiting')
    sys.exit(notok)

svcPortNum = int(os.getenv('KCACHE_DROP_PORT_NUM', "9435"))
cherrypy.log('kernel cache drop port is %d' % svcPortNum)

config = { 
        'global': {
            'server.socket_host': '0.0.0.0' ,
            'server.socket_port': svcPortNum,
        },
}
cherrypy.config.update(config)
cherrypy.quickstart(DropKernelCache())

